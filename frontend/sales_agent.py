"""
frontend/sales_agent.py - Dedicated Conversational AI Voice Assistance Interface
ChatGPT / Blintii-style centered chat layout with left-aligned AI bubbles,
right-aligned customer bubbles, fixed bottom composer (mic + text + send),
automatic voice playback, and preserved multi-turn context & CRM persistence.
"""
import hashlib
import html
import logging
import time
import uuid
import streamlit as st
import streamlit.components.v1 as components

import config
from backend import ai_agent, conversation as conv_manager
from backend import lead_qualification as lq
from backend import crm_service
from backend import speech_to_text as stt
from backend import text_to_speech as tts
from frontend import voice_player

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Hi! I'm DreamHome AI. I can help you find properties, answer your questions, "
    "and schedule property visits. You can type a message or speak using the microphone."
)


def _inject_chat_styles() -> None:
    """Inject scoped conversational CSS solely for the AI Voice Assistance page."""
    st.markdown("""
    <style>
        /* Centered conversational container */
        .main .block-container {
            max-width: 880px !important;
            padding-top: 1.1rem !important;
            padding-bottom: 6.5rem !important;
        }

        /* Minimal top header bar */
        .dh-chat-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 0.75rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid #E2E8F0;
            gap: 0.75rem;
        }
        .dh-chat-title-wrap {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            flex-wrap: wrap;
        }
        .dh-chat-title {
            font-size: 1.2rem;
            font-weight: 700;
            color: #0F172A;
            margin: 0;
            letter-spacing: -0.01em;
        }
        .dh-ready-dot {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.78rem;
            font-weight: 600;
            color: #047857;
            background: #ECFDF5;
            border: 1px solid #A7F3D0;
            border-radius: 9999px;
            padding: 0.18rem 0.6rem;
        }
        .dh-ready-dot.busy {
            color: #1D4ED8;
            background: #EFF6FF;
            border-color: #BFDBFE;
        }

        /* Welcome card when conversation is empty */
        .dh-welcome-box {
            max-width: 640px;
            margin: 2.5rem auto 1.5rem auto;
            text-align: center;
            padding: 1.75rem 1.5rem;
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 18px;
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        }
        .dh-welcome-badge {
            width: 44px;
            height: 44px;
            margin: 0 auto 0.85rem auto;
            border-radius: 12px;
            background: #4F46E5;
            color: #FFFFFF;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.05rem;
        }

        /* AI responses aligned LEFT */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
            background-color: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 18px 18px 18px 4px !important;
            padding: 0.9rem 1.1rem !important;
            margin-right: auto !important;
            margin-left: 0 !important;
            max-width: 84% !important;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
        }

        /* Customer messages aligned RIGHT */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            flex-direction: row-reverse !important;
            background-color: #4F46E5 !important;
            border: none !important;
            border-radius: 18px 18px 4px 18px !important;
            padding: 0.8rem 1.05rem !important;
            margin-left: auto !important;
            margin-right: 0 !important;
            width: fit-content !important;
            max-width: 76% !important;
            box-shadow: 0 2px 6px rgba(79, 70, 229, 0.16) !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) small {
            color: #FFFFFF !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
            text-align: left;
        }

        /* Fixed bottom composer styling */
        [data-testid="stBottom"] {
            background: linear-gradient(180deg, rgba(248, 250, 252, 0) 0%, #F8FAFC 22%) !important;
            padding-top: 0.65rem !important;
            padding-bottom: 0.75rem !important;
        }
        [data-testid="stBottomBlockContainer"] {
            max-width: 860px !important;
            margin: 0 auto !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        [data-testid="stBottom"] .st-key-dh_composer_bar > div > [data-testid="stHorizontalBlock"] {
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 18px;
            padding: 0.4rem 0.55rem;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
            align-items: center;
            gap: 0.45rem;
        }
        .st-key-dh_composer_bar [data-testid="stHorizontalBlock"]:first-child {
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 18px;
            padding: 0.4rem 0.55rem;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
            align-items: center;
            gap: 0.45rem;
        }
        .st-key-dh_composer_bar [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
            border: none !important;
            padding: 0 !important;
            box-shadow: none !important;
            background: transparent !important;
        }
        [data-testid="stBottom"] [data-testid="stForm"] {
            border: none !important;
            padding: 0 !important;
            background: transparent !important;
        }
        [data-testid="stBottom"] [data-testid="stTextInput"] input {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            font-size: 0.94rem !important;
            padding-left: 0.35rem !important;
        }
        [data-testid="stBottom"] [data-testid="stTextInput"] > div {
            border: none !important;
            background: transparent !important;
        }

        /* Compact, clean microphone pill inside composer */
        [data-testid="stBottom"] [data-testid="stAudioInput"] {
            background: #F1F5F9;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 0.1rem 0.35rem;
            min-height: 40px;
        }
        [data-testid="stBottom"] [data-testid="stAudioInput"]:has(button[aria-label="Stop recording"]) {
            background: #FEF2F2 !important;
            border-color: #EF4444 !important;
        }
        [data-testid="stBottom"] [data-testid="stAudioInput"]:has(button[aria-label="Stop recording"])::after {
            content: "Listening...";
            font-size: 0.76rem;
            font-weight: 700;
            color: #DC2626;
            padding-right: 0.35rem;
        }

        /* Subtle typing bubble */
        .dh-typing-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 16px;
            padding: 0.55rem 0.95rem;
            font-size: 0.86rem;
            color: #475569;
            margin: 0.25rem 0 0.75rem 0;
        }

        @media (max-width: 768px) {
            .main .block-container {
                padding-left: 0.65rem !important;
                padding-right: 0.65rem !important;
            }
            [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
            [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
                max-width: 92% !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)


def _init_session():
    """Initialize conversation, voice input, and TTS playback session state."""
    if "selected_language" not in st.session_state:
        st.session_state.selected_language = config.DEFAULT_LANGUAGE
    if "conv_context" not in st.session_state:
        lang = st.session_state.selected_language
        st.session_state.conv_context = conv_manager.create_session(
            language="en" if lang == "auto" else lang
        )
    if "customer_id" not in st.session_state:
        st.session_state.customer_id = None
    if "lead_id" not in st.session_state:
        st.session_state.lead_id = None
    if "appointment_id" not in st.session_state:
        st.session_state.appointment_id = None
    if "auto_voice_response" not in st.session_state:
        st.session_state.auto_voice_response = True
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "voice_error" not in st.session_state:
        st.session_state.voice_error = ""
    if "processed_audio_hashes" not in st.session_state:
        st.session_state.processed_audio_hashes = set()
    if "last_submitted_text" not in st.session_state:
        st.session_state.last_submitted_text = ""
    if "last_submitted_ts" not in st.session_state:
        st.session_state.last_submitted_ts = 0.0
    if "msg_meta_by_index" not in st.session_state:
        st.session_state.msg_meta_by_index = {}
    if "tts_cache" not in st.session_state:
        st.session_state.tts_cache = {}
    if "tts_errors" not in st.session_state:
        st.session_state.tts_errors = {}
    if "pending_autoplay_idx" not in st.session_state:
        st.session_state.pending_autoplay_idx = None
    if "manual_replay_idx" not in st.session_state:
        st.session_state.manual_replay_idx = None
    if "replay_seq" not in st.session_state:
        st.session_state.replay_seq = 0
    if "played_turn_ids" not in st.session_state:
        st.session_state.played_turn_ids = set()
    if "recorder_nonce" not in st.session_state:
        st.session_state.recorder_nonce = 0
    if "last_scroll_msg_count" not in st.session_state:
        st.session_state.last_scroll_msg_count = 0


def _reset_conversation():
    """Start a fresh conversation while resetting audio/turn caches cleanly."""
    for key in [
        "conv_context", "customer_id", "lead_id", "appointment_id",
        "voice_error", "msg_meta_by_index", "tts_cache", "tts_errors",
        "pending_autoplay_idx", "manual_replay_idx",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.processed_audio_hashes = set()
    st.session_state.played_turn_ids = set()
    st.session_state.last_submitted_text = ""
    st.session_state.last_submitted_ts = 0.0
    st.session_state.is_processing = False
    st.session_state.last_scroll_msg_count = 0
    st.session_state.recorder_nonce = st.session_state.get("recorder_nonce", 0) + 1


def _generate_tts_for_message(msg_idx: int, text: str, language: str) -> bool:
    """Synthesize speech for an AI response and cache bytes for playback & replay."""
    voice_override = (
        st.session_state.get("tts_voice_hi", config.TTS_VOICE_HI)
        if language == "hi"
        else st.session_state.get("tts_voice_en", config.TTS_VOICE_EN)
    )
    res = tts.synthesize_speech_full(
        text,
        language=language,
        voice_override=voice_override,
    )
    if res["success"] and res["audio_bytes"]:
        turn_id = f"msg_{msg_idx}_{uuid.uuid4().hex[:6]}"
        st.session_state.tts_cache[msg_idx] = {
            "audio_bytes": res["audio_bytes"],
            "mime_type": res["mime_type"],
            "provider": res["provider"],
            "voice": res["voice"],
            "turn_id": turn_id,
        }
        st.session_state.tts_errors.pop(msg_idx, None)
        st.session_state.pending_autoplay_idx = msg_idx
        return True

    st.session_state.tts_errors[msg_idx] = (
        res.get("error_message")
        or "Could not generate voice audio. Click Retry Voice to try again."
    )
    return False


def _process_turn(user_text: str, input_meta: dict = None) -> bool:
    """Run existing AI conversation engine, CRM/lead/appointment persistence, and TTS."""
    clean_text = (user_text or "").strip()
    if not clean_text:
        return False

    # Prevent accidental duplicate submission of identical text within 1.5s
    now = time.monotonic()
    if (
        clean_text == st.session_state.last_submitted_text
        and (now - st.session_state.last_submitted_ts) < 1.5
    ):
        return False

    st.session_state.last_submitted_text = clean_text
    st.session_state.last_submitted_ts = now
    st.session_state.is_processing = True
    st.session_state.voice_error = ""

    context = st.session_state.conv_context
    selected_model = st.session_state.get("selected_gemini_model")
    selected_lang = st.session_state.get("selected_language", config.DEFAULT_LANGUAGE)

    try:
        response, updated_context = ai_agent.process_customer_message(
            clean_text,
            context,
            model_name=selected_model,
            selected_language=selected_lang,
        )
        st.session_state.conv_context = updated_context

        user_msg_idx = len(updated_context.messages) - 2
        ai_msg_idx = len(updated_context.messages) - 1
        if input_meta and user_msg_idx >= 0:
            st.session_state.msg_meta_by_index[user_msg_idx] = input_meta

        # Sync conversational appointment booking & CRM IDs
        if updated_context.booked_appointment_id and not st.session_state.appointment_id:
            st.session_state.appointment_id = updated_context.booked_appointment_id
        if updated_context.__dict__.get("_customer_id"):
            st.session_state.customer_id = updated_context.__dict__["_customer_id"]

        profile = updated_context.customer_profile
        qualification = lq.score_lead(profile)
        full_user_text = "\n".join(m.content for m in updated_context.messages if m.role == "user")
        if full_user_text:
            qualification.sentiment = lq.analyze_sentiment(full_user_text)
        updated_context.lead_qualification = qualification

        if any([
            profile.name, profile.budget_max, profile.preferred_location,
            profile.property_type, profile.bedrooms, profile.phone, profile.email,
        ]):
            db_conv_id = updated_context.__dict__.get("_db_id")
            customer_id = crm_service.upsert_customer_from_profile(
                profile,
                conversation_id=db_conv_id,
                existing_customer_id=st.session_state.customer_id,
            )
            updated_context.__dict__["_customer_id"] = customer_id
            lead_id = crm_service.upsert_lead_from_qualification(customer_id, qualification)
            st.session_state.customer_id = customer_id
            st.session_state.lead_id = lead_id

        if st.session_state.auto_voice_response and ai_msg_idx >= 0:
            _generate_tts_for_message(ai_msg_idx, response, updated_context.language)

        return True

    except Exception as e:
        logger.error(f"Message processing error: {e}", exc_info=True)
        st.session_state.voice_error = "Something went wrong generating a response. Please try again."
        return False
    finally:
        st.session_state.is_processing = False


def _handle_voice_recording(raw_bytes: bytes, audio_hash: str, filename: str, status_slot) -> bool:
    """Transcribe recorded audio immediately and run AI + TTS turn."""
    st.session_state.processed_audio_hashes.add(audio_hash)
    st.session_state.recorder_nonce = st.session_state.get("recorder_nonce", 0) + 1
    st.session_state.is_processing = True
    st.session_state.voice_error = ""

    lang_choice = st.session_state.get("selected_language", config.DEFAULT_LANGUAGE)
    whisper_size = st.session_state.get("selected_whisper_model", config.WHISPER_MODEL)

    try:
        status_slot.markdown(
            '<div class="dh-typing-indicator">◐ Transcribing your voice...</div>',
            unsafe_allow_html=True,
        )
        res = stt.transcribe_audio_detailed(
            raw_bytes,
            language=lang_choice,
            model_size=whisper_size,
            filename=filename,
        )
        if not res["success"]:
            st.session_state.voice_error = res["error_message"]
            return False

        status_slot.markdown(
            '<div class="dh-typing-indicator">◐ DreamHome AI is typing...</div>',
            unsafe_allow_html=True,
        )
        return _process_turn(
            res["text"],
            input_meta={
                "source": "voice",
                "language": res["language"],
                "confidence": res["confidence"],
                "duration": res["duration"],
            },
        )
    finally:
        st.session_state.is_processing = False


def _render_header():
    """Render minimal top header with ready status dot, auto-voice toggle, and New Chat button."""
    is_busy = st.session_state.is_processing
    status_cls = "dh-ready-dot busy" if is_busy else "dh-ready-dot"
    status_txt = "Processing..." if is_busy else "Ready"

    h_left, h_toggle, h_new = st.columns([5.2, 1.8, 1.4], vertical_alignment="center")
    with h_left:
        st.markdown(f"""
        <div class="dh-chat-title-wrap">
            <h1 class="dh-chat-title">DreamHome AI Assistant</h1>
            <span class="{status_cls}">● {status_txt}</span>
        </div>
        """, unsafe_allow_html=True)
    with h_toggle:
        st.session_state.auto_voice_response = st.toggle(
            "🔊 Voice",
            value=st.session_state.auto_voice_response,
            help="Automatically speak AI responses aloud",
        )
    with h_new:
        if st.button("+ New Chat", width="stretch"):
            _reset_conversation()
            st.rerun()

    st.markdown("<div style='border-bottom:1px solid #E2E8F0; margin:0.25rem 0 0.9rem 0;'></div>", unsafe_allow_html=True)


def _render_messages():
    """Render welcome state or left-AI / right-customer chat bubbles with inline voice playback."""
    context = st.session_state.conv_context
    messages = context.messages

    if not messages:
        st.markdown(f"""
        <div class="dh-welcome-box">
            <div class="dh-welcome-badge">DH</div>
            <div style="font-size:1.15rem; font-weight:700; color:#0F172A; margin-bottom:0.45rem;">
                DreamHome AI Assistant
            </div>
            <div style="font-size:0.95rem; color:#475569; line-height:1.6;">
                {html.escape(WELCOME_MESSAGE)}
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    latest_ai_idx = max((i for i, m in enumerate(messages) if getattr(m, "role", "") == "assistant"), default=-1)
    autoplay_idx = st.session_state.pending_autoplay_idx
    replay_idx = st.session_state.manual_replay_idx

    for idx, msg in enumerate(messages):
        role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        msg_lang = msg.language if hasattr(msg, "language") else msg.get("language", "en")
        meta_tag = st.session_state.msg_meta_by_index.get(idx)

        if role == "user":
            with st.chat_message("user", avatar="👤"):
                if meta_tag and meta_tag.get("source") == "voice":
                    st.caption(
                        f"🎙️ {meta_tag.get('duration', 0):.1f}s · {str(meta_tag.get('language', 'en')).upper()}"
                    )
                st.markdown(content)
        else:
            with st.chat_message("assistant", avatar="🏠"):
                st.markdown(content)

                cached = st.session_state.tts_cache.get(idx)
                tts_err = st.session_state.tts_errors.get(idx)

                if cached is not None:
                    base_turn_id = cached["turn_id"]
                    should_auto = False
                    render_turn_id = base_turn_id

                    if idx == autoplay_idx and base_turn_id not in st.session_state.played_turn_ids:
                        should_auto = True
                        st.session_state.played_turn_ids.add(base_turn_id)
                    elif idx == replay_idx:
                        should_auto = True
                        render_turn_id = f"{base_turn_id}_r{st.session_state.replay_seq}"

                    active_player_idx = replay_idx if replay_idx is not None else latest_ai_idx
                    if idx == active_player_idx:
                        voice_player.render_voice_player(
                            audio_bytes=cached["audio_bytes"],
                            mime_type=cached["mime_type"],
                            turn_id=render_turn_id,
                            auto_play=should_auto,
                            provider=cached.get("provider", "edge-tts"),
                        )

                    if st.button("▶ Replay", key=f"replay_btn_{idx}"):
                        st.session_state.manual_replay_idx = idx
                        st.session_state.replay_seq += 1
                        st.rerun()

                elif tts_err:
                    st.warning(f"🔇 {tts_err}")
                    if st.button("🔄 Retry Voice", key=f"retry_tts_{idx}"):
                        with st.spinner("Generating voice..."):
                            _generate_tts_for_message(idx, content, msg_lang)
                        st.rerun()

                else:
                    if st.button("🔊 Listen", key=f"speak_tts_{idx}"):
                        with st.spinner("Generating voice..."):
                            _generate_tts_for_message(idx, content, msg_lang)
                        st.rerun()

    st.session_state.pending_autoplay_idx = None
    st.session_state.manual_replay_idx = None

    meta = context.__dict__.get("_last_response_meta")
    if meta and meta.get("error_message"):
        st.error(meta["error_message"])


def _auto_scroll_if_updated(msg_count: int):
    """Smoothly scroll conversation to the newest message when a new turn arrives."""
    if msg_count > st.session_state.last_scroll_msg_count:
        st.session_state.last_scroll_msg_count = msg_count
        components.html(
            """
            <script>
            setTimeout(function() {
                try {
                    const main = window.parent.document.querySelector('section.main');
                    if (main) { main.scrollTo({ top: main.scrollHeight, behavior: 'smooth' }); }
                } catch (e) {}
            }, 80);
            </script>
            """,
            height=0,
        )


def show():
    """Render the dedicated ChatGPT/Blintii-style AI Voice Assistance interface."""
    _init_session()
    _inject_chat_styles()
    _render_header()

    # Large central conversation area
    _render_messages()

    if st.session_state.voice_error:
        err_col, dismiss_col = st.columns([5, 1])
        with err_col:
            st.error(st.session_state.voice_error)
        with dismiss_col:
            if st.button("Dismiss", width="stretch"):
                st.session_state.voice_error = ""
                st.rerun()

    status_slot = st.empty()
    _auto_scroll_if_updated(len(st.session_state.conv_context.messages))

    # Fixed bottom message composer: [Microphone] [Message DreamHome AI...] [Send]
    mic_audio = None
    text_submitted = False
    typed_text = ""

    with st._bottom:
        with st.container(key="dh_composer_bar"):
            c_mic, c_input = st.columns([2.0, 6.0], vertical_alignment="center")

            with c_mic:
                if stt.is_whisper_available() and hasattr(st, "audio_input"):
                    mic_key = f"mic_input_{st.session_state.recorder_nonce}"
                    mic_audio = st.audio_input(
                        "Voice input",
                        sample_rate=16000,
                        key=mic_key,
                        disabled=st.session_state.is_processing,
                        label_visibility="collapsed",
                        help="Click microphone to speak, click stop when finished",
                    )
                else:
                    st.button("🎙️ Unavailable", disabled=True, width="stretch")

            with c_input:
                with st.form("composer_form", clear_on_submit=True):
                    f_text, f_send = st.columns([5.2, 1.1], vertical_alignment="center")
                    with f_text:
                        typed_text = st.text_input(
                            "Message DreamHome AI",
                            placeholder="Message DreamHome AI...",
                            disabled=st.session_state.is_processing,
                            label_visibility="collapsed",
                        )
                    with f_send:
                        text_submitted = st.form_submit_button(
                            "Send",
                            type="primary",
                            disabled=st.session_state.is_processing,
                            width="stretch",
                        )

    # Process voice recording automatically upon stop
    if mic_audio is not None:
        raw_bytes = mic_audio.getvalue()
        audio_hash = hashlib.sha256(raw_bytes).hexdigest()
        if audio_hash not in st.session_state.processed_audio_hashes:
            _handle_voice_recording(
                raw_bytes,
                audio_hash,
                getattr(mic_audio, "name", "mic.wav"),
                status_slot,
            )
            st.rerun()

    # Process text submission cleanly
    if text_submitted:
        if typed_text and typed_text.strip():
            status_slot.markdown(
                '<div class="dh-typing-indicator">◐ DreamHome AI is typing...</div>',
                unsafe_allow_html=True,
            )
            _process_turn(typed_text, input_meta={"source": "text"})
            st.rerun()
