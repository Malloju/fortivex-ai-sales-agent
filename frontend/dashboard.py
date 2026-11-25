"""
frontend/dashboard.py - Modern SaaS Home Dashboard for DreamHome AI
Displays real database metrics, welcome overview, primary conversation CTA,
lead conversion chart, recent activity, and quick links to CRM & Appointments.
"""
import pandas as pd
import streamlit as st
from backend import database as db
from frontend import styles
import config


def show():
    """Render the Home Dashboard page."""
    badge = "Demo Mode" if config.IS_DEMO_MODE else f"Live · {config.GEMINI_MODEL}"
    badge_var = "blue" if config.IS_DEMO_MODE else "green"

    styles.render_page_header(
        title=f"{config.COMPANY_NAME} — Overview",
        subtitle="AI-powered residential sales voice assistant, lead qualification, and appointment scheduling.",
        badge_text=badge,
        badge_variant=badge_var,
    )

    # Welcome & primary action card
    st.markdown("""
    <div class="dh-hero">
        <div style="font-size:1.05rem; font-weight:700; color:#0F172A; margin-bottom:0.3rem;">
            Welcome to the DreamHome AI Sales Assistant
        </div>
        <div style="font-size:0.9rem; color:#475569; max-width:780px; line-height:1.5;">
            Interact with customers via browser voice or text, answer property & policy questions from the
            ChromaDB knowledge base, qualify leads automatically, and book conflict-free site visits in SQLite.
        </div>
    </div>
    """, unsafe_allow_html=True)

    cta1, cta2, cta3, _ = st.columns([2, 1.3, 1.5, 2.2])
    with cta1:
        if st.button("🎙️ Start AI Conversation", type="primary", width="stretch"):
            st.session_state.pending_nav_page = "🎙️ AI Sales Agent"
            st.rerun()
    with cta2:
        if st.button("👥 Open CRM", width="stretch"):
            st.session_state.pending_nav_page = "👥 CRM"
            st.rerun()
    with cta3:
        if st.button("📅 Appointments", width="stretch"):
            st.session_state.pending_nav_page = "📅 Appointments"
            st.rerun()

    st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

    # Summary KPI cards from real database records
    metrics = db.get_dashboard_metrics()
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        styles.render_kpi_card("Total Calls", metrics["total_conversations"], "Recorded conversations")
    with k2:
        styles.render_kpi_card("Total Leads", metrics["total_leads"], f"{metrics['total_customers']} customer profiles")
    with k3:
        styles.render_kpi_card(
            "Qualified Leads",
            metrics["qualified_leads"],
            f"{metrics['conversion_rate']}% qualification rate",
        )
    with k4:
        styles.render_kpi_card("Appointments", metrics["total_appointments"], "Confirmed site visits")

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        st.subheader("Lead Conversion Pipeline")
        status_dist = metrics.get("lead_status_distribution", {})
        if status_dist:
            ordered_stages = ["new", "cold", "warm", "hot", "qualified", "converted"]
            stage_rows = [
                {"Stage": stage.title(), "Leads": status_dist.get(stage, 0)}
                for stage in ordered_stages
                if status_dist.get(stage, 0) > 0 or stage in ("cold", "warm", "hot", "qualified")
            ]
            conv_df = pd.DataFrame(stage_rows).set_index("Stage")
            st.bar_chart(conv_df, color="#4F46E5")
        else:
            styles.render_empty_state(
                "No lead pipeline data yet",
                "Start a conversation on the AI Sales Agent page to qualify your first lead.",
            )

        st.subheader("Recent Customer Activity")
        recent = metrics.get("recent_activity", [])
        if recent:
            activity_data = [
                {
                    "Date / Time": str(a.get("created_at", ""))[:16],
                    "Customer": a.get("customer_name") or "Prospect",
                    "Messages": a.get("total_messages", 0),
                }
                for a in recent
            ]
            st.dataframe(pd.DataFrame(activity_data), width="stretch", hide_index=True)
        else:
            styles.render_empty_state(
                "No recent activity",
                "Conversations and CRM updates will appear here automatically.",
            )

    with col_right:
        st.subheader("Top Requested Locations")
        top_locs = metrics.get("top_locations", [])
        if top_locs:
            loc_df = pd.DataFrame(top_locs)[["preferred_location", "count"]]
            loc_df.columns = ["Location", "Inquiries"]
            st.bar_chart(loc_df.set_index("Location"), color="#2563EB")
        else:
            styles.render_empty_state(
                "No location preferences yet",
                "Location trends appear as customers discuss target cities.",
            )

        st.subheader("System Readiness")
        from backend import rag_service, speech_to_text, text_to_speech

        kb_ok = rag_service.is_knowledge_base_indexed()
        stt_ok = speech_to_text.is_whisper_available()
        tts_ok = text_to_speech.is_tts_available()
        ai_pill = (
            '<span class="dh-pill dh-pill-blue">Demo Mode</span>'
            if config.IS_DEMO_MODE
            else f'<span class="dh-pill dh-pill-green">{config.GEMINI_MODEL}</span>'
        )
        kb_pill = '<span class="dh-pill dh-pill-green">Indexed</span>' if kb_ok else '<span class="dh-pill dh-pill-amber">Pending</span>'
        stt_pill = f'<span class="dh-pill dh-pill-green">Whisper ({config.WHISPER_MODEL})</span>' if stt_ok else '<span class="dh-pill dh-pill-slate">Unavailable</span>'
        tts_pill = '<span class="dh-pill dh-pill-green">Edge TTS Ready</span>' if tts_ok else '<span class="dh-pill dh-pill-slate">Disabled</span>'

        st.markdown(f"""
        <div class="dh-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.55rem;">
                <span style="color:#475569; font-size:0.88rem;">AI Conversation Engine</span>{ai_pill}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.55rem;">
                <span style="color:#475569; font-size:0.88rem;">RAG Knowledge Store</span>{kb_pill}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.55rem;">
                <span style="color:#475569; font-size:0.88rem;">Speech-to-Text (STT)</span>{stt_pill}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#475569; font-size:0.88rem;">Voice Synthesis (TTS)</span>{tts_pill}
            </div>
        </div>
        """, unsafe_allow_html=True)
