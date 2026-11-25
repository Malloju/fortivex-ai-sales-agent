"""
app.py - Main Streamlit application entry point for FortivexAI Sales Agent
DreamHome Realty — Autonomous AI Sales Voice Agent
"""
import logging
import sys
import streamlit as st

st.set_page_config(
    page_title="DreamHome AI | Sales Voice Agent",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "FortivexAI Sales Agent - DreamHome Realty Demo",
    },
)

import config
from frontend import styles

config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(config.LOG_FILE), mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@st.cache_resource
def initialize_app():
    """Initialize database and knowledge base on first run."""
    logger.info("Initializing FortivexAI Sales Agent...")
    try:
        from backend import database as db
        db.init_database()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    try:
        from backend import rag_service
        if not rag_service.is_knowledge_base_indexed():
            rag_service.index_knowledge_base()
    except Exception as e:
        logger.warning(f"Knowledge base indexing skipped: {e}")
    return True


initialize_app()
styles.inject_global_styles()

NAV_OPTIONS = [
    "🏠 Home Dashboard",
    "🎙️ AI Voice Assistance",
    "👥 CRM",
    "📅 Appointments",
    "🔍 Knowledge Base",
    "📊 Business Insights",
    "⚙️ Settings",
]

if "nav_page" not in st.session_state or st.session_state.nav_page not in NAV_OPTIONS:
    st.session_state.nav_page = NAV_OPTIONS[0]

# Handle programmatic navigation requests safely before instantiating sidebar radio
if "pending_nav_page" in st.session_state:
    target = st.session_state.pop("pending_nav_page")
    if target == "🎙️ AI Sales Agent":
        target = "🎙️ AI Voice Assistance"
    if target in NAV_OPTIONS:
        st.session_state.nav_page = target

# ---- Compact Light SaaS Sidebar ----
with st.sidebar:
    mode_badge = (
        '<span class="dh-pill dh-pill-blue">Demo Mode</span>'
        if config.IS_DEMO_MODE
        else '<span class="dh-pill dh-pill-green">Gemini AI</span>'
    )
    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between;
                padding:0.25rem 0 0.75rem 0; border-bottom:1px solid #E2E8F0; margin-bottom:0.65rem;">
        <div style="display:flex; align-items:center; gap:0.5rem;">
            <div style="width:30px; height:30px; border-radius:8px; background:#4F46E5;
                        color:#FFFFFF; display:flex; align-items:center; justify-content:center;
                        font-weight:700; font-size:0.95rem;">DH</div>
            <div>
                <div style="font-weight:700; font-size:0.95rem; color:#0F172A; line-height:1.1;">DreamHome AI</div>
                <div style="font-size:0.72rem; color:#64748B;">Sales Voice Agent</div>
            </div>
        </div>
        {mode_badge}
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        NAV_OPTIONS,
        key="nav_page",
        label_visibility="collapsed",
    )

    try:
        from backend import database as db
        metrics = db.get_dashboard_metrics()
        st.markdown(f"""
        <div style="margin-top:1rem; padding:0.7rem 0.75rem; background:#F8FAFC;
                    border:1px solid #E2E8F0; border-radius:8px; font-size:0.78rem;">
            <div style="font-weight:600; color:#64748B; text-transform:uppercase;
                        letter-spacing:0.04em; margin-bottom:0.45rem; font-size:0.7rem;">
                Live CRM Snapshot
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.2rem;">
                <span style="color:#475569;">Calls</span>
                <span style="font-weight:700; color:#0F172A;">{metrics['total_conversations']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.2rem;">
                <span style="color:#475569;">Leads</span>
                <span style="font-weight:700; color:#0F172A;">{metrics['total_leads']}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#475569;">Qualified</span>
                <span style="font-weight:700; color:#4F46E5;">{metrics['qualified_leads']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown("""
    <div style="margin-top:0.85rem; font-size:0.7rem; color:#94A3B8; text-align:center;">
        FortivexAI Round 3 · Demo Data Only
    </div>
    """, unsafe_allow_html=True)

# ---- Page Routing ----
try:
    if page == "🏠 Home Dashboard":
        from frontend import dashboard
        dashboard.show()
    elif page == "🎙️ AI Voice Assistance":
        from frontend import sales_agent
        sales_agent.show()
    elif page == "👥 CRM":
        from frontend import crm
        crm.show()
    elif page == "📅 Appointments":
        from frontend import appointments
        appointments.show()
    elif page == "🔍 Knowledge Base":
        from frontend import knowledge_base
        knowledge_base.show()
    elif page == "📊 Business Insights":
        from frontend import business_insights
        business_insights.show()
    elif page == "⚙️ Settings":
        from frontend import settings
        settings.show()
except Exception as e:
    logger.error(f"Page rendering error: {e}", exc_info=True)
    st.error("Unable to render this page right now. Please check logs/app.log for details.")
