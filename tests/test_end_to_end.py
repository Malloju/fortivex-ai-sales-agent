"""
tests/test_end_to_end.py - End-to-end workflow tests
Tests the complete Section 6 sales workflow in Demo Mode and mocked Gemini SDK mode.
"""
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Use temporary database for all E2E tests."""
    import config
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "e2e_test.db")
    monkeypatch.setattr(config, "IS_DEMO_MODE", True)

    from backend import database as db
    from backend import ai_agent
    ai_agent._agent_instance = None
    db.init_database()
    yield db
    ai_agent._agent_instance = None


def _get_future_slot():
    """Get valid future weekday slot for appointment."""
    now = datetime.now()
    future = now + timedelta(days=1)
    while future.weekday() == 6:
        future += timedelta(days=1)
    return future.strftime("%Y-%m-%d"), "11:00"


def test_complete_conversational_sales_workflow(use_temp_db):
    """
    Test the mandatory Section 6 workflow end-to-end without manual DB inserts:
    1. Customer asks for 2 BHK apartment in Phagwara within 50 lakh
    2. Agent recommends matching properties and updates profile
    3. Customer gives name, phone, and timeline
    4. Lead qualification score rises cleanly
    5. Customer requests site visit -> slots offered -> picks slot -> confirms
    6. Customer, lead, appointment, and call summary all persist in SQLite
    """
    db = use_temp_db
    from backend import conversation as conv_manager
    from backend import ai_agent
    from backend import lead_qualification as lq
    from backend import crm_service
    from backend import summary_service

    context = conv_manager.create_session()
    db_conv_id = context.__dict__.get("_db_id")

    # Turn 1: Exact mandatory prompt
    msg1 = "I am looking for a 2 BHK apartment in Phagwara within a budget of 50 lakh."
    resp1, context = ai_agent.process_customer_message(msg1, context)
    assert "Sunrise Apartments" in resp1 or "Phagwara" in resp1
    assert context.customer_profile.preferred_location == "Phagwara"
    assert context.customer_profile.property_type == "Apartment"
    assert context.customer_profile.bedrooms == 2
    assert context.customer_profile.budget_max == 5_000_000
    assert context.customer_profile.name is None

    # Save initial CRM record
    cid = crm_service.upsert_customer_from_profile(
        context.customer_profile, conversation_id=db_conv_id, existing_customer_id=None
    )
    context.__dict__["_customer_id"] = cid

    # Turn 2: Name, phone, timeline
    msg2 = "My name is Arun Kumar, phone 9876512345, planning to buy in 3 months"
    resp2, context = ai_agent.process_customer_message(msg2, context)
    assert context.customer_profile.name == "Arun Kumar"
    assert context.customer_profile.phone == "+91-98765-12345"
    assert context.customer_profile.purchase_timeline == "3 months"

    # Update SAME customer record (must not create duplicate row)
    cid2 = crm_service.upsert_customer_from_profile(
        context.customer_profile, conversation_id=db_conv_id, existing_customer_id=cid
    )
    assert cid2 == cid
    assert len(db.list_customers()) == 1

    qualification = lq.score_lead(context.customer_profile)
    assert qualification.lead_score >= 85
    assert qualification.lead_status.value == "qualified"
    lead_id = crm_service.upsert_lead_from_qualification(cid, qualification)

    # Turn 3: Request site visit
    resp3, context = ai_agent.process_customer_message("I want to schedule a site visit", context)
    assert "Available Slots" in resp3 or "slot" in resp3.lower()

    # Turn 4: Choose slot
    future_date, future_time = _get_future_slot()
    resp4, context = ai_agent.process_customer_message(
        f"Let's book {future_date} at {future_time} for Sunrise Apartments", context
    )
    assert context.awaiting_appointment_confirmation is True
    assert "Confirm" in resp4

    # Turn 5: Confirm booking
    resp5, context = ai_agent.process_customer_message("Yes, please confirm", context)
    assert "Confirmed" in resp5
    assert context.booked_appointment_id is not None
    assert context.booked_confirmation_code.startswith("DH-")

    # Verify DB state
    appointments = db.list_appointments()
    assert len(appointments) == 1
    assert appointments[0]["customer_id"] == cid
    assert appointments[0]["status"] == "confirmed"

    # Generate summary
    messages = [{"role": m.role, "content": m.content} for m in context.messages]
    summary = summary_service.generate_summary(
        conversation_id=db_conv_id,
        conversation_uuid=context.conversation_id,
        customer_id=cid,
        lead_id=lead_id,
        messages=messages,
        profile=context.customer_profile,
        qualification=qualification,
        appointment_id=context.booked_appointment_id,
    )
    assert summary["appointment_booked"] is True
    assert summary["lead_score"] >= 85

    metrics = db.get_dashboard_metrics()
    assert metrics["total_customers"] == 1
    assert metrics["total_leads"] == 1
    assert metrics["qualified_leads"] == 1
    assert metrics["total_appointments"] == 1


def test_mocked_gemini_sdk_flow(monkeypatch, use_temp_db):
    """Verify Google Gen AI SDK code path using a mocked google.genai.Client."""
    import config
    from backend import ai_agent, conversation as conv_manager

    monkeypatch.setattr(config, "IS_DEMO_MODE", False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-fake-key")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Hello! Sunrise Apartments 2BHK in Phagwara is available at Rs. 45 Lakh."
    mock_client.models.generate_content.return_value = mock_resp

    agent = ai_agent.AIAgent(model_name="gemini-2.5-flash")
    agent._client = mock_client
    ai_agent._agent_instance = agent

    context = conv_manager.create_session()
    resp, updated = ai_agent.process_customer_message(
        "Tell me about 2 BHK in Phagwara", context
    )
    assert "Sunrise Apartments" in resp
    meta = updated.__dict__.get("_last_response_meta", {})
    assert meta.get("mode") == "gemini"
    assert meta.get("model_used") == "gemini-2.5-flash"


def test_conversation_context_persistence(use_temp_db):
    """Test that conversation context maintains state across turns."""
    from backend import conversation as conv_manager
    from backend import ai_agent

    context = conv_manager.create_session()
    _, ctx1 = ai_agent.process_customer_message("I am looking in Jalandhar", context)
    _, ctx2 = ai_agent.process_customer_message("I need 3 bedrooms", ctx1)

    assert len(ctx2.messages) == 4
    assert ctx2.customer_profile.preferred_location == "Jalandhar"
    assert ctx2.customer_profile.bedrooms == 3


def test_call_summary_generation():
    """Test call summary generation."""
    from backend.models import CustomerProfile
    from backend import lead_qualification as lq
    from backend import summary_service

    profile = CustomerProfile(
        name="Summary Test",
        budget_max=6_000_000,
        preferred_location="Ludhiana",
        property_type="Apartment",
        bedrooms=2,
        purchase_timeline="6 months",
    )
    qualification = lq.score_lead(profile)
    messages = [
        {"role": "user", "content": "I need a 2BHK in Ludhiana"},
        {"role": "assistant", "content": "We have great options in Ludhiana!"},
    ]

    summary = summary_service.generate_summary(
        conversation_id=1,
        conversation_uuid="test-uuid",
        customer_id=None,
        lead_id=None,
        messages=messages,
        profile=profile,
        qualification=qualification,
        appointment_id=None,
    )

    assert "summary_text" in summary
    assert len(summary["summary_text"]) > 10
    assert isinstance(summary["key_points"], list)
    assert summary["appointment_booked"] is False


def test_stt_empty_and_silent_audio_handling():
    """Test Faster-Whisper handler catches empty and silent audio gracefully."""
    import io
    import wave
    from backend import speech_to_text as stt

    # Empty bytes
    text, _, _, err = stt.transcribe_audio_bytes(b"")
    assert text == ""
    assert "empty" in err.lower()

    # Silent short WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 16000)  # 0.5s silence
    text2, _, _, err2 = stt.transcribe_audio_bytes(buf.getvalue())
    assert text2 == ""
    assert "silent" in err2.lower() or "no sound" in err2.lower() or "no audio" in err2.lower()


def test_tts_text_cleaning_and_voice_selection():
    """Test Edge TTS markdown cleanup and English/Hindi voice selection."""
    from backend import text_to_speech as tts
    import config

    cleaned = tts._clean_text_for_speech("🏠 **Sunrise Apartments** — ₹45 Lakh! #DreamHome")
    assert "**" not in cleaned
    assert "#" not in cleaned
    assert "Sunrise Apartments" in cleaned

    assert tts._get_voice("en") == config.TTS_VOICE_EN
    assert tts._get_voice("hi") == config.TTS_VOICE_HI

