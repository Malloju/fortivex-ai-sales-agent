"""
backend/appointment_service.py - Appointment booking and management
Handles availability checking, booking, and confirmation.
"""
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

import config
from backend import database as db

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(config.TIMEZONE)


def get_current_time() -> datetime:
    """Get current time in configured timezone."""
    return datetime.now(TIMEZONE)


def get_available_slots(
    start_date: date = None,
    num_days: int = 7,
) -> List[Dict[str, str]]:
    """
    Get available appointment slots for the next num_days.
    Returns list of available slot dicts.
    """
    if start_date is None:
        start_date = get_current_time().date()
    
    slots = []
    current_date = start_date
    
    # Time slots during business hours
    slot_times = []
    for hour in range(config.BUSINESS_HOURS_START, config.BUSINESS_HOURS_END):
        for minute in [0, 30]:
            if hour == config.BUSINESS_HOURS_END - 1 and minute == 30:
                continue  # Don't book last half hour
            slot_times.append(f"{hour:02d}:{minute:02d}")
    
    days_checked = 0
    while len(slots) < 10 and days_checked < num_days * 2:
        # Skip Sundays
        if current_date.weekday() == 6:
            current_date += timedelta(days=1)
            days_checked += 1
            continue
        
        for time_str in slot_times:
            dt_str = f"{current_date.strftime('%Y-%m-%d')} {time_str}:00"
            
            # Check if slot is in the past
            slot_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            slot_dt = slot_dt.replace(tzinfo=TIMEZONE)
            if slot_dt <= get_current_time() + timedelta(hours=2):
                continue  # Need at least 2 hours notice
            
            if db.check_slot_availability(dt_str):
                slots.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "time": time_str,
                    "datetime_str": dt_str,
                    "display": f"{current_date.strftime('%A, %d %B %Y')} at {time_str}",
                    "is_available": True,
                })
        
        current_date += timedelta(days=1)
        days_checked += 1
    
    return slots[:10]


def parse_appointment_datetime(date_str: str, time_str: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse and validate appointment date and time.
    Returns (date_str, time_str, datetime_str) or None if invalid.
    """
    # Normalize date
    date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%B %d %Y"]
    parsed_date = None
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str.strip(), fmt).date()
            break
        except ValueError:
            continue
    
    if not parsed_date:
        return None
    
    # Normalize time
    time_formats = ["%H:%M", "%I:%M %p", "%I %p", "%H"]
    parsed_time = None
    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_str.strip(), fmt).time()
            break
        except ValueError:
            continue
    
    if not parsed_time:
        # Try parsing hour only
        try:
            hour = int(time_str.strip().split(":")[0].split(" ")[0])
            parsed_time = datetime.strptime(f"{hour}:00", "%H:%M").time()
        except (ValueError, IndexError):
            return None
    
    # Validate business hours
    if not (config.BUSINESS_HOURS_START <= parsed_time.hour < config.BUSINESS_HOURS_END):
        return None
    
    # Validate not in past
    slot_dt = datetime.combine(parsed_date, parsed_time)
    slot_dt = slot_dt.replace(tzinfo=TIMEZONE)
    if slot_dt <= get_current_time() + timedelta(hours=2):
        return None
    
    date_out = parsed_date.strftime("%Y-%m-%d")
    time_out = parsed_time.strftime("%H:%M")
    dt_out = f"{date_out} {time_out}:00"
    
    return date_out, time_out, dt_out


def book_appointment(
    customer_id: int,
    appointment_date: str,
    appointment_time: str,
    property_id: str = None,
    property_name: str = None,
    lead_id: int = None,
    conversation_id: int = None,
    notes: str = None,
) -> Dict[str, Any]:
    """
    Book an appointment. Returns booking result dict.
    """
    # Build datetime string
    datetime_str = f"{appointment_date} {appointment_time}:00"
    
    # Check availability
    if not db.check_slot_availability(datetime_str):
        # Find alternative slots
        alternatives = get_available_slots()
        alt_text = "; ".join([s["display"] for s in alternatives[:3]])
        return {
            "success": False,
            "error": "slot_unavailable",
            "message": f"The slot {appointment_date} at {appointment_time} is already booked.",
            "alternatives": alternatives[:3],
            "alternatives_text": alt_text,
        }
    
    # Validate date/time
    result = parse_appointment_datetime(appointment_date, appointment_time)
    if result is None:
        return {
            "success": False,
            "error": "invalid_datetime",
            "message": "Invalid date or time. Please choose during business hours.",
        }
    
    date_str, time_str, dt_str = result
    
    try:
        appt_id = db.create_appointment({
            "customer_id": customer_id,
            "lead_id": lead_id,
            "conversation_id": conversation_id,
            "property_id": property_id,
            "property_name": property_name,
            "appointment_date": date_str,
            "appointment_time": time_str,
            "appointment_datetime": dt_str,
            "duration_minutes": config.APPOINTMENT_DURATION_MINUTES,
            "notes": notes,
        })
        
        # Get confirmation code
        appointments = db.list_appointments()
        appt = next((a for a in appointments if a["id"] == appt_id), {})
        confirmation_code = appt.get("confirmation_code", "N/A")
        
        logger.info(f"Appointment {appt_id} booked for customer {customer_id}")
        
        return {
            "success": True,
            "appointment_id": appt_id,
            "confirmation_code": confirmation_code,
            "date": date_str,
            "time": time_str,
            "datetime_str": dt_str,
            "property_id": property_id,
            "property_name": property_name,
            "message": (
                f"Your appointment is confirmed! Confirmation code: {confirmation_code}. "
                f"Date: {date_str} at {time_str}."
            ),
        }
        
    except Exception as e:
        logger.error(f"Appointment booking error: {e}")
        return {
            "success": False,
            "error": "db_error",
            "message": f"Could not save appointment. Please try again.",
        }


def get_suggested_slots_text() -> str:
    """Return a natural language description of available slots."""
    slots = get_available_slots()
    if not slots:
        return "Please contact our office directly to schedule a visit."
    
    slot_text = ", ".join([s["display"] for s in slots[:4]])
    return f"Available slots: {slot_text}."


def cancel_appointment(appointment_id: int) -> bool:
    """Cancel an appointment by ID."""
    return db.cancel_appointment(appointment_id)
