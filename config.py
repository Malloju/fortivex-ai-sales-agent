"""
config.py - Centralized configuration management for FortivexAI Sales Agent
Loads from environment variables with sensible defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# --- Base paths ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
AUDIO_DIR = BASE_DIR / "audio_temp"
ASSETS_DIR = BASE_DIR / "assets"
DOCS_DIR = BASE_DIR / "docs"

# Ensure directories exist
for _dir in [DATA_DIR, LOGS_DIR, AUDIO_DIR, ASSETS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


def _resolve_path(env_val: str, default_rel: str) -> Path:
    raw = Path(env_val) if env_val else Path(default_rel)
    return raw if raw.is_absolute() else (BASE_DIR / raw)


# --- Gemini AI ---
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
SUPPORTED_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

# --- Application mode ---
APP_MODE: str = os.getenv("APP_MODE", "demo").lower()
IS_DEMO_MODE: bool = APP_MODE == "demo" or not GEMINI_API_KEY.strip()

# --- Database ---
DATABASE_PATH: Path = _resolve_path(os.getenv("DATABASE_PATH", ""), "data/dreamhome.db")

# --- ChromaDB ---
CHROMA_PATH: str = str(_resolve_path(os.getenv("CHROMA_PATH", ""), "chroma_db"))

# --- Whisper (Speech-to-Text) ---
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")

# --- Language ---
DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")

# --- Conversation ---
CONVERSATION_HISTORY_LIMIT: int = int(os.getenv("CONVERSATION_HISTORY_LIMIT", "20"))

# --- Timezone ---
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")

# --- Logging ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Path = _resolve_path(os.getenv("LOG_FILE", ""), "logs/app.log")

# --- Appointment Settings ---
BUSINESS_HOURS_START: int = int(os.getenv("BUSINESS_HOURS_START", "9"))
BUSINESS_HOURS_END: int = int(os.getenv("BUSINESS_HOURS_END", "18"))
APPOINTMENT_DURATION_MINUTES: int = int(os.getenv("APPOINTMENT_DURATION_MINUTES", "60"))

# --- TTS Voices ---
TTS_VOICE_EN: str = os.getenv("TTS_VOICE_EN", "en-IN-NeerjaNeural")
TTS_VOICE_HI: str = os.getenv("TTS_VOICE_HI", "hi-IN-SwaraNeural")

# --- RAG Settings ---
RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))

# --- Lead Scoring Criteria ---
LEAD_SCORE_BUDGET: int = int(os.getenv("SCORE_BUDGET", "20"))
LEAD_SCORE_LOCATION: int = int(os.getenv("SCORE_LOCATION", "20"))
LEAD_SCORE_PROPERTY_TYPE: int = int(os.getenv("SCORE_PROPERTY_TYPE", "15"))
LEAD_SCORE_TIMELINE: int = int(os.getenv("SCORE_TIMELINE", "20"))
LEAD_SCORE_CONTACT: int = int(os.getenv("SCORE_CONTACT", "15"))
LEAD_SCORE_INTEREST: int = int(os.getenv("SCORE_INTEREST", "10"))

# --- Company Info ---
COMPANY_NAME: str = "DreamHome Realty"
COMPANY_TAGLINE: str = "Your Dream Home, Our Promise"
APP_TITLE: str = "FortivexAI - AI Sales Voice Agent"

# --- Data files ---
PROPERTIES_CSV: Path = DATA_DIR / "properties.csv"
KNOWLEDGE_TXT: Path = DATA_DIR / "company_knowledge.txt"
SAMPLE_CUSTOMERS_CSV: Path = DATA_DIR / "sample_customers.csv"

# --- ChromaDB collection names ---
CHROMA_COLLECTION_KNOWLEDGE: str = "dreamhome_knowledge"
CHROMA_COLLECTION_PROPERTIES: str = "dreamhome_properties"


def get_config_summary() -> dict:
    """Return a sanitized config summary (no secrets)."""
    return {
        "app_mode": APP_MODE,
        "is_demo_mode": IS_DEMO_MODE,
        "gemini_model": GEMINI_MODEL,
        "gemini_fallback_model": GEMINI_FALLBACK_MODEL,
        "gemini_api_configured": bool(GEMINI_API_KEY.strip()),
        "whisper_model": WHISPER_MODEL,
        "default_language": DEFAULT_LANGUAGE,
        "conversation_history_limit": CONVERSATION_HISTORY_LIMIT,
        "timezone": TIMEZONE,
        "database_path": str(DATABASE_PATH),
        "chroma_path": CHROMA_PATH,
        "rag_chunk_size": RAG_CHUNK_SIZE,
        "rag_top_k": RAG_TOP_K,
        "tts_voice_en": TTS_VOICE_EN,
        "tts_voice_hi": TTS_VOICE_HI,
        "business_hours": f"{BUSINESS_HOURS_START}:00 - {BUSINESS_HOURS_END}:00",
    }
