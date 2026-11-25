"""
tests/test_ui.py - Automated Streamlit UI verification across all 7 pages,
and the redesigned AI Voice Assistance conversational interface.
"""
import io
import sys
import wave
from pathlib import Path
import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _dummy_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes((np.ones(4000, dtype="<i2") * 1000).tobytes())
    return buf.getvalue()


@pytest.fixture
def isolated_ui_db(tmp_path, monkeypatch):
    """Isolate SQLite DB for UI tests so real data/dreamhome.db stays clean."""
    import config
    from backend import database as db
    from backend import ai_agent

    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "ui_test.db")
    monkeypatch.setattr(config, "IS_DEMO_MODE", True)
    ai_agent._agent_instance = None
    db.init_database()
    yield db
    ai_agent._agent_instance = None


def _send_chat_text(at: AppTest, text: str) -> None:
    """Type into bottom composer text_input and click Send."""
    at.text_input[0].input(text)
    send_btns = [b for b in at.button if b.label == "Send"]
    assert len(send_btns) == 1
    send_btns[0].click().run()


def test_all_seven_pages_render_without_exception(isolated_ui_db):
    """Navigate through all 7 pages including AI Voice Assistance and verify zero exceptions."""
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception

    pages = [
        "🏠 Home Dashboard",
        "🎙️ AI Voice Assistance",
        "👥 CRM",
        "📅 Appointments",
        "🔍 Knowledge Base",
        "📊 Business Insights",
        "⚙️ Settings",
    ]
    for page_name in pages:
        at.sidebar.radio[0].set_value(page_name).run()
        assert not at.exception, f"Exception on page {page_name}: {at.exception}"


def test_dashboard_cta_navigates_to_voice_assistance(isolated_ui_db):
    """Verify Home Dashboard primary CTA still routes seamlessly to AI Voice Assistance."""
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    cta_btns = [b for b in at.button if "Start AI Conversation" in b.label]
    assert len(cta_btns) == 1
    cta_btns[0].click().run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "🎙️ AI Voice Assistance"


def test_auto_voice_response_cached_replay_and_new_chat(isolated_ui_db, monkeypatch):
    """
    Verify ChatGPT-style AI Voice Assistance flow:
    1. Welcome screen shown when empty; Auto-voice toggle ON by default.
    2. Sending text creates right-aligned user bubble + left-aligned AI bubble + TTS audio.
    3. Clicking Replay plays cached audio WITHOUT regenerating TTS.
    4. Turning Voice OFF skips TTS while keeping conversation history & context.
    5. Clicking '+ New Chat' clears messages cleanly.
    """
    from backend import text_to_speech as tts

    calls = []
    wav_bytes = _dummy_wav_bytes()

    def fake_tts_full(text, language="en", voice_override=None):
        calls.append((text, language))
        return {
            "success": True,
            "audio_bytes": wav_bytes,
            "mime_type": "audio/wav",
            "provider": "mock-tts",
            "voice": "test",
            "error_message": "",
        }

    monkeypatch.setattr(tts, "synthesize_speech_full", fake_tts_full)

    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("🎙️ AI Voice Assistance").run()
    assert not at.exception
    assert at.session_state["auto_voice_response"] is True
    assert len(at.chat_message) == 0

    # Turn 1 via bottom composer
    _send_chat_text(at, "I am looking for a 2 BHK apartment in Phagwara.")
    assert not at.exception
    assert len(at.chat_message) == 2
    assert any("budget" in md.value.lower() for md in at.chat_message[1].markdown)
    assert len(calls) == 1
    assert 1 in at.session_state["tts_cache"]
    assert at.session_state["pending_autoplay_idx"] is None

    # Replay must NOT regenerate TTS
    replay_btns = [b for b in at.button if "Replay" in b.label]
    assert len(replay_btns) == 1
    replay_btns[0].click().run()
    assert not at.exception
    assert len(calls) == 1

    # Turn 2: toggle Voice OFF and preserve context (remembers Phagwara + 2 BHK)
    voice_toggles = [t for t in at.toggle if "Voice" in t.label]
    assert len(voice_toggles) == 1
    voice_toggles[0].set_value(False).run()
    assert at.session_state["auto_voice_response"] is False

    _send_chat_text(at, "Around 50 lakh.")
    assert not at.exception
    assert len(calls) == 1  # TTS skipped when OFF
    assert len(at.chat_message) == 4
    assert any("Phagwara" in md.value for md in at.chat_message[3].markdown)

    # New Chat clears conversation cleanly
    new_btns = [b for b in at.button if "New Chat" in b.label]
    assert len(new_btns) == 1
    new_btns[0].click().run()
    assert not at.exception
    assert len(at.chat_message) == 0


def test_tts_failure_shows_error_and_retry_works(isolated_ui_db, monkeypatch):
    """Verify TTS failure displays friendly error + Retry Voice button, and retry succeeds."""
    from backend import text_to_speech as tts

    attempt = {"n": 0}
    wav_bytes = _dummy_wav_bytes()

    def flaky_tts(text, language="en", voice_override=None):
        attempt["n"] += 1
        if attempt["n"] == 1:
            return {
                "success": False,
                "audio_bytes": None,
                "mime_type": "audio/mpeg",
                "provider": "none",
                "voice": "en-IN-NeerjaNeural",
                "error_message": "Simulated TTS failure",
            }
        return {
            "success": True,
            "audio_bytes": wav_bytes,
            "mime_type": "audio/wav",
            "provider": "mock-tts",
            "voice": "test",
            "error_message": "",
        }

    monkeypatch.setattr(tts, "synthesize_speech_full", flaky_tts)

    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("🎙️ AI Voice Assistance").run()

    _send_chat_text(at, "I am looking for a 2 BHK apartment in Phagwara within 50 lakh")
    assert not at.exception
    assert 1 in at.session_state["tts_errors"]

    retry_btns = [b for b in at.button if "Retry Voice" in b.label]
    assert len(retry_btns) == 1
    retry_btns[0].click().run()
    assert not at.exception
    assert 1 in at.session_state["tts_cache"]
    assert 1 not in at.session_state["tts_errors"]


def test_voice_assistance_crm_persistence_across_restart(isolated_ui_db, monkeypatch):
    """Verify CRM persistence still works behind the scenes with the minimalist chat UI."""
    from backend import text_to_speech as tts
    monkeypatch.setattr(
        tts,
        "synthesize_speech_full",
        lambda *a, **kw: {
            "success": True,
            "audio_bytes": _dummy_wav_bytes(),
            "mime_type": "audio/wav",
            "provider": "mock-tts",
            "voice": "test",
            "error_message": "",
        },
    )

    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("🎙️ AI Voice Assistance").run()
    assert not at.exception

    _send_chat_text(at, "I am looking for a 2 BHK apartment in Phagwara within 50 lakh")
    assert not at.exception

    customers = isolated_ui_db.list_customers()
    assert len(customers) == 1
    assert customers[0]["preferred_location"] == "Phagwara"

    # Restart simulation preserves CRM and navigates all other pages cleanly
    at_restarted = AppTest.from_file("app.py", default_timeout=30)
    at_restarted.run()
    assert not at_restarted.exception
    at_restarted.sidebar.radio[0].set_value("👥 CRM").run()
    assert not at_restarted.exception


def test_voice_recording_handler_populates_chat_and_tts(isolated_ui_db, monkeypatch):
    """Verify voice recording pipeline inside Streamlit AppTest transcribes speech, renders chat & caches TTS."""
    from backend import speech_to_text as stt
    from backend import text_to_speech as tts

    monkeypatch.setattr(
        stt,
        "transcribe_audio_detailed",
        lambda *a, **kw: {
            "success": True,
            "text": "I am looking for a 2 BHK apartment in Phagwara within 50 lakh",
            "language": "en",
            "confidence": 0.98,
            "duration": 4.2,
            "error_code": "",
            "error_message": "",
        },
    )
    monkeypatch.setattr(
        tts,
        "synthesize_speech_full",
        lambda *a, **kw: {
            "success": True,
            "audio_bytes": _dummy_wav_bytes(),
            "mime_type": "audio/wav",
            "provider": "mock-tts",
            "voice": "test",
            "error_message": "",
        },
    )

    script = """
import io, wave, numpy as np, streamlit as st
from frontend import sales_agent
sales_agent._init_session()
if st.button("SimulateMic"):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes((np.ones(4000, dtype="<i2") * 1000).tobytes())
    sales_agent._handle_voice_recording(buf.getvalue(), "hash_mic_1", "mic.wav", st.empty())
sales_agent._render_messages()
"""
    at = AppTest.from_string(script, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.chat_message) == 0

    at.button[0].click().run()
    assert not at.exception
    assert len(at.chat_message) == 2
    assert any("2 BHK apartment in Phagwara" in md.value for md in at.chat_message[0].markdown)
    assert any("Phagwara" in md.value for md in at.chat_message[1].markdown)
    assert 1 in at.session_state["tts_cache"]
    assert "hash_mic_1" in at.session_state["processed_audio_hashes"]

