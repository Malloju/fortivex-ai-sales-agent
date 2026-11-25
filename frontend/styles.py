"""
frontend/styles.py - Shared modern light-themed SaaS design system for DreamHome AI
Provides restrained blue/indigo styling, crisp cards, status pills, and empty states.
"""
import html
import streamlit as st


def inject_global_styles() -> None:
    """Inject modern light-themed SaaS CSS across all pages."""
    st.markdown("""
    <style>
        /* Base layout & typography */
        html, body, [class*="css"] {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #0F172A;
        }
        .stApp {
            background-color: #F8FAFC;
        }
        .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
            max-width: 1280px;
        }

        /* Hide noisy Streamlit chrome */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        [data-testid="stDeployButton"] { display: none; }

        /* Compact, crisp light sidebar */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E2E8F0;
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1rem;
            padding-left: 0.9rem;
            padding-right: 0.9rem;
        }
        [data-testid="stSidebar"] [role="radiogroup"] {
            gap: 0.2rem;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            padding: 0.45rem 0.7rem;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 500;
            color: #334155;
            transition: background-color 0.15s ease, color 0.15s ease;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {
            background-color: #F1F5F9;
            color: #0F172A;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background-color: #EEF2FF;
            color: #4338CA;
            font-weight: 600;
            border: 1px solid #C7D2FE;
        }
        /* Hide default radio circle for clean nav list look */
        [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {
            display: none;
        }

        /* Cards & containers */
        .dh-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 1.1rem 1.25rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            margin-bottom: 0.85rem;
        }
        .dh-hero {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-left: 4px solid #4F46E5;
            border-radius: 12px;
            padding: 1.35rem 1.5rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        }
        .dh-page-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 0.85rem;
            margin-bottom: 1.1rem;
            border-bottom: 1px solid #E2E8F0;
        }
        .dh-page-title {
            font-size: 1.55rem;
            font-weight: 700;
            color: #0F172A;
            margin: 0;
            letter-spacing: -0.02em;
        }
        .dh-page-subtitle {
            font-size: 0.9rem;
            color: #475569;
            margin: 0.2rem 0 0 0;
        }

        /* KPI cards */
        .dh-kpi {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 0.95rem 1.1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
        }
        .dh-kpi-label {
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #64748B;
            margin-bottom: 0.35rem;
        }
        .dh-kpi-value {
            font-size: 1.65rem;
            font-weight: 700;
            color: #0F172A;
            line-height: 1.2;
        }
        .dh-kpi-hint {
            font-size: 0.78rem;
            color: #4F46E5;
            margin-top: 0.25rem;
        }

        /* Status pills */
        .dh-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.22rem 0.65rem;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .dh-pill-indigo { background: #EEF2FF; color: #4338CA; border: 1px solid #C7D2FE; }
        .dh-pill-blue   { background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }
        .dh-pill-green  { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
        .dh-pill-amber  { background: #FFFBEB; color: #B45309; border: 1px solid #FDE68A; }
        .dh-pill-red    { background: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA; }
        .dh-pill-slate  { background: #F1F5F9; color: #334155; border: 1px solid #CBD5E1; }

        /* Voice status strip */
        .dh-status-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 0.65rem 1rem;
            margin-bottom: 0.85rem;
        }

        /* Chat bubbles polish */
        [data-testid="stChatMessage"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.6rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
        }

        /* Buttons */
        .stButton > button {
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.88rem;
            border: 1px solid #CBD5E1;
            transition: all 0.15s ease;
        }
        .stButton > button[kind="primary"] {
            background-color: #4F46E5;
            border-color: #4F46E5;
            color: #FFFFFF;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #4338CA;
            border-color: #4338CA;
        }

        /* Clean empty state */
        .dh-empty {
            background: #FFFFFF;
            border: 1px dashed #CBD5E1;
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
            color: #475569;
            font-size: 0.9rem;
        }

        /* Responsive adjustments for smaller screens */
        @media (max-width: 768px) {
            .main .block-container {
                padding-left: 0.85rem;
                padding-right: 0.85rem;
            }
            .dh-page-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 0.4rem;
            }
        }
    </style>
    """, unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str, badge_text: str = "", badge_variant: str = "indigo") -> None:
    """Render a consistent clean page header."""
    safe_title = html.escape(title)
    safe_sub = html.escape(subtitle)
    badge_html = (
        f'<span class="dh-pill dh-pill-{badge_variant}">{html.escape(badge_text)}</span>'
        if badge_text else ""
    )
    st.markdown(f"""
    <div class="dh-page-header">
        <div>
            <h1 class="dh-page-title">{safe_title}</h1>
            <p class="dh-page-subtitle">{safe_sub}</p>
        </div>
        <div>{badge_html}</div>
    </div>
    """, unsafe_allow_html=True)


def render_kpi_card(label: str, value, hint: str = "") -> None:
    """Render a clean SaaS metric card."""
    safe_label = html.escape(str(label))
    safe_val = html.escape(str(value))
    hint_html = f'<div class="dh-kpi-hint">{html.escape(hint)}</div>' if hint else ""
    st.markdown(f"""
    <div class="dh-kpi">
        <div class="dh-kpi-label">{safe_label}</div>
        <div class="dh-kpi-value">{safe_val}</div>
        {hint_html}
    </div>
    """, unsafe_allow_html=True)


def render_empty_state(title: str, body: str) -> None:
    """Render a clean, low-noise empty state box."""
    st.markdown(f"""
    <div class="dh-empty">
        <div style="font-weight:600; color:#0F172A; margin-bottom:0.25rem;">{html.escape(title)}</div>
        <div>{html.escape(body)}</div>
    </div>
    """, unsafe_allow_html=True)
