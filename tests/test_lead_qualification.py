"""
tests/test_lead_qualification.py - Tests for lead scoring engine
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models import CustomerProfile, LeadStatus, SentimentType, Message
from backend import lead_qualification as lq
from backend import conversation as conv_manager


def test_empty_profile_scores_zero():
    """Empty profile should score 0."""
    profile = CustomerProfile()
    result = lq.score_lead(profile)
    assert result.lead_score == 0
    assert result.lead_status == LeadStatus.NEW


def test_full_profile_scores_high():
    """Complete profile should score >= 90 and be QUALIFIED."""
    profile = CustomerProfile(
        name="Rajesh Kumar",
        phone="+91-98765-00000",
        email="rajesh@example.com",
        budget_max=5000000,
        preferred_location="Phagwara",
        property_type="Apartment",
        bedrooms=2,
        purchase_timeline="2 months",
    )
    result = lq.score_lead(profile)
    assert result.lead_score >= 90
    assert result.lead_status == LeadStatus.QUALIFIED


def test_positive_sentiment_alone_does_not_qualify_lead():
    """Positive sentiment alone must never classify an uninformative customer as qualified."""
    positive_msg = "I love your company! Everything sounds amazing and wonderful!"
    sentiment = lq.analyze_sentiment(positive_msg)
    assert sentiment == SentimentType.POSITIVE

    empty_profile = CustomerProfile()
    result = lq.score_lead(empty_profile)
    result.sentiment = sentiment
    assert result.lead_score == 0
    assert result.lead_status == LeadStatus.NEW


def test_name_extraction_avoids_false_positives():
    """Phrases like 'I am looking for' must not extract 'Looking For' as a name."""
    msgs = [Message(role="user", content="I am looking for a 2 BHK apartment in Phagwara within a budget of 50 lakh.")]
    profile = conv_manager.extract_profile_from_messages(msgs)
    assert profile.name is None
    assert profile.bedrooms == 2
    assert profile.preferred_location == "Phagwara"
    assert profile.property_type == "Apartment"
    assert profile.budget_max == 5_000_000

    # Actual name introduction works cleanly
    msgs.append(Message(role="user", content="My name is Rajesh Kumar and phone is 9876500000"))
    profile2 = conv_manager.extract_profile_from_messages(msgs)
    assert profile2.name == "Rajesh Kumar"
    assert profile2.phone == "+91-98765-00000"


def test_budget_only_gives_budget_score():
    """Only budget provided."""
    profile = CustomerProfile(budget_max=5000000)
    result = lq.score_lead(profile)
    assert result.score_budget > 0
    assert result.score_location == 0
    assert result.score_contact == 0


def test_location_only():
    """Only location provided."""
    profile = CustomerProfile(preferred_location="Ludhiana")
    result = lq.score_lead(profile)
    assert result.score_location > 0
    assert result.score_budget == 0


def test_lead_status_thresholds():
    """Test lead status threshold mapping."""
    profile_hot = CustomerProfile(
        budget_max=5000000,
        preferred_location="Phagwara",
        property_type="Apartment",
        purchase_timeline="3 months",
    )
    result = lq.score_lead(profile_hot)
    assert result.lead_score >= 50
    assert result.lead_status in (LeadStatus.HOT, LeadStatus.QUALIFIED)

    profile_cold = CustomerProfile(budget_max=3000000)
    result_cold = lq.score_lead(profile_cold)
    assert result_cold.lead_status == LeadStatus.COLD


def test_contact_scoring():
    """Contact info should contribute to score."""
    profile_no_contact = CustomerProfile(budget_max=5000000, preferred_location="Phagwara")
    profile_with_contact = CustomerProfile(
        budget_max=5000000, preferred_location="Phagwara", phone="+91-98765-00000"
    )

    result_no = lq.score_lead(profile_no_contact)
    result_with = lq.score_lead(profile_with_contact)

    assert result_with.score_contact > 0
    assert result_with.lead_score > result_no.lead_score


def test_budget_extraction_lakh():
    """Test budget extraction from text."""
    _, max_b = lq.extract_budget_from_text("within 50 lakh")
    assert max_b == 5_000_000

    _, max_b = lq.extract_budget_from_text("budget is 40 lakh")
    assert max_b == 4_000_000


def test_budget_extraction_crore():
    """Test crore budget extraction."""
    _, max_b = lq.extract_budget_from_text("1.5 crore")
    assert max_b == 15_000_000


def test_budget_extraction_range():
    """Test range budget extraction."""
    min_b, max_b = lq.extract_budget_from_text("30 to 50 lakh")
    assert min_b == 3_000_000
    assert max_b == 5_000_000


def test_sentiment_positive():
    """Test positive sentiment detection."""
    text = "Yes, I'm very interested! This looks perfect and I love the amenities."
    assert lq.analyze_sentiment(text) == SentimentType.POSITIVE


def test_sentiment_negative():
    """Test negative sentiment detection."""
    text = "This is too expensive and not suitable for my needs."
    assert lq.analyze_sentiment(text) == SentimentType.NEGATIVE


def test_format_budget():
    """Test budget formatting."""
    assert "Crore" in lq.format_budget(15_000_000)
    assert "Lakh" in lq.format_budget(5_000_000)
    assert "45" in lq.format_budget(4_500_000)


def test_recommended_action_qualified():
    """Qualified lead should get visit action."""
    profile = CustomerProfile(
        name="Test",
        phone="+91-99999-00000",
        budget_max=5000000,
        preferred_location="Phagwara",
        property_type="Apartment",
        purchase_timeline="1 month",
    )
    result = lq.score_lead(profile)
    assert len(result.recommended_action) > 0
