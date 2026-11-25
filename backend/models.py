"""
backend/models.py - Pydantic models for FortivexAI Sales Agent
Defines data structures for validation and serialization (Pydantic v2).
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator
from enum import Enum


class LeadStatus(str, Enum):
    NEW = "new"
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class PropertyType(str, Enum):
    APARTMENT = "Apartment"
    INDEPENDENT_HOUSE = "Independent House"
    VILLA = "Villa"
    ANY = "Any"


class AppointmentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class SentimentType(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class CustomerProfile(BaseModel):
    """Extracted customer profile from conversation."""
    name: Optional[str] = Field(None, description="Customer's full name")
    phone: Optional[str] = Field(None, description="Customer's phone number")
    email: Optional[str] = Field(None, description="Customer's email address")
    budget_min: Optional[int] = Field(None, description="Minimum budget in INR")
    budget_max: Optional[int] = Field(None, description="Maximum budget in INR")
    preferred_location: Optional[str] = Field(None, description="Preferred city or area")
    property_type: Optional[str] = Field(None, description="Type of property wanted")
    bedrooms: Optional[int] = Field(None, description="Number of bedrooms required")
    bathrooms: Optional[int] = Field(None, description="Number of bathrooms required")
    purchase_timeline: Optional[str] = Field(None, description="When they plan to purchase")
    specific_requirements: Optional[str] = Field(None, description="Special requirements")
    furnishing_preference: Optional[str] = Field(None, description="Furnishing preference")
    is_nri: Optional[bool] = Field(False, description="Is the customer an NRI")
    loan_required: Optional[bool] = Field(None, description="Does customer need home loan")


class ExtractedCustomerInfo(BaseModel):
    """Structured AI output schema for extracting customer details."""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    preferred_location: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    purchase_timeline: Optional[str] = None
    specific_requirements: Optional[str] = None
    furnishing_preference: Optional[str] = None
    is_nri: Optional[bool] = None
    loan_required: Optional[bool] = None
    sentiment: SentimentType = SentimentType.NEUTRAL


class GeneratedCallSummary(BaseModel):
    """Structured AI output schema for call summary generation."""
    summary_text: str
    customer_requirements: Optional[str] = None
    budget_discussed: Optional[str] = None
    preferred_property: Optional[str] = None
    sentiment: SentimentType = SentimentType.NEUTRAL
    next_action: str = "Follow up with customer."
    key_points: List[str] = Field(default_factory=list)


class LeadQualification(BaseModel):
    """Lead qualification result with scoring."""
    lead_score: int = Field(0, ge=0, le=100, description="Lead score 0-100")
    lead_status: LeadStatus = Field(LeadStatus.NEW, description="Lead qualification status")
    sentiment: SentimentType = Field(SentimentType.NEUTRAL, description="Customer sentiment")

    # Score breakdown
    score_budget: int = Field(0, description="Points for budget information")
    score_location: int = Field(0, description="Points for location preference")
    score_property_type: int = Field(0, description="Points for property type")
    score_timeline: int = Field(0, description="Points for purchase timeline")
    score_contact: int = Field(0, description="Points for contact information")
    score_interest: int = Field(0, description="Points for clear purchase interest")

    # Recommendations
    recommended_action: str = Field("", description="Next recommended action")
    recommended_properties: List[str] = Field(default_factory=list, description="Suggested property IDs")

    @model_validator(mode="after")
    def sync_status_with_score(self) -> "LeadQualification":
        """Ensure lead_status accurately reflects lead_score unless already converted/lost."""
        if self.lead_status in (LeadStatus.CONVERTED, LeadStatus.LOST):
            return self
        if self.lead_score >= 75:
            self.lead_status = LeadStatus.QUALIFIED
        elif self.lead_score >= 50:
            self.lead_status = LeadStatus.HOT
        elif self.lead_score >= 30:
            self.lead_status = LeadStatus.WARM
        elif self.lead_score > 0:
            self.lead_status = LeadStatus.COLD
        else:
            self.lead_status = LeadStatus.NEW
        return self


class CallSummary(BaseModel):
    """Summary generated after a conversation."""
    conversation_id: str
    summary_text: str
    customer_requirements: Optional[str] = None
    budget_discussed: Optional[str] = None
    preferred_property: Optional[str] = None
    sentiment: SentimentType = SentimentType.NEUTRAL
    lead_score: int = 0
    lead_status: LeadStatus = LeadStatus.NEW
    appointment_booked: bool = False
    appointment_id: Optional[int] = None
    next_action: str = ""
    key_points: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class AppointmentRequest(BaseModel):
    """Appointment booking request."""
    customer_name: str
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    property_id: Optional[str] = None
    property_name: Optional[str] = None
    preferred_date: str  # YYYY-MM-DD format
    preferred_time: str  # HH:MM format
    notes: Optional[str] = None


class AppointmentSlot(BaseModel):
    """An available appointment slot."""
    date: str
    time: str
    datetime_str: str
    is_available: bool = True


class Message(BaseModel):
    """A single conversation message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    language: str = "en"


class ConversationContext(BaseModel):
    """Full conversation context with extracted information."""
    conversation_id: str
    session_id: str
    messages: List[Message] = Field(default_factory=list)
    customer_profile: CustomerProfile = Field(default_factory=CustomerProfile)
    lead_qualification: Optional[LeadQualification] = None
    language: str = "en"
    is_active: bool = True
    recommended_property_names: List[str] = Field(default_factory=list)
    pending_appointment_date: Optional[str] = None
    pending_appointment_time: Optional[str] = None
    pending_property_name: Optional[str] = None
    awaiting_appointment_confirmation: bool = False
    booked_appointment_id: Optional[int] = None
    booked_confirmation_code: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Property(BaseModel):
    """Property information model."""
    property_id: str
    property_name: str
    property_type: str
    location: str
    price_inr: int
    bedrooms: int
    bathrooms: int
    area_sqft: int
    furnishing: str
    amenities: str
    possession_status: str
    description: str
    contact_information: str

    @property
    def price_formatted(self) -> str:
        """Format price in Indian number system."""
        price = self.price_inr
        if price >= 10_000_000:
            return f"₹{price/10_000_000:.2f} Crore"
        elif price >= 100_000:
            return f"₹{price/100_000:.1f} Lakh"
        else:
            return f"₹{price:,}"
