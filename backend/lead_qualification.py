"""
backend/lead_qualification.py - Lead scoring and qualification engine
Implements transparent, configurable lead scoring.
"""
import logging
import re
from typing import Optional

from backend.models import CustomerProfile, LeadQualification, LeadStatus, SentimentType
import config

logger = logging.getLogger(__name__)

# Qualification thresholds
QUALIFIED_THRESHOLD = 75
HOT_THRESHOLD = 50
WARM_THRESHOLD = 30


def score_lead(profile: CustomerProfile) -> LeadQualification:
    """
    Score a lead based on the customer profile.
    
    Scoring criteria:
    - Budget provided: 20 points
    - Location preference provided: 20 points
    - Property type provided: 15 points
    - Purchase timeline provided: 20 points
    - Contact information provided: 15 points
    - Clear purchase interest: 10 points (inferred from other criteria)
    Total: 100 points
    """
    score_budget = 0
    score_location = 0
    score_property_type = 0
    score_timeline = 0
    score_contact = 0
    score_interest = 0
    
    # Budget scoring
    if profile.budget_max and profile.budget_max > 0:
        score_budget = config.LEAD_SCORE_BUDGET  # 20
        if profile.budget_min and profile.budget_min > 0:
            score_budget = min(config.LEAD_SCORE_BUDGET, score_budget)  # Already max
    
    # Location scoring
    if profile.preferred_location and len(profile.preferred_location.strip()) > 1:
        score_location = config.LEAD_SCORE_LOCATION  # 20
    
    # Property type scoring
    if profile.property_type and profile.property_type.lower() not in ["any", "", "none"]:
        score_property_type = config.LEAD_SCORE_PROPERTY_TYPE  # 15
    elif profile.bedrooms and profile.bedrooms > 0:
        score_property_type = int(config.LEAD_SCORE_PROPERTY_TYPE * 0.5)  # Partial credit
    
    # Timeline scoring
    if profile.purchase_timeline and len(profile.purchase_timeline.strip()) > 2:
        timeline_lower = profile.purchase_timeline.lower()
        if any(word in timeline_lower for word in ["immediate", "asap", "1 month", "month", "week", "urgent"]):
            score_timeline = config.LEAD_SCORE_TIMELINE  # 20 - urgent
        elif any(word in timeline_lower for word in ["3 month", "quarter", "2 month"]):
            score_timeline = int(config.LEAD_SCORE_TIMELINE * 0.85)  # 17 - near-term
        elif any(word in timeline_lower for word in ["6 month", "half year"]):
            score_timeline = int(config.LEAD_SCORE_TIMELINE * 0.7)  # 14 - mid-term
        elif any(word in timeline_lower for word in ["year", "flexible", "whenever"]):
            score_timeline = int(config.LEAD_SCORE_TIMELINE * 0.5)  # 10 - long-term
        else:
            score_timeline = int(config.LEAD_SCORE_TIMELINE * 0.5)  # 10 - provided but vague
    
    # Contact scoring
    has_phone = profile.phone and len(str(profile.phone).strip()) > 5
    has_email = profile.email and "@" in str(profile.email)
    if has_phone and has_email:
        score_contact = config.LEAD_SCORE_CONTACT  # 15
    elif has_phone or has_email:
        score_contact = int(config.LEAD_SCORE_CONTACT * 0.7)  # 10 - partial
    
    # Interest scoring: award if at least 3 key criteria are present
    criteria_count = sum([
        1 if score_budget > 0 else 0,
        1 if score_location > 0 else 0,
        1 if score_property_type > 0 else 0,
        1 if score_timeline > 0 else 0,
    ])
    if criteria_count >= 3:
        score_interest = config.LEAD_SCORE_INTEREST  # 10
    elif criteria_count >= 2:
        score_interest = int(config.LEAD_SCORE_INTEREST * 0.5)  # 5
    
    total_score = score_budget + score_location + score_property_type + score_timeline + score_contact + score_interest
    total_score = min(100, max(0, total_score))
    
    # Determine lead status
    if total_score >= QUALIFIED_THRESHOLD:
        lead_status = LeadStatus.QUALIFIED
    elif total_score >= HOT_THRESHOLD:
        lead_status = LeadStatus.HOT
    elif total_score >= WARM_THRESHOLD:
        lead_status = LeadStatus.WARM
    elif total_score > 0:
        lead_status = LeadStatus.COLD
    else:
        lead_status = LeadStatus.NEW
    
    # Determine recommended action
    recommended_action = _get_recommended_action(lead_status, profile, total_score)
    
    return LeadQualification(
        lead_score=total_score,
        lead_status=lead_status,
        sentiment=SentimentType.NEUTRAL,
        score_budget=score_budget,
        score_location=score_location,
        score_property_type=score_property_type,
        score_timeline=score_timeline,
        score_contact=score_contact,
        score_interest=score_interest,
        recommended_action=recommended_action,
    )


def _get_recommended_action(status: LeadStatus, profile: CustomerProfile, score: int) -> str:
    """Determine the next recommended action based on lead status."""
    if status == LeadStatus.QUALIFIED:
        if profile.phone or profile.email:
            return "Schedule property visit immediately. High-intent buyer."
        return "Collect contact information and schedule property visit."
    elif status == LeadStatus.HOT:
        missing = []
        if not profile.phone and not profile.email:
            missing.append("contact details")
        if not profile.purchase_timeline:
            missing.append("purchase timeline")
        return f"Follow up urgently. Collect: {', '.join(missing) or 'appointment confirmation'}."
    elif status == LeadStatus.WARM:
        missing = []
        if not profile.budget_max:
            missing.append("budget")
        if not profile.preferred_location:
            missing.append("location preference")
        if not profile.property_type:
            missing.append("property type")
        return f"Nurture lead. Missing info: {', '.join(missing)}."
    elif status == LeadStatus.COLD:
        return "Send property catalog. Schedule follow-up call in 1 week."
    else:
        return "Gather basic requirements: budget, location, and property type."


def analyze_sentiment(conversation_text: str) -> SentimentType:
    """
    Basic rule-based sentiment analysis from conversation text.
    Returns positive, negative, neutral, or mixed.
    """
    text_lower = conversation_text.lower()
    
    positive_words = [
        "interested", "good", "great", "excellent", "perfect", "love", "like",
        "yes", "definitely", "sure", "looking forward", "excited", "happy",
        "wonderful", "amazing", "want to", "would like", "ready", "confirm",
        "please book", "schedule", "visit", "suits", "affordable", "reasonable"
    ]
    
    negative_words = [
        "expensive", "costly", "not interested", "no", "don't like", "problem",
        "issue", "bad", "poor", "terrible", "disappointed", "unhappy", "wrong",
        "cancel", "not suitable", "overpriced", "too much", "can't afford"
    ]
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > 0 and negative_count > 0:
        return SentimentType.MIXED
    elif positive_count > negative_count:
        return SentimentType.POSITIVE
    elif negative_count > positive_count:
        return SentimentType.NEGATIVE
    else:
        return SentimentType.NEUTRAL


def extract_budget_from_text(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Extract budget range from free text.
    Returns (budget_min, budget_max) in INR.
    """
    # Remove commas & normalize spoken number words for voice transcripts
    text_clean = text.replace(",", "").lower()
    word_numbers = {
        "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
        "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
        "पचास": "50", "चालीस": "40", "साठ": "60", "लाख": "lakh", "करोड़": "crore",
    }
    for word, digit in word_numbers.items():
        text_clean = text_clean.replace(word, digit)
    text_lower = text_clean
    
    budget_min = None
    budget_max = None
    
    # Crore patterns
    crore_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(?:crore|crores|cr\b)",
        r"(\d+(?:\.\d+)?)\s*(?:crore|crores|cr\b)",
        r"budget\s*(?:of|is|around)?\s*(\d+(?:\.\d+)?)\s*(?:crore|crores|cr\b)",
    ]

    # Lakh patterns
    lakh_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l\b)",
        r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs)\b",
        r"(\d+(?:\.\d+)?)\s*l\b",
        r"budget\s*(?:of|is|around)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l\b)",
        r"within\s*(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l\b)",
        r"under\s*(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l\b)",
    ]
    
    for pattern in crore_patterns:
        m = re.search(pattern, text_lower)
        if m:
            groups = m.groups()
            if len(groups) == 2 and groups[1]:
                budget_min = int(float(groups[0]) * 10_000_000)
                budget_max = int(float(groups[1]) * 10_000_000)
            else:
                budget_max = int(float(groups[0]) * 10_000_000)
            return budget_min, budget_max
    
    for pattern in lakh_patterns:
        m = re.search(pattern, text_clean.lower())
        if m:
            groups = m.groups()
            if len(groups) == 2 and groups[1]:
                budget_min = int(float(groups[0]) * 100_000)
                budget_max = int(float(groups[1]) * 100_000)
            else:
                budget_max = int(float(groups[0]) * 100_000)
            return budget_min, budget_max
    
    return None, None


def format_budget(amount: int) -> str:
    """Format amount in Indian number system."""
    if amount >= 10_000_000:
        return f"₹{amount/10_000_000:.2f} Crore"
    elif amount >= 100_000:
        return f"₹{amount/100_000:.1f} Lakh"
    return f"₹{amount:,}"
