"""
backend/crm_service.py - CRM business logic layer
Orchestrates customer and lead management operations without creating duplicates.
"""
import logging
from typing import Optional, Dict, Any, List

from backend import database as db
from backend.models import CustomerProfile, LeadQualification

logger = logging.getLogger(__name__)


def upsert_customer_from_profile(
    profile: CustomerProfile,
    conversation_id: int = None,
    existing_customer_id: int = None,
) -> int:
    """
    Create or update a customer based on extracted profile.
    Reuses existing_customer_id if provided, or matches by phone/email.
    Returns customer_id.
    """
    customer_id = existing_customer_id

    if not customer_id and profile.phone:
        existing = db.find_customer_by_phone(profile.phone)
        if existing:
            customer_id = existing["id"]

    if not customer_id and profile.email:
        existing = db.find_customer_by_email(profile.email)
        if existing:
            customer_id = existing["id"]

    customer_data = {
        "name": profile.name or "Unknown",
        "phone": profile.phone,
        "email": profile.email,
        "budget_min": profile.budget_min,
        "budget_max": profile.budget_max,
        "preferred_location": profile.preferred_location,
        "property_type": profile.property_type,
        "bedrooms": profile.bedrooms,
        "purchase_timeline": profile.purchase_timeline,
        "specific_requirements": profile.specific_requirements,
        "furnishing_preference": profile.furnishing_preference,
        "is_nri": profile.is_nri,
        "loan_required": profile.loan_required,
    }

    if customer_id:
        db.update_customer(customer_id, customer_data)
        logger.info(f"Updated customer {customer_id}")
    else:
        customer_id = db.create_customer(customer_data)
        logger.info(f"Created customer {customer_id}")

    if conversation_id:
        db.update_conversation_customer(conversation_id, customer_id)

    return customer_id


def upsert_lead_from_qualification(
    customer_id: int,
    qualification: LeadQualification,
) -> int:
    """Create or update a lead for a customer."""
    lead_data = {
        "lead_score": qualification.lead_score,
        "lead_status": qualification.lead_status.value,
        "sentiment": qualification.sentiment.value,
        "score_budget": qualification.score_budget,
        "score_location": qualification.score_location,
        "score_property_type": qualification.score_property_type,
        "score_timeline": qualification.score_timeline,
        "score_contact": qualification.score_contact,
        "score_interest": qualification.score_interest,
        "recommended_action": qualification.recommended_action,
        "recommended_properties": qualification.recommended_properties,
    }

    leads = db.list_leads(limit=500)
    existing_lead = next(
        (l for l in leads if l["customer_id"] == customer_id), None
    )

    if existing_lead:
        db.update_lead(existing_lead["id"], lead_data)
        return existing_lead["id"]
    return db.create_lead(customer_id, lead_data)


def save_conversation_message(
    conversation_db_id: int,
    role: str,
    content: str,
    language: str = "en",
) -> int:
    """Save a conversation message."""
    return db.add_message(conversation_db_id, role, content, language)


def get_customer_summary(customer_id: int) -> Optional[Dict]:
    """Get full customer summary with lead, conversation, and appointment info."""
    customer = db.get_customer(customer_id)
    if not customer:
        return None

    leads = db.list_leads(limit=500)
    customer_leads = [l for l in leads if l["customer_id"] == customer_id]

    appointments = db.list_appointments(limit=500)
    customer_appointments = [a for a in appointments if a["customer_id"] == customer_id]

    conversations = db.list_conversations(limit=50, customer_id=customer_id)
    for conv in conversations:
        conv["messages"] = db.get_conversation_messages(conv["id"])

    return {
        "customer": customer,
        "leads": customer_leads,
        "appointments": customer_appointments,
        "conversations": conversations,
        "lead_count": len(customer_leads),
        "appointment_count": len(customer_appointments),
    }


def search_customers(query: str) -> List[Dict]:
    """Search customers by name, phone, email, or location."""
    return db.list_customers(search=query)
