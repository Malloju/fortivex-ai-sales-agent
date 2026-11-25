"""
frontend/crm.py - Modern SaaS CRM page showing customers, leads, and conversation logs
"""
import html
import pandas as pd
import streamlit as st
from backend import database as db
from backend import lead_qualification as lq
from backend import crm_service
from frontend import styles


def show():
    """Render the CRM page."""
    styles.render_page_header(
        title="Customer Relationship Manager",
        subtitle="Inspect qualified leads, customer requirements, conversation transcripts, and scheduled visits.",
        badge_text="SQLite CRM",
        badge_variant="indigo",
    )

    tab_customers, tab_leads, tab_history = st.tabs(
        ["Customers", "Lead Pipeline", "Conversation History"]
    )

    # ============================================================
    # CUSTOMERS TAB
    # ============================================================
    with tab_customers:
        col_search, col_loc = st.columns([3, 1])
        with col_search:
            search_query = st.text_input(
                "Search customers",
                placeholder="Search by name, phone, email, or city...",
            )
        with col_loc:
            loc_filter = st.selectbox(
                "Filter City",
                ["All", "Phagwara", "Jalandhar", "Ludhiana", "Nawanshahr", "Adampur"],
            )

        customers = db.list_customers(search=search_query)
        if loc_filter != "All":
            customers = [
                c for c in customers
                if (c.get("preferred_location") or "").lower() == loc_filter.lower()
            ]

        if customers:
            display_data = []
            for c in customers:
                budget = lq.format_budget(c["budget_max"]) if c.get("budget_max") else "—"
                display_data.append({
                    "ID": c["id"],
                    "Name": c.get("name") or "Prospect",
                    "Phone": c.get("phone") or "—",
                    "Email": c.get("email") or "—",
                    "Budget": budget,
                    "Location": c.get("preferred_location") or "—",
                    "Property": c.get("property_type") or "—",
                    "BHK": c.get("bedrooms") or "—",
                    "Timeline": c.get("purchase_timeline") or "—",
                    "Added": str(c.get("created_at", ""))[:10],
                })

            st.dataframe(pd.DataFrame(display_data), width="stretch", hide_index=True)

            customer_map = {
                f"#{c['id']} — {c.get('name') or 'Prospect'} ({c.get('preferred_location') or 'No city'})": c["id"]
                for c in customers
            }
            selected_label = st.selectbox("Inspect Customer Profile", list(customer_map.keys()))
            selected_customer_id = customer_map[selected_label]

            summary = crm_service.get_customer_summary(selected_customer_id)
            if summary:
                cust = summary["customer"]
                st.markdown(f"""
                <div class="dh-card">
                    <div style="font-weight:700; font-size:1.02rem; color:#0F172A; margin-bottom:0.65rem;">
                        {html.escape(cust.get('name') or 'Prospect')} · Customer #{selected_customer_id}
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:0.6rem; font-size:0.88rem;">
                        <div><span style="color:#64748B;">Phone:</span> <b>{html.escape(str(cust.get('phone') or 'Not provided'))}</b></div>
                        <div><span style="color:#64748B;">Email:</span> <b>{html.escape(str(cust.get('email') or 'Not provided'))}</b></div>
                        <div><span style="color:#64748B;">Budget:</span> <b>{html.escape(lq.format_budget(cust['budget_max']) if cust.get('budget_max') else 'Not specified')}</b></div>
                        <div><span style="color:#64748B;">Location:</span> <b>{html.escape(str(cust.get('preferred_location') or 'Not specified'))}</b></div>
                        <div><span style="color:#64748B;">Property Type:</span> <b>{html.escape(str(cust.get('property_type') or 'Any'))}</b></div>
                        <div><span style="color:#64748B;">Bedrooms:</span> <b>{html.escape(str(cust.get('bedrooms') or 'Not specified'))}</b></div>
                        <div><span style="color:#64748B;">Timeline:</span> <b>{html.escape(str(cust.get('purchase_timeline') or 'Flexible'))}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if cust.get("specific_requirements"):
                    st.caption(f"Special Requirements: {cust['specific_requirements']}")

                if summary["leads"]:
                    st.markdown("**Lead Qualification**")
                    for lead in summary["leads"]:
                        st.write(
                            f"• Lead #{lead['id']} — Score: **{lead.get('lead_score', 0)}/100** "
                            f"— Status: **{lead.get('lead_status', 'new').upper()}** "
                            f"— Sentiment: {lead.get('sentiment', 'neutral').title()} "
                            f"— Next Action: {lead.get('recommended_action') or 'Follow up'}"
                        )

                if summary["appointments"]:
                    st.markdown("**Scheduled Appointments**")
                    for appt in summary["appointments"]:
                        st.write(
                            f"• 📅 {appt.get('appointment_date')} at {appt.get('appointment_time')} "
                            f"— {appt.get('property_name') or 'Property visit'} "
                            f"— Code: `{appt.get('confirmation_code')}` "
                            f"[{appt.get('status', 'confirmed').upper()}]"
                        )

                if summary["conversations"]:
                    st.markdown("**Linked Conversations**")
                    for conv in summary["conversations"]:
                        with st.expander(f"Conversation {conv['conversation_uuid'][:8]} ({conv.get('total_messages', 0)} messages)"):
                            for m in conv.get("messages", []):
                                icon = "👤" if m["role"] == "user" else "🏠"
                                st.markdown(f"{icon} **{m['role'].title()}:** {m['content']}")
        else:
            styles.render_empty_state(
                "No customers match your filter",
                "Try clearing the search box or start a conversation on the AI Sales Agent page.",
            )

    # ============================================================
    # LEAD PIPELINE TAB
    # ============================================================
    with tab_leads:
        leads = db.list_leads()
        if leads:
            status_filter = st.multiselect(
                "Filter by Lead Status",
                ["new", "cold", "warm", "hot", "qualified", "converted", "lost"],
                default=["new", "cold", "warm", "hot", "qualified"],
            )
            filtered_leads = [l for l in leads if l.get("lead_status") in status_filter]

            if filtered_leads:
                display_leads = [
                    {
                        "Lead ID": l["id"],
                        "Customer": l.get("customer_name") or "Prospect",
                        "Phone": l.get("customer_phone") or "—",
                        "Score": f"{l.get('lead_score', 0)}/100",
                        "Status": l.get("lead_status", "new").upper(),
                        "Location": l.get("preferred_location") or "—",
                        "Budget": lq.format_budget(l["budget_max"]) if l.get("budget_max") else "—",
                        "Sentiment": l.get("sentiment", "neutral").title(),
                        "Recommended Action": l.get("recommended_action") or "—",
                    }
                    for l in filtered_leads
                ]
                st.dataframe(pd.DataFrame(display_leads), width="stretch", hide_index=True)

                st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
                p_cols = st.columns(5)
                for i, stage in enumerate(["new", "cold", "warm", "hot", "qualified"]):
                    with p_cols[i]:
                        styles.render_kpi_card(
                            stage.title(),
                            sum(1 for l in leads if l.get("lead_status") == stage),
                        )
            else:
                styles.render_empty_state("No matching leads", "Adjust the status filter above.")
        else:
            styles.render_empty_state(
                "No leads recorded yet",
                "Leads are automatically scored and saved during AI Sales Agent conversations.",
            )

    # ============================================================
    # CONVERSATION HISTORY TAB
    # ============================================================
    with tab_history:
        conversations = db.list_conversations()
        if conversations:
            for conv in conversations:
                with st.expander(
                    f"Conversation {conv['conversation_uuid'][:8]} · "
                    f"Customer: {conv.get('customer_name') or 'Prospect'} · "
                    f"{str(conv.get('created_at', ''))[:16]}"
                ):
                    st.caption(
                        f"Messages: {conv.get('total_messages', 0)} · "
                        f"Language: {conv.get('language', 'en').upper()}"
                    )
                    messages = db.get_conversation_messages(conv["id"])
                    for msg in messages:
                        role_icon = "👤" if msg["role"] == "user" else "🏠"
                        st.markdown(f"{role_icon} **{msg['role'].title()}:** {msg['content']}")
        else:
            styles.render_empty_state(
                "No conversation history yet",
                "Start a conversation on the AI Sales Agent page to record transcripts.",
            )
