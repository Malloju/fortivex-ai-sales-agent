"""
backend/ai_agent.py - AI conversation engine for DreamHome Realty
Uses the current supported Google Gen AI Python SDK (`google-genai`) with RAG
augmentation, structured outputs, conversational appointment booking, and a
transparently labeled Demo Mode fallback.
"""
import importlib.util
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import config
from backend.models import (
    CustomerProfile,
    ConversationContext,
    ExtractedCustomerInfo,
    GeneratedCallSummary,
)
from backend import rag_service
from backend import lead_qualification as lq
from backend import conversation as conv_manager
from backend import appointment_service
from backend import crm_service

logger = logging.getLogger(__name__)

GENAI_AVAILABLE: bool = importlib.util.find_spec("google.genai") is not None

SYSTEM_PROMPT = """You are Priya, an AI sales consultant for DreamHome Realty, a fictional real estate consultancy in Punjab, India (for demonstration purposes only).

Your responsibilities:
1. Warmly greet customers and understand their residential property requirements.
2. Ask relevant follow-up questions without repeating information the customer already provided.
3. Answer questions strictly using the provided COMPANY KNOWLEDGE and MATCHING PROPERTIES context.
4. NEVER invent property prices, availability, RERA approvals, legal guarantees, or financial guarantees.
5. If reliable information is not in the retrieved context, honestly tell the customer it is unavailable and offer to connect them with a consultant at +91-18001-00000.
6. Gradually collect lead details: name, budget, preferred location, property type, bedrooms, purchase timeline, and voluntary contact details.
7. Recommend matching properties from the retrieved context and offer to book a site visit appointment during business hours (Mon-Sat, 9 AM - 6 PM IST).
8. Keep responses concise (3-5 sentences plus bulleted property options when relevant).
9. Respond in the same language as the customer (English or Hindi).
"""


def _format_property_bullet(prop: Dict[str, Any]) -> str:
    """Format a property row from CSV into a clean chat bullet."""
    price_inr = int(prop.get("price_inr", 0))
    price_str = lq.format_budget(price_inr)
    return (
        f"🏠 **{prop.get('property_name')}** ({prop.get('property_id')}) — {price_str}\n"
        f"   • {prop.get('bedrooms')} BHK {prop.get('property_type')} | {prop.get('location')} | "
        f"{prop.get('area_sqft')} sqft | {prop.get('furnishing')} | {prop.get('possession_status')}\n"
        f"   • Amenities: {prop.get('amenities')}"
    )


def _extract_date_time_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse natural language date and time references from user message."""
    text_lower = text.lower()
    now = appointment_service.get_current_time()

    parsed_date: Optional[str] = None
    # Explicit YYYY-MM-DD or DD-MM-YYYY / DD/MM/YYYY
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text_lower)
    dmy_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", text_lower)
    if iso_match:
        parsed_date = iso_match.group(1)
    elif dmy_match:
        raw = dmy_match.group(1).replace("/", "-")
        try:
            parsed_date = datetime.strptime(raw, "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    elif "day after tomorrow" in text_lower:
        target = now.date() + timedelta(days=2)
        if target.weekday() == 6:
            target += timedelta(days=1)
        parsed_date = target.strftime("%Y-%m-%d")
    elif "tomorrow" in text_lower or "kal" in text_lower:
        target = now.date() + timedelta(days=1)
        if target.weekday() == 6:
            target += timedelta(days=1)
        parsed_date = target.strftime("%Y-%m-%d")
    elif "today" in text_lower or "aaj" in text_lower:
        parsed_date = now.date().strftime("%Y-%m-%d")
    else:
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        for idx, day_name in enumerate(weekdays):
            if day_name in text_lower:
                days_ahead = (idx - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                parsed_date = (now.date() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                break

    parsed_time: Optional[str] = None
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text_lower)
    hhmm_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        parsed_time = f"{hour:02d}:{minute:02d}"
    elif hhmm_match:
        hour = int(hhmm_match.group(1))
        minute = int(hhmm_match.group(2))
        parsed_time = f"{hour:02d}:{minute:02d}"

    return parsed_date, parsed_time


def _detect_property_mention(text: str, context: ConversationContext) -> Optional[str]:
    """Detect if the customer mentioned one of the listed properties."""
    text_lower = text.lower()
    for name in context.recommended_property_names:
        base_name = name.split("-")[0].strip().lower()
        if name.lower() in text_lower or (base_name and base_name in text_lower):
            return name
    # Also check properties CSV
    props = rag_service.search_properties_by_criteria(top_k=30)
    for p in props:
        pname = p.get("property_name", "")
        base_name = pname.split("-")[0].strip().lower()
        if pname.lower() in text_lower or (len(base_name) > 4 and base_name in text_lower):
            return pname
    return context.pending_property_name or (
        context.recommended_property_names[0] if context.recommended_property_names else None
    )


class AIAgent:
    """Main AI conversation agent with Google Gen AI SDK + RAG integration."""

    def __init__(self, model_name: Optional[str] = None):
        self._client = None
        self._active_model = model_name or config.GEMINI_MODEL
        self._init_error: Optional[str] = None
        self._init_gemini()

    def _init_gemini(self):
        """Initialize Google Gen AI SDK client if API key is configured and not in demo mode."""
        if config.IS_DEMO_MODE:
            logger.info("Running in DEMO mode. Deterministic responses will be used.")
            return

        if not GENAI_AVAILABLE:
            self._init_error = "google-genai SDK is not installed. Run: pip install google-genai"
            logger.error(self._init_error)
            return

        try:
            from google import genai
            self._client = genai.Client(api_key=config.GEMINI_API_KEY.strip())
            logger.info(f"Google Gen AI SDK initialized (model: {self._active_model})")
        except Exception as e:
            self._init_error = f"Failed to initialize Google Gen AI client: {e}"
            logger.error(self._init_error)
            self._client = None

    def is_live_ai_available(self) -> bool:
        """Return True only when live Gemini API is configured and client initialized."""
        return (not config.IS_DEMO_MODE) and (self._client is not None)

    def generate_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        customer_profile: CustomerProfile,
        retrieved_docs: List[str] = None,
        context: Optional[ConversationContext] = None,
    ) -> Tuple[str, CustomerProfile, Dict[str, Any]]:
        """
        Generate AI response for a user message.
        Returns (response_text, updated_profile, metadata).
        """
        # 1. Extract profile updates from latest user message (fast rule-based pass)
        new_profile = conv_manager.extract_profile_from_messages(
            [type("M", (), {"role": "user", "content": user_message})()]
        )
        updated_profile = conv_manager.merge_profiles(customer_profile, new_profile)

        metadata: Dict[str, Any] = {
            "mode": "demo" if config.IS_DEMO_MODE else "gemini",
            "model_used": "demo-deterministic" if config.IS_DEMO_MODE else self._active_model,
            "error_message": self._init_error,
            "appointment_action": None,
        }

        # 2. If live Gemini is available, also run structured extraction on recent conversation
        if self.is_live_ai_available():
            recent_text = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in (conversation_history[-6:] + [{"role": "user", "content": user_message}])
            )
            structured_data = self.extract_structured_profile(recent_text)
            if structured_data:
                try:
                    ai_profile = CustomerProfile(**{
                        k: v for k, v in structured_data.items()
                        if k in CustomerProfile.model_fields and v is not None
                    })
                    updated_profile = conv_manager.merge_profiles(updated_profile, ai_profile)
                except Exception as e:
                    logger.warning(f"Ignoring invalid structured profile output: {e}")

        # 3. Check conversational appointment booking workflow first
        if context is not None:
            appt_reply, appt_action = self._handle_conversational_appointment(
                user_message, updated_profile, context
            )
            if appt_reply is not None:
                metadata["appointment_action"] = appt_action
                return appt_reply, updated_profile, metadata

        # 4. Generate response via Demo Mode or Gemini SDK
        if config.IS_DEMO_MODE:
            response = self._demo_response(user_message, updated_profile, retrieved_docs, context)
            return response, updated_profile, metadata

        if not self._client:
            metadata["mode"] = "fallback_demo"
            metadata["model_used"] = "demo-fallback"
            metadata["error_message"] = (
                self._init_error
                or "Gemini client is unavailable. Showing deterministic demo response instead."
            )
            response = self._demo_response(user_message, updated_profile, retrieved_docs, context)
            return response, updated_profile, metadata

        response, api_err, used_model = self._gemini_response(
            user_message, conversation_history, updated_profile, retrieved_docs, context
        )
        metadata["model_used"] = used_model
        if api_err:
            metadata["mode"] = "fallback_demo"
            metadata["error_message"] = api_err
        return response, updated_profile, metadata

    def _gemini_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        profile: CustomerProfile,
        retrieved_docs: List[str] = None,
        context: Optional[ConversationContext] = None,
    ) -> Tuple[str, Optional[str], str]:
        """Generate response using `google-genai` SDK with fallback model support."""
        from google.genai import types

        matching_props = rag_service.search_properties_by_criteria(
            location=profile.preferred_location,
            property_type=profile.property_type,
            bedrooms=profile.bedrooms,
            max_budget=profile.budget_max,
            top_k=4,
        )
        if context is not None and matching_props:
            context.recommended_property_names = [p["property_name"] for p in matching_props]

        context_sections = []
        if retrieved_docs:
            context_sections.append("--- RETRIEVED COMPANY KNOWLEDGE ---\n" + "\n\n".join(retrieved_docs[:5]))
        if matching_props:
            props_text = "\n".join(_format_property_bullet(p) for p in matching_props)
            context_sections.append(f"--- MATCHING PROPERTIES FROM INVENTORY ---\n{props_text}")

        profile_text = self._build_profile_context(profile)
        if profile_text:
            context_sections.append(profile_text)

        available_slots = appointment_service.get_available_slots()[:4]
        if available_slots:
            slots_str = ", ".join(s["display"] for s in available_slots)
            context_sections.append(f"--- NEXT AVAILABLE APPOINTMENT SLOTS ---\n{slots_str}")

        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

        augmented_user_msg = "\n\n".join(context_sections + [f"Customer message: {user_message}"])
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=augmented_user_msg)]))

        models_to_try = [self._active_model]
        if config.GEMINI_FALLBACK_MODEL and config.GEMINI_FALLBACK_MODEL != self._active_model:
            models_to_try.append(config.GEMINI_FALLBACK_MODEL)

        last_err = ""
        for model_id in models_to_try:
            try:
                response = self._client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.5,
                        max_output_tokens=800,
                    ),
                )
                if response and response.text:
                    return response.text.strip(), None, model_id
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Gemini call failed on model '{model_id}': {e}")
                err_lower = last_err.lower()
                if "api_key" in err_lower or "api key" in err_lower or "permission" in err_lower or "unauthorized" in err_lower:
                    friendly_err = (
                        "Invalid or unauthorized Gemini API key. Please check GEMINI_API_KEY in `.env` "
                        "or switch APP_MODE=demo. Falling back to demo response for this turn."
                    )
                    return self._demo_response(user_message, profile, retrieved_docs, context), friendly_err, "demo-fallback"
                if "quota" in err_lower or "429" in err_lower or "rate" in err_lower:
                    friendly_err = (
                        "Gemini API rate limit reached. Please wait briefly before sending the next message. "
                        "Showing demo fallback response for continuity."
                    )
                    return self._demo_response(user_message, profile, retrieved_docs, context), friendly_err, "demo-fallback"

        friendly_err = (
            f"Configured Gemini model `{self._active_model}` could not be reached ({last_err[:120]}). "
            f"Update `GEMINI_MODEL` in `.env` (e.g., `gemini-2.5-flash` or `gemini-2.0-flash`). "
            "Showing demo fallback response."
        )
        return self._demo_response(user_message, profile, retrieved_docs, context), friendly_err, "demo-fallback"

    def _handle_conversational_appointment(
        self,
        user_message: str,
        profile: CustomerProfile,
        context: ConversationContext,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Handle multi-turn appointment slot offering, validation, confirmation, and booking."""
        msg_lower = user_message.lower().strip()
        parsed_date, parsed_time = _extract_date_time_from_text(user_message)
        has_booking_intent = any(
            kw in msg_lower
            for kw in ["appointment", "visit", "schedule", "book", "slot", "tour", "site visit"]
        )
        has_confirm_intent = any(
            re.search(rf"\b{kw}\b", msg_lower)
            for kw in ["yes", "confirm", "book it", "sure", "ok", "okay", "go ahead", "please book", "haan"]
        )

        # Case A: User is responding to a pending confirmation prompt
        if context.awaiting_appointment_confirmation and context.pending_appointment_date and context.pending_appointment_time:
            if any(w in msg_lower for w in ["no", "cancel", "change", "different", "another"]):
                context.awaiting_appointment_confirmation = False
                context.pending_appointment_date = None
                context.pending_appointment_time = None
                slots_text = "\n".join(f"• {s['display']}" for s in appointment_service.get_available_slots()[:4])
                return (
                    f"No problem! Let's pick a different slot. Here are our next available times:\n\n{slots_str if False else slots_text}\n\nWhich date and time works best for you?",
                    None,
                )

            if parsed_date or parsed_time:
                # User picked a different date/time instead of confirming old one
                context.pending_appointment_date = parsed_date or context.pending_appointment_date
                context.pending_appointment_time = parsed_time or context.pending_appointment_time
            elif has_confirm_intent:
                # Confirm & book into SQLite
                return self._finalize_chat_booking(profile, context)

        # Case B: User provided both date & time along with booking/slot selection
        if (parsed_date and parsed_time) and (
            has_booking_intent or context.pending_property_name or context.recommended_property_names or context.awaiting_appointment_confirmation
        ):
            prop_name = _detect_property_mention(user_message, context) or "DreamHome Property Visit"
            validated = appointment_service.parse_appointment_datetime(parsed_date, parsed_time)
            if validated is None:
                slots_text = "\n".join(f"• {s['display']}" for s in appointment_service.get_available_slots()[:3])
                return (
                    f"Sorry, **{parsed_date} at {parsed_time}** is outside our visiting hours "
                    f"(Mon–Sat, {config.BUSINESS_HOURS_START}:00–{config.BUSINESS_HOURS_END}:00 IST, "
                    f"minimum 2 hours advance notice).\n\nHere are available alternative slots:\n{slots_text}\n\n"
                    f"Which slot would you like to book?",
                    None,
                )

            norm_date, norm_time, norm_dt = validated
            from backend import database as db
            if not db.check_slot_availability(norm_dt):
                slots_text = "\n".join(f"• {s['display']}" for s in appointment_service.get_available_slots()[:3])
                return (
                    f"The slot on **{norm_date} at {norm_time}** is already booked.\n\n"
                    f"Here are our next available slots:\n{slots_text}\n\n"
                    f"Would you like one of these instead?",
                    None,
                )

            context.pending_appointment_date = norm_date
            context.pending_appointment_time = norm_time
            context.pending_property_name = prop_name

            # If explicit confirm keyword + date/time in same message (e.g. "Confirm visit tomorrow at 10 AM")
            if "confirm" in msg_lower or "book it" in msg_lower:
                return self._finalize_chat_booking(profile, context)

            context.awaiting_appointment_confirmation = True
            return (
                f"The slot on **{norm_date} at {norm_time} IST** for **{prop_name}** is available!\n\n"
                f"Please reply **Yes / Confirm** to finalize your appointment"
                + ("" if profile.name else " (and feel free to share your name if you haven't yet)") + ".",
                {"status": "awaiting_confirmation", "date": norm_date, "time": norm_time, "property": prop_name},
            )

        # Case C: User expresses general appointment intent without date/time
        if has_booking_intent and not (parsed_date and parsed_time):
            prop_name = _detect_property_mention(user_message, context) or "your preferred property"
            context.pending_property_name = prop_name
            slots = appointment_service.get_available_slots()[:4]
            slots_text = "\n".join(f"• {s['display']}" for s in slots)
            return (
                f"I'd be happy to schedule a site visit for **{prop_name}**! "
                f"Our visiting hours are Monday–Saturday, {config.BUSINESS_HOURS_START}:00 AM to {config.BUSINESS_HOURS_END - 12}:00 PM IST.\n\n"
                f"📅 **Available Slots:**\n{slots_text}\n\n"
                f"Which date and time would you prefer?",
                {"status": "slots_offered"},
            )

        return None, None

    def _finalize_chat_booking(
        self,
        profile: CustomerProfile,
        context: ConversationContext,
    ) -> Tuple[str, Dict[str, Any]]:
        """Persist customer, lead, and confirmed appointment into SQLite."""
        db_conv_id = context.__dict__.get("_db_id")
        existing_cid = context.__dict__.get("_customer_id")
        customer_id = crm_service.upsert_customer_from_profile(
            profile, db_conv_id, existing_customer_id=existing_cid
        )
        context.__dict__["_customer_id"] = customer_id

        qualification = lq.score_lead(profile)
        lead_id = crm_service.upsert_lead_from_qualification(customer_id, qualification)

        result = appointment_service.book_appointment(
            customer_id=customer_id,
            appointment_date=context.pending_appointment_date,
            appointment_time=context.pending_appointment_time,
            property_name=context.pending_property_name or "DreamHome Property Visit",
            lead_id=lead_id,
            conversation_id=db_conv_id,
            notes="Booked conversationally via AI Sales Agent",
        )

        context.awaiting_appointment_confirmation = False
        if result["success"]:
            context.booked_appointment_id = result["appointment_id"]
            context.booked_confirmation_code = result["confirmation_code"]
            return (
                f"✅ **Appointment Confirmed!**\n\n"
                f"• **Confirmation Code:** `{result['confirmation_code']}`\n"
                f"• **Property:** {result.get('property_name')}\n"
                f"• **Date & Time:** {result['date']} at {result['time']} IST\n"
                f"• **Customer:** {profile.name or 'Guest'}\n\n"
                f"Your details and appointment have been saved in our CRM. You can view or manage it anytime in the **Appointments** tab!",
                result,
            )

        alt_text = result.get("alternatives_text", "")
        return (
            f"⚠️ {result['message']}" + (f"\n\nAvailable alternatives: {alt_text}" if alt_text else ""),
            result,
        )

    def _demo_response(
        self,
        user_message: str,
        profile: CustomerProfile,
        retrieved_docs: List[str] = None,
        context: Optional[ConversationContext] = None,
    ) -> str:
        """
        [DEMO MODE] Deterministic, profile-aware response generator using actual CSV/RAG data.
        Avoids asking again for details already present in `profile`.
        """
        msg_lower = user_message.lower()

        if any(re.search(rf"\b{w}\b", msg_lower) for w in ["hello", "hi", "namaste", "hey", "good morning", "good afternoon"]):
            if context and len(context.messages) > 0:
                return "Hello! How can I assist you further with DreamHome Realty properties?"
            return (
                "Namaste! Welcome to DreamHome Realty (Demo Mode). I'm Priya, your AI property consultant. "
                "We list fictional demonstration homes across Phagwara, Jalandhar, Ludhiana, Nawanshahr, and Adampur. "
                "What location, property type, and budget are you looking for?"
            )

        # Topic-specific RAG-backed demo answers BEFORE generic property re-listing
        if any(w in msg_lower for w in ["loan", "emi", "payment", "bank", "finance"]):
            return (
                "We coordinate residential home loan documentation with partner banks (SBI, HDFC, ICICI, Axis, and PNB), "
                "alongside direct bank transfer and milestone-linked plans for under-construction homes. "
                "Loan approval and exact interest rates depend on lender eligibility (no guarantee implied). "
                "Would you like me to recommend properties or schedule a site visit?"
            )

        if any(w in msg_lower for w in ["refund", "cancel", "policy", "office", "hours", "timing", "rera", "brokerage"]):
            if retrieved_docs:
                return f"Here is our policy information from the DreamHome Realty knowledge base:\n\n{retrieved_docs[0][:450]}"

        if any(w in msg_lower for w in ["ameniti", "gym", "pool", "parking", "security"]):
            if retrieved_docs:
                return f"Here are the amenities details from our portfolio:\n\n{retrieved_docs[0][:450]}"

        # Search matching properties from actual CSV whenever criteria are present
        if any([profile.preferred_location, profile.budget_max, profile.bedrooms, profile.property_type]):
            # If customer gave location/property type but has NOT shared budget yet, ask preferred budget first
            if (profile.preferred_location or profile.property_type or profile.bedrooms) and not profile.budget_max:
                criteria_desc = " ".join(
                    part for part in [
                        f"{profile.bedrooms} BHK" if profile.bedrooms else None,
                        profile.property_type or "property",
                        f"in {profile.preferred_location}" if profile.preferred_location else None,
                    ] if part
                )
                sample_matches = rag_service.search_properties_by_criteria(
                    location=profile.preferred_location,
                    property_type=profile.property_type,
                    bedrooms=profile.bedrooms,
                    top_k=2,
                )
                if sample_matches:
                    prices = [int(p["price_inr"]) for p in sample_matches]
                    range_hint = f" (our listings start around {lq.format_budget(min(prices))})"
                else:
                    range_hint = ""
                if context and context.language == "hi":
                    return (
                        f"बिल्कुल! मैं **{criteria_desc}** के लिए विकल्प देख रही हूँ{range_hint}। "
                        f"आपका अनुमानित बजट (preferred budget) कितना है?"
                    )
                return (
                    f"Great! I'll look for **{criteria_desc}** options for you{range_hint}. "
                    f"What is your preferred budget?"
                )

            matches = rag_service.search_properties_by_criteria(
                location=profile.preferred_location,
                property_type=profile.property_type,
                bedrooms=profile.bedrooms,
                max_budget=profile.budget_max,
                top_k=3,
            )
            if matches:
                if context is not None:
                    context.recommended_property_names = [m["property_name"] for m in matches]
                prop_lines = "\n\n".join(_format_property_bullet(m) for m in matches)

                missing_prompts = []
                if not profile.name:
                    missing_prompts.append("your name")
                if not profile.purchase_timeline:
                    missing_prompts.append("your purchase timeline")
                if not (profile.phone or profile.email):
                    missing_prompts.append("your preferred contact number or email")

                if missing_prompts:
                    follow_up = f"To tailor this better, could you share **{' and '.join(missing_prompts[:2])}**? "
                else:
                    follow_up = ""

                visit_prompt = (
                    f"Would you like to schedule a site visit for **{matches[0]['property_name']}**?"
                    if not (context and context.booked_appointment_id)
                    else "Your site visit is already scheduled!"
                )
                if context and context.language == "hi":
                    return (
                        f"आपकी पसंद ({profile.bedrooms or ''} BHK {profile.property_type or ''}, "
                        f"{profile.preferred_location or 'Punjab'}, बजट {lq.format_budget(profile.budget_max)}) "
                        f"के अनुसार ये बेहतरीन विकल्प उपलब्ध हैं:\n\n{prop_lines}\n\n"
                        f"क्या आप इनमें से किसी प्रॉपर्टी की साइट विज़िट (site visit) बुक करना चाहेंगे?"
                    )
                return (
                    f"Based on your preferences ({profile.bedrooms or ''} BHK {profile.property_type or 'property'} "
                    f"in {profile.preferred_location or 'Punjab'} within {lq.format_budget(profile.budget_max)}), "
                    f"here are matching DreamHome Realty listings:\n\n"
                    f"{prop_lines}\n\n{follow_up}{visit_prompt}"
                )
            elif profile.preferred_location or profile.budget_max:
                return (
                    f"I checked our current demonstration portfolio for "
                    f"{profile.bedrooms or ''} BHK {profile.property_type or 'properties'} "
                    f"in {profile.preferred_location or 'Punjab'}"
                    + (f" within {lq.format_budget(profile.budget_max)}" if profile.budget_max else "")
                    + ", and no exact match is currently listed. Would you like to adjust your budget or explore nearby cities like Phagwara, Jalandhar, or Ludhiana?"
                )

        # Fallback when no criteria matched
        if any(w in msg_lower for w in ["price", "cost", "budget", "lakh", "crore"]):
            return (
                "In our demonstration portfolio, prices range from:\n"
                "• 1 BHK Apartments: ₹19 Lakh – ₹22 Lakh\n"
                "• 2 BHK Apartments: ₹35 Lakh – ₹62 Lakh\n"
                "• 3 BHK Apartments: ₹41 Lakh – ₹98 Lakh\n"
                "• Independent Houses & Villas: ₹82 Lakh – ₹1.80 Crore\n\n"
                "Which city and budget range would you prefer?"
            )

        # Follow up only on missing information
        missing = []
        if not profile.preferred_location:
            missing.append("preferred city (Phagwara, Jalandhar, Ludhiana, Nawanshahr, or Adampur)")
        if not profile.budget_max:
            missing.append("budget")
        if not profile.property_type and not profile.bedrooms:
            missing.append("property type / BHK")
        if missing:
            return (
                f"Thank you! Could you please tell me your **{', '.join(missing)}** "
                f"so I can suggest the best matching properties for you?"
            )

        return (
            "Thank you for sharing those details! Would you like to schedule a site visit "
            "or ask any questions about amenities, payment options, or office hours?"
        )

    def _build_profile_context(self, profile: CustomerProfile) -> str:
        """Build a profile summary string for AI context injection."""
        parts = ["[KNOWN CUSTOMER INFO - Do NOT ask again for this information:]"]
        if profile.name:
            parts.append(f"Name: {profile.name}")
        if profile.budget_max:
            parts.append(f"Budget: up to {lq.format_budget(profile.budget_max)}")
        if profile.preferred_location:
            parts.append(f"Location: {profile.preferred_location}")
        if profile.property_type:
            parts.append(f"Property type: {profile.property_type}")
        if profile.bedrooms:
            parts.append(f"Bedrooms: {profile.bedrooms} BHK")
        if profile.purchase_timeline:
            parts.append(f"Timeline: {profile.purchase_timeline}")
        if profile.phone:
            parts.append(f"Phone: {profile.phone}")
        if profile.email:
            parts.append(f"Email: {profile.email}")
        if len(parts) == 1:
            return ""
        return "\n".join(parts)

    def extract_structured_profile(self, conversation_text: str) -> Dict[str, Any]:
        """
        Extract structured customer profile using Gemini structured JSON output
        when live AI is active, otherwise falls back to rule-based extraction.
        """
        if not self.is_live_ai_available():
            messages = [type("M", (), {"role": "user", "content": conversation_text})()]
            return conv_manager.extract_profile_from_messages(messages).model_dump()

        try:
            from google.genai import types
            prompt = (
                "Extract any customer real estate requirements explicitly stated in this conversation. "
                "Use null for unknown fields. Never invent phone numbers, names, or budgets.\n\n"
                f"Conversation:\n{conversation_text[:3000]}"
            )
            response = self._client.models.generate_content(
                model=self._active_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedCustomerInfo,
                    temperature=0.0,
                ),
            )
            if response and response.text:
                parsed = ExtractedCustomerInfo.model_validate_json(response.text)
                return parsed.model_dump()
        except Exception as e:
            logger.warning(f"Structured profile extraction fallback triggered: {e}")

        messages = [type("M", (), {"role": "user", "content": conversation_text})()]
        return conv_manager.extract_profile_from_messages(messages).model_dump()

    def generate_structured_summary(self, conversation_text: str) -> Optional[Dict[str, Any]]:
        """Generate structured call summary using Gemini JSON schema when active."""
        if not self.is_live_ai_available():
            return None
        try:
            from google.genai import types
            prompt = (
                "Summarize this DreamHome Realty customer conversation accurately based ONLY "
                "on what was actually discussed.\n\n"
                f"Conversation:\n{conversation_text[:4000]}"
            )
            response = self._client.models.generate_content(
                model=self._active_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeneratedCallSummary,
                    temperature=0.2,
                ),
            )
            if response and response.text:
                parsed = GeneratedCallSummary.model_validate_json(response.text)
                return parsed.model_dump()
        except Exception as e:
            logger.warning(f"Structured summary generation failed: {e}")
        return None


_agent_instance: Optional[AIAgent] = None


def get_agent(model_name: Optional[str] = None) -> AIAgent:
    """Get or create the AI agent singleton."""
    global _agent_instance
    if _agent_instance is None or (model_name and model_name != _agent_instance._active_model):
        _agent_instance = AIAgent(model_name=model_name)
    return _agent_instance


def process_customer_message(
    user_message: str,
    context: ConversationContext,
    model_name: Optional[str] = None,
    selected_language: Optional[str] = None,
) -> Tuple[str, ConversationContext]:
    """
    Main entry point for processing a customer message.
    Respects explicit selected_language ('en'/'hi') or auto-detects when 'auto'/None.
    Stores retrieved RAG sources and response metadata on context.__dict__ for UI display.
    Returns (ai_response, updated_context).
    """
    agent = get_agent(model_name=model_name)

    if selected_language in ("en", "hi"):
        detected_lang = selected_language
    else:
        detected_lang = conv_manager.detect_language(user_message, hint=None)
    context.language = detected_lang
    db_conv_id = context.__dict__.get("_db_id")
    if db_conv_id:
        try:
            from backend import database as _db
            _db.update_conversation_language(db_conv_id, detected_lang)
        except Exception:
            pass

    # Retrieve relevant documents via RAG
    retrieved_docs: List[str] = []
    retrieved_sources: List[Dict[str, Any]] = []
    try:
        docs, metas = rag_service.retrieve_relevant_docs(user_message)
        retrieved_docs = docs
        retrieved_sources = metas
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")

    history = conv_manager.get_conversation_history_for_ai(context)

    response, updated_profile, meta = agent.generate_response(
        user_message=user_message,
        conversation_history=history,
        customer_profile=context.customer_profile,
        retrieved_docs=retrieved_docs,
        context=context,
    )

    context = conv_manager.add_message_to_session(context, "user", user_message, language=detected_lang)
    context = conv_manager.add_message_to_session(context, "assistant", response, language=detected_lang)
    context.customer_profile = updated_profile

    meta["sources"] = retrieved_sources
    meta["retrieved_snippets"] = retrieved_docs[:4]
    context.__dict__["_last_response_meta"] = meta

    return response, context
