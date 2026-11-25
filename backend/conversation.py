"""
backend/conversation.py - Conversation context and session management
Manages multi-turn conversation state including profile extraction,
language detection, and conversational appointment state.
"""
import logging
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import config
from backend.models import CustomerProfile, ConversationContext, Message
from backend import lead_qualification as lq
from backend import database as db

logger = logging.getLogger(__name__)

# In-memory session store (supplemented by DB persistence)
_sessions: Dict[str, ConversationContext] = {}

NON_NAME_WORDS = {
    "looking", "interested", "searching", "planning", "calling", "here", "from",
    "a", "an", "the", "in", "at", "on", "to", "for", "with", "about", "budget",
    "needing", "wanting", "buying", "checking", "asking", "trying", "hoping",
    "ready", "going", "moving", "relocating", "available", "free", "fine",
    "good", "great", "sure", "yes", "no", "ok", "okay", "happy", "excited",
    "based", "currently", "actually", "just", "only", "also", "very", "quite",
    "you", "sir", "maam", "madam", "hi", "hello", "namaste", "dreamhome",
    "phagwara", "jalandhar", "ludhiana", "nawanshahr", "adampur", "apartment",
    "villa", "house", "property", "bhk", "lakh", "crore", "please", "thank",
}


def create_session(language: str = None) -> ConversationContext:
    """Create a new conversation session."""
    session_id = str(uuid.uuid4())
    conv_uuid = str(uuid.uuid4())
    lang = language or (config.DEFAULT_LANGUAGE if config.DEFAULT_LANGUAGE != "auto" else "en")

    context = ConversationContext(
        conversation_id=conv_uuid,
        session_id=session_id,
        messages=[],
        customer_profile=CustomerProfile(),
        language=lang,
    )

    try:
        db_id = db.create_conversation(conv_uuid, session_id, language=lang)
        context.__dict__["_db_id"] = db_id
    except Exception as e:
        logger.warning(f"Could not persist conversation to DB: {e}")
        context.__dict__["_db_id"] = None

    _sessions[session_id] = context
    return context


def get_session(session_id: str) -> Optional[ConversationContext]:
    """Get conversation session by ID."""
    return _sessions.get(session_id)


def detect_language(text: str, hint: str = None) -> str:
    """Detect English or Hindi from Devanagari script or Hinglish cues."""
    if hint in ("en", "hi"):
        return hint
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    hinglish_cues = ["namaste", "mujhe", "chahiye", "ghar", "kitna", "mera naam", "bataiye", "kripya", "haan"]
    text_lower = text.lower()
    if sum(1 for cue in hinglish_cues if re.search(rf"\b{cue}\b", text_lower)) >= 2:
        return "hi"
    return "en"


def add_message_to_session(
    context: ConversationContext,
    role: str,
    content: str,
    language: str = None,
) -> ConversationContext:
    """Add a message to the conversation context and persist."""
    msg_lang = language or context.language or "en"
    msg = Message(role=role, content=content, language=msg_lang)
    context.messages.append(msg)
    context.updated_at = datetime.now()

    db_id = context.__dict__.get("_db_id")
    if db_id:
        try:
            db.add_message(db_id, role, content, msg_lang)
        except Exception as e:
            logger.warning(f"Could not persist message: {e}")

    return context


def _extract_name_from_text(text: str) -> Optional[str]:
    """Safely extract person name without false positives like 'I am looking for'."""
    patterns = [
        r"(?:my name is|name is|mera naam)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
        r"(?:call me|name\s*[:\-])\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)",
        r"(?:this is|i am|i'm)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)(?=\s*(?:[,.\-!]|and\b|from\b|calling\b|my\b|phone\b|$))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw_candidate = match.group(1).strip()
        words = [w for w in raw_candidate.split() if w.lower() not in NON_NAME_WORDS]
        if not words:
            continue
        # Reject if the very first word after "I am / this is" was a non-name verb/article
        first_word = raw_candidate.split()[0].lower()
        if first_word in NON_NAME_WORDS:
            continue
        candidate = " ".join(words[:2]).title()
        if len(candidate) >= 2 and candidate.isalpha() or all(part.isalpha() for part in candidate.split()):
            return candidate
    return None


def extract_profile_from_messages(messages: List[Message]) -> CustomerProfile:
    """
    Extract customer profile from conversation messages using safe rule-based parsing.
    Serves as immediate extractor and fallback when structured AI extraction is unavailable.
    """
    profile = CustomerProfile()

    user_messages = [m.content for m in messages if m.role == "user"]
    user_text = " ".join(user_messages).lower()
    full_text = " ".join(m.content for m in messages)

    # Extract name safely across individual user messages
    for text in user_messages:
        extracted_name = _extract_name_from_text(text)
        if extracted_name:
            profile.name = extracted_name
            break

    # Extract Indian phone number
    compact_text = re.sub(r"[\s\-()]", "", full_text)
    phone_match = re.search(r"(?:\+91|0)?([6-9]\d{9})\b", compact_text)
    if phone_match:
        digits = phone_match.group(1)
        profile.phone = f"+91-{digits[:5]}-{digits[5:]}"

    # Extract email
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", full_text)
    if email_match:
        profile.email = email_match.group(0).lower()

    # Extract budget
    budget_min, budget_max = lq.extract_budget_from_text(user_text)
    if budget_max:
        profile.budget_max = budget_max
    if budget_min:
        profile.budget_min = budget_min

    # Extract location (city, locality, or phonetic STT aliases)
    location_aliases = {
        "phagwara": "Phagwara",
        "fagwara": "Phagwara",
        "phagwada": "Phagwara",
        "फगवाड़ा": "Phagwara",
        "lpu": "Phagwara",
        "kapurthala road": "Phagwara",
        "jalandhar": "Jalandhar",
        "jullundur": "Jalandhar",
        "जालंधर": "Jalandhar",
        "model town": "Jalandhar",
        "civil lines": "Jalandhar",
        "punjabi bagh": "Jalandhar",
        "ludhiana": "Ludhiana",
        "लुधियाना": "Ludhiana",
        "sarabha nagar": "Ludhiana",
        "brs nagar": "Ludhiana",
        "dugri": "Ludhiana",
        "lohara": "Ludhiana",
        "haibowal": "Ludhiana",
        "nawanshahr": "Nawanshahr",
        "adampur": "Adampur",
    }
    for alias, city in location_aliases.items():
        if alias in user_text if any(ord(c) > 127 for c in alias) else re.search(rf"\b{re.escape(alias)}\b", user_text):
            profile.preferred_location = city
            break

    # Extract property type
    if re.search(r"\bvilla\b", user_text):
        profile.property_type = "Villa"
    elif re.search(r"\b(independent house|house|bungalow|kothi)\b", user_text):
        profile.property_type = "Independent House"
    elif re.search(r"\b(apartment|flat|bhk|बीएचके)\b", user_text) or "फ्लैट" in user_text:
        profile.property_type = "Apartment"

    # Extract bedrooms (numeric or spoken words)
    normalized_bhk_text = (
        user_text.replace("one bhk", "1 bhk")
        .replace("two bhk", "2 bhk")
        .replace("to bhk", "2 bhk")
        .replace("three bhk", "3 bhk")
        .replace("four bhk", "4 bhk")
        .replace("two bedroom", "2 bedroom")
        .replace("three bedroom", "3 bedroom")
        .replace("दो बीएचके", "2 bhk")
        .replace("तीन बीएचके", "3 bhk")
    )
    bhk_match = re.search(r"\b(\d)\s*(?:bhk|bedroom|bedrooms|bed room|br)\b", normalized_bhk_text)
    if bhk_match:
        profile.bedrooms = int(bhk_match.group(1))

    # Extract furnishing preference
    if "fully furnished" in user_text:
        profile.furnishing_preference = "Fully Furnished"
    elif "semi-furnished" in user_text or "semi furnished" in user_text:
        profile.furnishing_preference = "Semi-Furnished"
    elif "unfurnished" in user_text:
        profile.furnishing_preference = "Unfurnished"

    # Extract purchase timeline
    timeline_patterns = [
        (r"\b(immediate|immediately|asap|right away|this week|this month)\b", "Immediate"),
        (r"\b1\s*month\b", "1 month"),
        (r"\b2\s*months?\b", "2 months"),
        (r"\b3\s*months?\b", "3 months"),
        (r"\b6\s*months?\b", "6 months"),
        (r"\b(1\s*year|one year|next year)\b", "1 year"),
        (r"\bflexible\b", "Flexible"),
    ]
    for pattern, timeline_val in timeline_patterns:
        if re.search(pattern, user_text):
            profile.purchase_timeline = timeline_val
            break

    # Extract specific requirements
    req_cues = [
        "swimming pool", "pool", "gym", "parking", "garden", "ground floor",
        "ready to move", "under construction", "security", "lift", "clubhouse",
        "solar", "near lpu", "smart home",
    ]
    matched_reqs = [cue for cue in req_cues if cue in user_text]
    if matched_reqs:
        profile.specific_requirements = ", ".join(dict.fromkeys(matched_reqs))

    # Detect NRI
    if re.search(r"\b(nri|abroad|usa|uk|canada|dubai|singapore|australia)\b", user_text):
        profile.is_nri = True

    # Detect loan requirement
    if re.search(r"\b(loan|emi|mortgage|finance|financing)\b", user_text):
        profile.loan_required = True

    return profile


def merge_profiles(existing: CustomerProfile, new_data: CustomerProfile) -> CustomerProfile:
    """Merge new profile data into existing, updating newly discovered fields cleanly."""
    for field_name in CustomerProfile.model_fields:
        new_value = getattr(new_data, field_name, None)
        existing_value = getattr(existing, field_name, None)
        if new_value is not None and new_value != "":
            # Do not accidentally overwrite True/existing data with default False on is_nri
            if field_name == "is_nri" and existing_value is True and new_value is False:
                continue
            if field_name == "specific_requirements" and existing_value and new_value != existing_value:
                combined = list(dict.fromkeys(
                    [s.strip() for s in existing_value.split(",") if s.strip()]
                    + [s.strip() for s in new_value.split(",") if s.strip()]
                ))
                setattr(existing, field_name, ", ".join(combined))
                continue
            setattr(existing, field_name, new_value)
    return existing


def get_conversation_history_for_ai(
    context: ConversationContext,
    max_messages: int = None,
) -> List[Dict[str, str]]:
    """Get formatted conversation history respecting configured limit."""
    limit = max_messages or config.CONVERSATION_HISTORY_LIMIT
    messages = context.messages[-limit:]
    return [{"role": m.role, "content": m.content} for m in messages]


def end_session(session_id: str) -> None:
    """Mark session as ended."""
    if session_id in _sessions:
        _sessions[session_id].is_active = False
        db_id = _sessions[session_id].__dict__.get("_db_id")
        if db_id:
            try:
                with db.get_db_connection() as conn:
                    conn.execute(
                        "UPDATE conversations SET is_active=0 WHERE id=?", (db_id,)
                    )
            except Exception:
                pass
