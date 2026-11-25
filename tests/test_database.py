"""
tests/test_database.py - Tests for database operations
"""
import pytest
import tempfile
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    import config
    temp_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "DATABASE_PATH", temp_db)
    
    from backend import database as db
    db.init_database()
    yield db


def test_database_initialization(use_temp_db):
    """Test that database initializes with all tables."""
    db = use_temp_db
    with db.get_db_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t["name"] for t in tables]
    
    assert "customers" in table_names
    assert "leads" in table_names
    assert "conversations" in table_names
    assert "conversation_messages" in table_names
    assert "appointments" in table_names
    assert "call_summaries" in table_names


def test_create_customer(use_temp_db):
    """Test customer creation."""
    db = use_temp_db
    customer_data = {
        "name": "Test Customer",
        "phone": "+91-99999-11111",
        "email": "test@example.com",
        "budget_max": 5000000,
        "preferred_location": "Phagwara",
        "property_type": "Apartment",
        "bedrooms": 2,
    }
    
    customer_id = db.create_customer(customer_data)
    assert customer_id > 0
    
    retrieved = db.get_customer(customer_id)
    assert retrieved is not None
    assert retrieved["name"] == "Test Customer"
    assert retrieved["phone"] == "+91-99999-11111"
    assert retrieved["budget_max"] == 5000000


def test_find_customer_by_phone(use_temp_db):
    """Test customer lookup by phone."""
    db = use_temp_db
    db.create_customer({"name": "Priya Test", "phone": "+91-88888-00000"})
    
    result = db.find_customer_by_phone("+91-88888-00000")
    assert result is not None
    assert result["name"] == "Priya Test"


def test_update_customer(use_temp_db):
    """Test customer update."""
    db = use_temp_db
    cid = db.create_customer({"name": "Old Name", "phone": "+91-77777-00000"})
    db.update_customer(cid, {"name": "New Name", "budget_max": 7000000})
    
    updated = db.get_customer(cid)
    assert updated["name"] == "New Name"


def test_create_lead(use_temp_db):
    """Test lead creation linked to customer."""
    db = use_temp_db
    cid = db.create_customer({"name": "Lead Customer"})
    
    lead_data = {
        "lead_score": 65,
        "lead_status": "hot",
        "sentiment": "positive",
        "score_budget": 20,
        "score_location": 20,
        "score_property_type": 15,
        "score_timeline": 10,
        "score_contact": 0,
        "score_interest": 0,
        "recommended_action": "Schedule visit",
        "recommended_properties": [],
    }
    
    lead_id = db.create_lead(cid, lead_data)
    assert lead_id > 0
    
    leads = db.list_leads()
    assert any(l["id"] == lead_id for l in leads)


def test_create_conversation_and_messages(use_temp_db):
    """Test conversation and message persistence."""
    db = use_temp_db
    conv_id = db.create_conversation("test-uuid-123", "session-abc")
    assert conv_id > 0
    
    db.add_message(conv_id, "user", "Hello, I need a 2BHK")
    db.add_message(conv_id, "assistant", "Great! Let me help you.")
    
    messages = db.get_conversation_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_dashboard_metrics(use_temp_db):
    """Test dashboard metrics calculation."""
    db = use_temp_db
    
    # Create some test data
    cid = db.create_customer({"name": "Metrics Test"})
    db.create_lead(cid, {"lead_score": 80, "lead_status": "qualified", "sentiment": "positive"})
    
    metrics = db.get_dashboard_metrics()
    
    assert "total_conversations" in metrics
    assert "total_customers" in metrics
    assert "total_leads" in metrics
    assert "qualified_leads" in metrics
    assert "total_appointments" in metrics
    assert metrics["total_customers"] >= 1
    assert metrics["qualified_leads"] >= 1
