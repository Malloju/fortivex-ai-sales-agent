"""
backend/database.py - SQLite database management for DreamHome Realty CRM
Handles schema creation, CRUD operations, and all persistence needs.
"""
import json
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

import config

logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """Context manager for safe database connections."""
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Initialize the database with all required tables."""
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        conn.executescript("""
            -- Customers table
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                budget_min INTEGER,
                budget_max INTEGER,
                preferred_location TEXT,
                property_type TEXT,
                bedrooms INTEGER,
                purchase_timeline TEXT,
                specific_requirements TEXT,
                furnishing_preference TEXT,
                is_nri INTEGER DEFAULT 0,
                loan_required INTEGER,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
            CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);

            -- Leads table
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                lead_score INTEGER DEFAULT 0,
                lead_status TEXT DEFAULT 'new',
                sentiment TEXT DEFAULT 'neutral',
                score_budget INTEGER DEFAULT 0,
                score_location INTEGER DEFAULT 0,
                score_property_type INTEGER DEFAULT 0,
                score_timeline INTEGER DEFAULT 0,
                score_contact INTEGER DEFAULT 0,
                score_interest INTEGER DEFAULT 0,
                recommended_action TEXT,
                recommended_properties TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_leads_customer ON leads(customer_id);
            CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(lead_status);

            -- Conversations table
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_uuid TEXT UNIQUE NOT NULL,
                customer_id INTEGER,
                session_id TEXT,
                language TEXT DEFAULT 'en',
                is_active INTEGER DEFAULT 1,
                total_messages INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_conversations_uuid ON conversations(conversation_uuid);
            CREATE INDEX IF NOT EXISTS idx_conversations_customer ON conversations(customer_id);

            -- Conversation messages table
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(conversation_id);

            -- Appointments table
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                lead_id INTEGER,
                conversation_id INTEGER,
                property_id TEXT,
                property_name TEXT,
                appointment_date TEXT NOT NULL,
                appointment_time TEXT NOT NULL,
                appointment_datetime TEXT NOT NULL,
                duration_minutes INTEGER DEFAULT 60,
                status TEXT DEFAULT 'confirmed',
                notes TEXT,
                confirmation_code TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );

            CREATE INDEX IF NOT EXISTS idx_appointments_datetime ON appointments(appointment_datetime);
            CREATE INDEX IF NOT EXISTS idx_appointments_customer ON appointments(customer_id);
            CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_no_double_book
                ON appointments(appointment_datetime, status)
                WHERE status NOT IN ('cancelled', 'rescheduled');

            -- Call summaries table
            CREATE TABLE IF NOT EXISTS call_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                conversation_uuid TEXT,
                customer_id INTEGER,
                lead_id INTEGER,
                summary_text TEXT,
                customer_requirements TEXT,
                budget_discussed TEXT,
                preferred_property TEXT,
                sentiment TEXT DEFAULT 'neutral',
                lead_score INTEGER DEFAULT 0,
                lead_status TEXT DEFAULT 'new',
                appointment_booked INTEGER DEFAULT 0,
                appointment_id INTEGER,
                next_action TEXT,
                key_points TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_summaries_conversation ON call_summaries(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_summaries_customer ON call_summaries(customer_id);
        """)

    logger.info(f"Database initialized at {config.DATABASE_PATH}")


# ============================================================
# CUSTOMER CRUD
# ============================================================

def create_customer(customer_data: Dict[str, Any]) -> int:
    """Create a new customer record. Returns customer ID."""
    loan_val = customer_data.get("loan_required")
    loan_db = None if loan_val is None else (1 if loan_val else 0)
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO customers (name, phone, email, budget_min, budget_max,
                preferred_location, property_type, bedrooms, purchase_timeline,
                specific_requirements, furnishing_preference, is_nri, loan_required, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            customer_data.get("name") or "Unknown",
            customer_data.get("phone"),
            customer_data.get("email"),
            customer_data.get("budget_min"),
            customer_data.get("budget_max"),
            customer_data.get("preferred_location"),
            customer_data.get("property_type"),
            customer_data.get("bedrooms"),
            customer_data.get("purchase_timeline"),
            customer_data.get("specific_requirements"),
            customer_data.get("furnishing_preference"),
            1 if customer_data.get("is_nri") else 0,
            loan_db,
            customer_data.get("notes"),
        ))
        customer_id = cursor.lastrowid
        logger.info(f"Created customer ID {customer_id}: {customer_data.get('name')}")
        return customer_id


def update_customer(customer_id: int, customer_data: Dict[str, Any]) -> bool:
    """Update existing customer record."""
    name_val = customer_data.get("name")
    if name_val == "Unknown":
        name_val = None  # Never overwrite a real name with Unknown

    is_nri_val = customer_data.get("is_nri")
    is_nri_db = None if is_nri_val is None else (1 if is_nri_val else 0)

    loan_val = customer_data.get("loan_required")
    loan_db = None if loan_val is None else (1 if loan_val else 0)

    with get_db_connection() as conn:
        conn.execute("""
            UPDATE customers SET
                name = COALESCE(?, name),
                phone = COALESCE(?, phone),
                email = COALESCE(?, email),
                budget_min = COALESCE(?, budget_min),
                budget_max = COALESCE(?, budget_max),
                preferred_location = COALESCE(?, preferred_location),
                property_type = COALESCE(?, property_type),
                bedrooms = COALESCE(?, bedrooms),
                purchase_timeline = COALESCE(?, purchase_timeline),
                specific_requirements = COALESCE(?, specific_requirements),
                furnishing_preference = COALESCE(?, furnishing_preference),
                is_nri = COALESCE(?, is_nri),
                loan_required = COALESCE(?, loan_required),
                notes = COALESCE(?, notes),
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (
            name_val,
            customer_data.get("phone"),
            customer_data.get("email"),
            customer_data.get("budget_min"),
            customer_data.get("budget_max"),
            customer_data.get("preferred_location"),
            customer_data.get("property_type"),
            customer_data.get("bedrooms"),
            customer_data.get("purchase_timeline"),
            customer_data.get("specific_requirements"),
            customer_data.get("furnishing_preference"),
            is_nri_db,
            loan_db,
            customer_data.get("notes"),
            customer_id,
        ))
        return True


def get_customer(customer_id: int) -> Optional[Dict]:
    """Fetch a customer by ID."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None


def find_customer_by_phone(phone: str) -> Optional[Dict]:
    """Find a customer by phone number."""
    if not phone:
        return None
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE phone = ?", (phone,)
        ).fetchone()
        return dict(row) if row else None


def find_customer_by_email(email: str) -> Optional[Dict]:
    """Find a customer by email."""
    if not email:
        return None
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None


def list_customers(limit: int = 100, search: str = "") -> List[Dict]:
    """List all customers with optional search."""
    with get_db_connection() as conn:
        if search:
            rows = conn.execute("""
                SELECT * FROM customers
                WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? OR preferred_location LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM customers ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# LEAD CRUD
# ============================================================

def create_lead(customer_id: int, lead_data: Dict[str, Any]) -> int:
    """Create a new lead record."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO leads (customer_id, lead_score, lead_status, sentiment,
                score_budget, score_location, score_property_type, score_timeline,
                score_contact, score_interest, recommended_action, recommended_properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            customer_id,
            lead_data.get("lead_score", 0),
            lead_data.get("lead_status", "new"),
            lead_data.get("sentiment", "neutral"),
            lead_data.get("score_budget", 0),
            lead_data.get("score_location", 0),
            lead_data.get("score_property_type", 0),
            lead_data.get("score_timeline", 0),
            lead_data.get("score_contact", 0),
            lead_data.get("score_interest", 0),
            lead_data.get("recommended_action", ""),
            json.dumps(lead_data.get("recommended_properties", [])),
        ))
        lead_id = cursor.lastrowid
        logger.info(f"Created lead ID {lead_id} for customer {customer_id}")
        return lead_id


def update_lead(lead_id: int, lead_data: Dict[str, Any]) -> bool:
    """Update an existing lead including full score breakdown."""
    rec_props = lead_data.get("recommended_properties")
    rec_props_json = json.dumps(rec_props) if rec_props is not None else None
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE leads SET
                lead_score = COALESCE(?, lead_score),
                lead_status = COALESCE(?, lead_status),
                sentiment = COALESCE(?, sentiment),
                score_budget = COALESCE(?, score_budget),
                score_location = COALESCE(?, score_location),
                score_property_type = COALESCE(?, score_property_type),
                score_timeline = COALESCE(?, score_timeline),
                score_contact = COALESCE(?, score_contact),
                score_interest = COALESCE(?, score_interest),
                recommended_action = COALESCE(?, recommended_action),
                recommended_properties = COALESCE(?, recommended_properties),
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (
            lead_data.get("lead_score"),
            lead_data.get("lead_status"),
            lead_data.get("sentiment"),
            lead_data.get("score_budget"),
            lead_data.get("score_location"),
            lead_data.get("score_property_type"),
            lead_data.get("score_timeline"),
            lead_data.get("score_contact"),
            lead_data.get("score_interest"),
            lead_data.get("recommended_action"),
            rec_props_json,
            lead_id,
        ))
        return True


def list_leads(limit: int = 100) -> List[Dict]:
    """List all leads with customer info."""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT l.*, c.name as customer_name, c.phone as customer_phone,
                   c.preferred_location, c.budget_max, c.property_type, c.bedrooms
            FROM leads l
            LEFT JOIN customers c ON l.customer_id = c.id
            ORDER BY l.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# CONVERSATION CRUD
# ============================================================

def create_conversation(uuid: str, session_id: str = "", language: str = "en") -> int:
    """Create a new conversation record."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO conversations (conversation_uuid, session_id, language)
            VALUES (?, ?, ?)
        """, (uuid, session_id, language))
        return cursor.lastrowid


def update_conversation_customer(conversation_id: int, customer_id: int) -> None:
    """Associate a conversation with a customer."""
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE conversations SET customer_id = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (customer_id, conversation_id))


def update_conversation_language(conversation_id: int, language: str) -> None:
    """Update detected conversation language."""
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE conversations SET language = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (language, conversation_id))


def add_message(conversation_id: int, role: str, content: str, language: str = "en") -> int:
    """Add a message to a conversation."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO conversation_messages (conversation_id, role, content, language)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, role, content, language))
        conn.execute("""
            UPDATE conversations SET
                total_messages = total_messages + 1,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (conversation_id,))
        return cursor.lastrowid


def get_conversation_messages(conversation_id: int) -> List[Dict]:
    """Get all messages for a conversation."""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM conversation_messages WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conversation_id,)).fetchall()
        return [dict(r) for r in rows]


def list_conversations(limit: int = 50, customer_id: Optional[int] = None) -> List[Dict]:
    """List recent conversations, optionally filtered by customer."""
    with get_db_connection() as conn:
        if customer_id is not None:
            rows = conn.execute("""
                SELECT c.*, cu.name as customer_name
                FROM conversations c
                LEFT JOIN customers cu ON c.customer_id = cu.id
                WHERE c.customer_id = ?
                ORDER BY c.created_at DESC LIMIT ?
            """, (customer_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT c.*, cu.name as customer_name
                FROM conversations c
                LEFT JOIN customers cu ON c.customer_id = cu.id
                ORDER BY c.created_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# APPOINTMENT CRUD
# ============================================================

def create_appointment(appt_data: Dict[str, Any]) -> int:
    """Create a new appointment."""
    import random, string
    code = "DH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO appointments (customer_id, lead_id, conversation_id, property_id,
                property_name, appointment_date, appointment_time, appointment_datetime,
                duration_minutes, status, notes, confirmation_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            appt_data["customer_id"],
            appt_data.get("lead_id"),
            appt_data.get("conversation_id"),
            appt_data.get("property_id"),
            appt_data.get("property_name"),
            appt_data["appointment_date"],
            appt_data["appointment_time"],
            appt_data["appointment_datetime"],
            appt_data.get("duration_minutes", 60),
            "confirmed",
            appt_data.get("notes"),
            code,
        ))
        appt_id = cursor.lastrowid
        logger.info(f"Created appointment ID {appt_id}: {code}")
        return appt_id


def check_slot_availability(appointment_datetime: str) -> bool:
    """Check if a slot is available (no conflicts)."""
    with get_db_connection() as conn:
        count = conn.execute("""
            SELECT COUNT(*) FROM appointments
            WHERE appointment_datetime = ?
            AND status NOT IN ('cancelled', 'rescheduled')
        """, (appointment_datetime,)).fetchone()[0]
        return count == 0


def cancel_appointment(appointment_id: int) -> bool:
    """Cancel an appointment."""
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE appointments SET status = 'cancelled',
            updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (appointment_id,))
        return True


def list_appointments(status: str = None, limit: int = 50) -> List[Dict]:
    """List appointments with customer info."""
    with get_db_connection() as conn:
        if status:
            rows = conn.execute("""
                SELECT a.*, c.name as customer_name, c.phone as customer_phone, c.email as customer_email
                FROM appointments a
                LEFT JOIN customers c ON a.customer_id = c.id
                WHERE a.status = ?
                ORDER BY a.appointment_datetime ASC LIMIT ?
            """, (status, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT a.*, c.name as customer_name, c.phone as customer_phone, c.email as customer_email
                FROM appointments a
                LEFT JOIN customers c ON a.customer_id = c.id
                ORDER BY a.appointment_datetime DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# CALL SUMMARY CRUD
# ============================================================

def save_call_summary(summary_data: Dict[str, Any]) -> int:
    """Save a call summary."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO call_summaries (conversation_id, conversation_uuid, customer_id,
                lead_id, summary_text, customer_requirements, budget_discussed,
                preferred_property, sentiment, lead_score, lead_status,
                appointment_booked, appointment_id, next_action, key_points)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            summary_data.get("conversation_id"),
            summary_data.get("conversation_uuid"),
            summary_data.get("customer_id"),
            summary_data.get("lead_id"),
            summary_data.get("summary_text"),
            summary_data.get("customer_requirements"),
            summary_data.get("budget_discussed"),
            summary_data.get("preferred_property"),
            summary_data.get("sentiment", "neutral"),
            summary_data.get("lead_score", 0),
            summary_data.get("lead_status", "new"),
            1 if summary_data.get("appointment_booked") else 0,
            summary_data.get("appointment_id"),
            summary_data.get("next_action"),
            json.dumps(summary_data.get("key_points", [])),
        ))
        return cursor.lastrowid


def list_call_summaries(limit: int = 50) -> List[Dict]:
    """List call summaries with customer info."""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT cs.*, c.name as customer_name
            FROM call_summaries cs
            LEFT JOIN customers c ON cs.customer_id = c.id
            ORDER BY cs.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# ANALYTICS / DASHBOARD METRICS
# ============================================================

def get_dashboard_metrics() -> Dict[str, Any]:
    """Get metrics for the dashboard from actual data."""
    with get_db_connection() as conn:
        total_conversations = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        qualified_leads = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_status IN ('qualified', 'hot')"
        ).fetchone()[0]
        total_appointments = conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE status = 'confirmed'"
        ).fetchone()[0]

        # Lead status breakdown for conversion chart
        status_rows = conn.execute("""
            SELECT lead_status, COUNT(*) as count FROM leads
            GROUP BY lead_status
        """).fetchall()
        lead_status_dist = {r["lead_status"]: r["count"] for r in status_rows}

        # Sentiment distribution
        sentiment_rows = conn.execute("""
            SELECT sentiment, COUNT(*) as count FROM call_summaries
            GROUP BY sentiment
        """).fetchall()
        sentiment_dist = {r["sentiment"]: r["count"] for r in sentiment_rows}

        # Location preferences
        location_rows = conn.execute("""
            SELECT preferred_location, COUNT(*) as count FROM customers
            WHERE preferred_location IS NOT NULL AND preferred_location != ''
            GROUP BY preferred_location ORDER BY count DESC LIMIT 5
        """).fetchall()
        top_locations = [dict(r) for r in location_rows]

        # Property type preferences
        ptype_rows = conn.execute("""
            SELECT property_type, COUNT(*) as count FROM customers
            WHERE property_type IS NOT NULL AND property_type != ''
            GROUP BY property_type ORDER BY count DESC
        """).fetchall()
        top_property_types = [dict(r) for r in ptype_rows]

        # Recent activity
        recent_convs = conn.execute("""
            SELECT c.created_at, cu.name as customer_name, c.total_messages
            FROM conversations c
            LEFT JOIN customers cu ON c.customer_id = cu.id
            ORDER BY c.created_at DESC LIMIT 5
        """).fetchall()
        recent_activity = [dict(r) for r in recent_convs]

        conversion_rate = (qualified_leads / total_leads * 100) if total_leads > 0 else 0

        return {
            "total_conversations": total_conversations,
            "total_customers": total_customers,
            "total_leads": total_leads,
            "qualified_leads": qualified_leads,
            "total_appointments": total_appointments,
            "conversion_rate": round(conversion_rate, 1),
            "lead_status_distribution": lead_status_dist,
            "sentiment_distribution": sentiment_dist,
            "top_locations": top_locations,
            "top_property_types": top_property_types,
            "recent_activity": recent_activity,
        }
