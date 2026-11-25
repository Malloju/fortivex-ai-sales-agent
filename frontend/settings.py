"""
frontend/settings.py - Modern SaaS Settings & Configuration Page
Never exposes secret API key values. Allows configuring session voice/AI preferences.
"""
import os
import streamlit as st
import config
from backend import rag_service, speech_to_text as stt, text_to_speech as tts
from frontend import styles


def show():
    """Render the Settings page."""
    styles.render_page_header(
        title="Settings & System Status",
        subtitle="Inspect AI, speech-to-text, text-to-speech, and database configuration. Secret API keys are never shown.",
        badge_text="Demo Mode" if config.IS_DEMO_MODE else "Production",
        badge_variant="blue" if config.IS_DEMO_MODE else "green",
    )

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.subheader("AI & Gemini Configuration")
        api_configured = bool(config.GEMINI_API_KEY.strip())
        st.markdown(f"""
        <div class="dh-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.45rem;">
                <span style="color:#475569;">Operating Mode</span>
                <b>{'Demo Mode (Deterministic)' if config.IS_DEMO_MODE else 'Live Gemini AI'}</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.45rem;">
                <span style="color:#475569;">API Key Status</span>
                <b>{'Configured (hidden)' if api_configured else 'Not configured'}</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.45rem;">
                <span style="color:#475569;">Primary Model</span>
                <code>{config.GEMINI_MODEL}</code>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#475569;">History Limit</span>
                <b>{config.CONVERSATION_HISTORY_LIMIT} messages</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

        current_model = st.session_state.get("selected_gemini_model", config.GEMINI_MODEL)
        model_choices = list(dict.fromkeys([current_model] + config.SUPPORTED_GEMINI_MODELS))
        st.session_state.selected_gemini_model = st.selectbox(
            "Active Gemini Model (current session)",
            model_choices,
            index=model_choices.index(current_model),
        )

        if not api_configured:
            st.info(
                "To enable live Gemini AI: copy `.env.example` to `.env`, set `GEMINI_API_KEY` "
                "(from Google AI Studio) and `APP_MODE=production`, then restart the app."
            )

    with col2:
        st.subheader("Voice Pipeline (STT & TTS)")
        stt_status = stt.get_stt_status()
        tts_status = tts.get_tts_status()

        st.markdown(f"""
        <div class="dh-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.45rem;">
                <span style="color:#475569;">Faster-Whisper STT</span>
                <b>{'Ready (CPU int8)' if stt_status['whisper_available'] else 'Not installed'}</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.45rem;">
                <span style="color:#475569;">Audio Decoder</span>
                <b>{'PyAV + Stdlib Wave' if stt_status['pyav_available'] else 'Stdlib Wave'}</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.45rem;">
                <span style="color:#475569;">FFmpeg Binary</span>
                <b>{'Installed' if stt_status['ffmpeg_available'] else 'Optional (PyAV active)'}</b>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#475569;">Edge TTS Output</span>
                <b>{'Available' if tts_status['edge_tts_available'] else 'Not installed'}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

        whisper_sizes = ["tiny", "base", "small", "medium"]
        cur_w = st.session_state.get("selected_whisper_model", config.WHISPER_MODEL)
        if cur_w not in whisper_sizes:
            whisper_sizes.insert(0, cur_w)
        st.session_state.selected_whisper_model = st.selectbox(
            "Whisper Model Size (session)",
            whisper_sizes,
            index=whisper_sizes.index(cur_w),
        )

        st.session_state.auto_voice_response = st.toggle(
            "🔊 Automatic voice response",
            value=st.session_state.get("auto_voice_response", True),
            help="Automatically generate and play spoken audio after each AI response.",
        )

        langs = ["auto", "en", "hi"]
        cur_lang = st.session_state.get("selected_language", config.DEFAULT_LANGUAGE)
        if cur_lang not in langs:
            cur_lang = "auto"
        st.session_state.selected_language = st.selectbox(
            "Default Speech / Conversation Language",
            langs,
            index=langs.index(cur_lang),
            format_func=lambda x: {"auto": "Auto-Detect (EN / HI)", "en": "English", "hi": "Hindi"}[x],
        )

        v1, v2 = st.columns(2)
        with v1:
            en_voices = ["en-IN-NeerjaNeural", "en-IN-PrabhatNeural"]
            cur_en = st.session_state.get("tts_voice_en", config.TTS_VOICE_EN)
            if cur_en not in en_voices:
                en_voices.insert(0, cur_en)
            st.session_state.tts_voice_en = st.selectbox("English TTS Voice", en_voices, index=en_voices.index(cur_en))
        with v2:
            hi_voices = ["hi-IN-SwaraNeural", "hi-IN-MadhurNeural"]
            cur_hi = st.session_state.get("tts_voice_hi", config.TTS_VOICE_HI)
            if cur_hi not in hi_voices:
                hi_voices.insert(0, cur_hi)
            st.session_state.tts_voice_hi = st.selectbox("Hindi TTS Voice", hi_voices, index=hi_voices.index(cur_hi))

    st.markdown("---")

    c3, c4 = st.columns(2, gap="large")
    with c3:
        st.subheader("Storage & RAG Index")
        kb_stats = rag_service.get_knowledge_base_stats()
        db_size_kb = os.path.getsize(config.DATABASE_PATH) / 1024 if config.DATABASE_PATH.exists() else 0.0
        st.markdown(f"""
        <div class="dh-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                <span style="color:#475569;">SQLite CRM Database</span>
                <b>{db_size_kb:.1f} KB</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                <span style="color:#475569;">Knowledge Chunks</span>
                <b>{kb_stats.get('knowledge_chunks', 0)}</b>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#475569;">Property Documents</span>
                <b>{kb_stats.get('property_documents', 0)}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.subheader("Lead Scoring & Office Hours")
        st.markdown(f"""
        <div class="dh-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                <span style="color:#475569;">Business Hours</span>
                <b>{config.BUSINESS_HOURS_START}:00 – {config.BUSINESS_HOURS_END}:00 ({config.TIMEZONE})</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:0.4rem;">
                <span style="color:#475569;">Slot Duration</span>
                <b>{config.APPOINTMENT_DURATION_MINUTES} minutes</b>
            </div>
            <div style="font-size:0.83rem; color:#475569; margin-top:0.5rem;">
                Scoring: Budget {config.LEAD_SCORE_BUDGET} + Location {config.LEAD_SCORE_LOCATION} +
                Type {config.LEAD_SCORE_PROPERTY_TYPE} + Timeline {config.LEAD_SCORE_TIMELINE} +
                Contact {config.LEAD_SCORE_CONTACT} + Interest {config.LEAD_SCORE_INTEREST} = <b>100 pts</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
