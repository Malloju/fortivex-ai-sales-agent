"""
backend/summary_service.py - Call summary generation
Generates structured summaries after conversations (using Gemini structured output when active,
with deterministic summary generation as fallback).
"""
import logging
from typing import Dict, Any, List, Optional

from backend.models import CustomerProfile, LeadQualification
from backend import database as db
from backend import lead_qualification as lq

logger = logging.getLogger(__name__)


def generate_summary(
    conversation_id: int,
    conversation_uuid: str,
    customer_id: Optional[int],
    lead_id: Optional[int],
    messages: List[Dict],
    profile: CustomerProfile,
    qualification: LeadQualification,
    appointment_id: Optional[int] = None,
    use_ai: bool = True,
) -> Dict[str, Any]:
    """
    Generate a structured call summary from conversation data and persist to SQLite.
    """
    full_conversation = "\n".join(
        f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}"
        for m in messages
        if m.get("content")
    )

    key_points = _extract_key_points(profile, qualification, appointment_id)
    requirements = _build_requirements_text(profile)

    budget_text = ""
    if profile.budget_max:
        budget_text = lq.format_budget(profile.budget_max)
        if profile.budget_min:
            budget_text = f"{lq.format_budget(profile.budget_min)} - {budget_text}"

    parts = []
    if profile.bedrooms:
        parts.append(f"{profile.bedrooms} BHK")
    if profile.property_type and profile.property_type.lower() != "any":
        parts.append(profile.property_type)
    if profile.preferred_location:
        parts.append(f"in {profile.preferred_location}")
    preferred_property = " ".join(parts) if parts else "Not specified"

    sentiment = lq.analyze_sentiment(full_conversation)
    summary_text = _build_summary_text(
        profile, qualification, budget_text, preferred_property, appointment_id
    )
    next_action = qualification.recommended_action or "Follow up with customer."
    if appointment_id:
        next_action = f"Appointment booked (ID: {appointment_id}). Send confirmation and prepare property details."

    # Enhance with Gemini structured summary if active
    if use_ai and full_conversation.strip():
        try:
            from backend import ai_agent
            agent = ai_agent.get_agent()
            ai_summary = agent.generate_structured_summary(full_conversation)
            if ai_summary:
                summary_text = ai_summary.get("summary_text") or summary_text
                requirements = ai_summary.get("customer_requirements") or requirements
                budget_text = ai_summary.get("budget_discussed") or budget_text
                preferred_property = ai_summary.get("preferred_property") or preferred_property
                if ai_summary.get("sentiment") in ("positive", "neutral", "negative", "mixed"):
                    sentiment_val = ai_summary["sentiment"]
                else:
                    sentiment_val = sentiment.value
                next_action = ai_summary.get("next_action") or next_action
                if ai_summary.get("key_points"):
                    key_points = ai_summary["key_points"]
                sentiment = type("S", (), {"value": sentiment_val})()
        except Exception as e:
            logger.warning(f"Structured AI summary skipped: {e}")

    summary_data = {
        "conversation_id": conversation_id,
        "conversation_uuid": conversation_uuid,
        "customer_id": customer_id,
        "lead_id": lead_id,
        "summary_text": summary_text,
        "customer_requirements": requirements,
        "budget_discussed": budget_text or "Not specified",
        "preferred_property": preferred_property,
        "sentiment": sentiment.value,
        "lead_score": qualification.lead_score,
        "lead_status": qualification.lead_status.value,
        "appointment_booked": appointment_id is not None,
        "appointment_id": appointment_id,
        "next_action": next_action,
        "key_points": key_points,
    }

    try:
        summary_id = db.save_call_summary(summary_data)
        logger.info(f"Saved call summary ID {summary_id}")
        summary_data["summary_id"] = summary_id
    except Exception as e:
        logger.error(f"Failed to save summary: {e}")

    return summary_data


def _extract_key_points(
    profile: CustomerProfile,
    qualification: LeadQualification,
    appointment_id: Optional[int],
) -> List[str]:
    """Extract key talking points from the conversation."""
    points = []
    if profile.name:
        points.append(f"Customer name: {profile.name}")
    if profile.budget_max:
        points.append(f"Budget: up to {lq.format_budget(profile.budget_max)}")
    if profile.preferred_location:
        points.append(f"Preferred location: {profile.preferred_location}")
    if profile.property_type:
        bhk_prefix = f"{profile.bedrooms} BHK " if profile.bedrooms else ""
        points.append(f"Property type: {bhk_prefix}{profile.property_type}")
    if profile.purchase_timeline:
        points.append(f"Timeline: {profile.purchase_timeline}")
    if profile.phone or profile.email:
        contact = profile.phone or profile.email
        points.append(f"Contact: {contact}")
    if appointment_id:
        points.append(f"Appointment booked (ID: {appointment_id})")
    points.append(f"Lead score: {qualification.lead_score}/100 ({qualification.lead_status.value.upper()})")
    return points


def _build_requirements_text(profile: CustomerProfile) -> str:
    """Build a human-readable requirements summary."""
    parts = []
    if profile.bedrooms:
        parts.append(f"{profile.bedrooms} BHK")
    if profile.property_type and profile.property_type.lower() != "any":
        parts.append(profile.property_type)
    if profile.preferred_location:
        parts.append(f"in {profile.preferred_location}")
    if profile.furnishing_preference:
        parts.append(f"({profile.furnishing_preference})")
    if profile.specific_requirements:
        parts.append(f"- {profile.specific_requirements}")
    return " ".join(parts) if parts else "Requirements not fully specified."


def _build_summary_text(
    profile: CustomerProfile,
    qualification: LeadQualification,
    budget_text: str,
    preferred_property: str,
    appointment_id: Optional[int],
) -> str:
    """Build a natural language summary of the conversation."""
    name = profile.name or "the customer"
    summary_parts = [f"Conversation summary for {name}."]

    if preferred_property and preferred_property != "Not specified":
        summary_parts.append(f"Customer is looking for a {preferred_property}.")
    if budget_text:
        summary_parts.append(f"Budget: {budget_text}.")
    if profile.purchase_timeline:
        summary_parts.append(f"Purchase timeline: {profile.purchase_timeline}.")
    if profile.loan_required:
        summary_parts.append("Customer expressed interest in home loan assistance.")
    if appointment_id:
        summary_parts.append(f"Site visit appointment scheduled (ID: {appointment_id}).")

    summary_parts.append(
        f"Lead score: {qualification.lead_score}/100. Status: {qualification.lead_status.value.upper()}."
    )
    summary_parts.append(f"Recommended action: {qualification.recommended_action}")

    return " ".join(summary_parts)
