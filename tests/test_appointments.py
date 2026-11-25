"""
tests/test_appointments.py - Tests for appointment booking system
"""
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Use temporary database for tests."""
    import config
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "test_appt.db")
    from backend import database as db
    db.init_database()
    return db


def _get_future_slot():
    """Get a valid future date/time for testing."""
    # Get next Monday 10 AM
    now = datetime.now()
    days_ahead = 1 if now.hour < 8 else 1
    future = now + timedelta(days=days_ahead)
    # Ensure it's a weekday
    while future.weekday() == 6:  # Skip Sunday
        future += timedelta(days=1)
    return future.strftime("%Y-%m-%d"), "10:00"


def test_check_slot_availability_empty(use_temp_db):
    """Empty DB should have all slots available."""
    from backend import database as db
    date_str, time_str = _get_future_slot()
    dt_str = f"{date_str} {time_str}:00"
    assert db.check_slot_availability(dt_str) is True


def test_book_appointment(use_temp_db):
    """Test successful appointment booking."""
    from backend import database as db
    from backend import appointment_service as svc
    
    # Create customer
    cid = db.create_customer({"name": "Booking Test", "phone": "+91-11111-00000"})
    
    date_str, time_str = _get_future_slot()
    
    result = svc.book_appointment(
        customer_id=cid,
        appointment_date=date_str,
        appointment_time=time_str,
        property_name="Test Property",
    )
    
    assert result["success"] is True
    assert result["appointment_id"] > 0
    assert "confirmation_code" in result
    assert result["confirmation_code"].startswith("DH-")


def test_duplicate_appointment_prevented(use_temp_db):
    """Test that double booking is prevented."""
    from backend import database as db
    from backend import appointment_service as svc
    
    cid1 = db.create_customer({"name": "Customer A"})
    cid2 = db.create_customer({"name": "Customer B"})
    
    date_str, time_str = _get_future_slot()
    
    # First booking should succeed
    result1 = svc.book_appointment(cid1, date_str, time_str)
    assert result1["success"] is True
    
    # Second booking at same slot should fail
    result2 = svc.book_appointment(cid2, date_str, time_str)
    assert result2["success"] is False
    assert result2["error"] == "slot_unavailable"
    assert "alternatives" in result2


def test_cancel_appointment(use_temp_db):
    """Test appointment cancellation."""
    from backend import database as db
    from backend import appointment_service as svc
    
    cid = db.create_customer({"name": "Cancel Test"})
    date_str, time_str = _get_future_slot()
    
    result = svc.book_appointment(cid, date_str, time_str)
    assert result["success"]
    appt_id = result["appointment_id"]
    
    # Cancel it
    cancelled = svc.cancel_appointment(appt_id)
    assert cancelled is True
    
    # Slot should now be available again
    dt_str = f"{date_str} {time_str}:00"
    assert db.check_slot_availability(dt_str) is True


def test_get_available_slots():
    """Test slot availability listing."""
    from backend import appointment_service as svc
    slots = svc.get_available_slots()
    
    assert isinstance(slots, list)
    assert len(slots) > 0
    
    for slot in slots:
        assert "date" in slot
        assert "time" in slot
        assert "display" in slot
        assert slot["is_available"] is True


def test_parse_appointment_datetime():
    """Test datetime parsing."""
    from backend import appointment_service as svc
    
    # Valid future date
    date_str, time_str = _get_future_slot()
    result = svc.parse_appointment_datetime(date_str, time_str)
    assert result is not None
    
    # Invalid time (outside business hours)
    result_invalid = svc.parse_appointment_datetime(date_str, "23:00")
    assert result_invalid is None


def test_list_appointments(use_temp_db):
    """Test listing appointments."""
    from backend import database as db
    from backend import appointment_service as svc
    
    cid = db.create_customer({"name": "List Test"})
    date_str, time_str = _get_future_slot()
    svc.book_appointment(cid, date_str, time_str)
    
    appointments = db.list_appointments()
    assert len(appointments) >= 1
    assert all("customer_name" in a for a in appointments)
