"""
frontend/business_insights.py - Modern SaaS Business Analytics & Call Summaries Page
"""
import json
import pandas as pd
import streamlit as st
from backend import database as db
from frontend import styles


def show():
    """Render the Business Insights page."""
    styles.render_page_header(
        title="Business Insights",
        subtitle="Real-time conversion metrics, customer sentiment, demand trends, and call summaries from SQLite.",
        badge_text="Live Analytics",
        badge_variant="indigo",
    )

    metrics = db.get_dashboard_metrics()
    summaries = db.list_call_summaries(limit=100)
    leads = db.list_leads(limit=200)

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        styles.render_kpi_card("Calls", metrics["total_conversations"])
    with k2:
        styles.render_kpi_card("Leads", metrics["total_leads"])
    with k3:
        styles.render_kpi_card("Qualified", metrics["qualified_leads"])
    with k4:
        styles.render_kpi_card("Appointments", metrics["total_appointments"])
    with k5:
        styles.render_kpi_card("Conversion", f"{metrics['conversion_rate']}%")

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        st.subheader("Lead Pipeline Breakdown")
        pipeline_data = {}
        for lead in leads:
            status = lead.get("lead_status", "new")
            pipeline_data[status] = pipeline_data.get(status, 0) + 1
        if pipeline_data:
            pipeline_df = pd.DataFrame(
                list(pipeline_data.items()), columns=["Status", "Count"]
            ).sort_values("Count", ascending=False)
            st.bar_chart(pipeline_df.set_index("Status"), color="#4F46E5")
        else:
            styles.render_empty_state("No pipeline data yet", "Lead statuses populate as conversations occur.")

        st.subheader("Most Requested Locations")
        top_locs = metrics.get("top_locations", [])
        if top_locs:
            loc_df = pd.DataFrame(top_locs)[["preferred_location", "count"]]
            loc_df.columns = ["Location", "Requests"]
            st.bar_chart(loc_df.set_index("Location"), color="#2563EB")
        else:
            styles.render_empty_state("No location trends yet", "Preferences appear after customer inquiries.")

    with col_right:
        st.subheader("Customer Sentiment Distribution")
        sentiment_data = metrics.get("sentiment_distribution", {})
        if sentiment_data:
            sent_df = pd.DataFrame(
                list(sentiment_data.items()), columns=["Sentiment", "Count"]
            )
            st.bar_chart(sent_df.set_index("Sentiment"), color="#4F46E5")
        else:
            styles.render_empty_state("No sentiment data yet", "Save a call summary to analyze sentiment.")

        st.subheader("Property Type Interest")
        ptypes = metrics.get("top_property_types", [])
        if ptypes:
            pt_df = pd.DataFrame(ptypes)[["property_type", "count"]]
            pt_df.columns = ["Type", "Count"]
            st.bar_chart(pt_df.set_index("Type"), color="#2563EB")
        else:
            styles.render_empty_state("No property interest data yet", "Property preferences populate from CRM.")

    st.markdown("---")
    st.subheader("Lead Score Distribution")
    if leads:
        scores = [l.get("lead_score", 0) for l in leads]
        buckets = {
            "0-24 (Cold)": sum(1 for s in scores if 0 <= s < 25),
            "25-49 (Warm)": sum(1 for s in scores if 25 <= s < 50),
            "50-74 (Hot)": sum(1 for s in scores if 50 <= s < 75),
            "75-100 (Qualified)": sum(1 for s in scores if 75 <= s <= 100),
        }
        bucket_df = pd.DataFrame(list(buckets.items()), columns=["Score Range", "Count"])
        c1, c2 = st.columns([3, 1])
        with c1:
            st.bar_chart(bucket_df.set_index("Score Range"), color="#4F46E5")
        with c2:
            avg_score = sum(scores) / len(scores) if scores else 0
            styles.render_kpi_card("Avg Lead Score", f"{avg_score:.1f}/100", f"Across {len(scores)} leads")
    else:
        styles.render_empty_state("No lead scores yet", "Scores appear after conversations start.")

    st.markdown("---")
    st.subheader("Call Summaries")
    if summaries:
        for summary in summaries[:15]:
            with st.expander(
                f"{summary.get('customer_name') or 'Prospect'} · "
                f"Score: {summary.get('lead_score', 0)}/100 ({str(summary.get('lead_status', 'new')).upper()}) · "
                f"{str(summary.get('created_at', ''))[:16]}"
            ):
                st.write(summary.get("summary_text", "N/A"))
                st.caption(
                    f"Budget: {summary.get('budget_discussed', 'N/A')} · "
                    f"Property: {summary.get('preferred_property', 'N/A')} · "
                    f"Sentiment: {str(summary.get('sentiment', 'neutral')).title()} · "
                    f"Appointment: {'Booked' if summary.get('appointment_booked') else 'None'}"
                )
                st.write(f"**Next Action:** {summary.get('next_action', 'Follow up')}")
                try:
                    key_points = json.loads(summary.get("key_points") or "[]")
                    if key_points:
                        for pt in key_points:
                            st.markdown(f"• {pt}")
                except Exception:
                    pass
    else:
        styles.render_empty_state(
            "No call summaries saved yet",
            "Click 'Save Summary' on the AI Sales Agent page after a conversation.",
        )

    st.markdown("---")
    st.subheader("Appointment Statistics")
    appointments = db.list_appointments()
    if appointments:
        total = len(appointments)
        confirmed = sum(1 for a in appointments if a.get("status") == "confirmed")
        cancelled = sum(1 for a in appointments if a.get("status") == "cancelled")
        completed = sum(1 for a in appointments if a.get("status") == "completed")

        a1, a2, a3, a4 = st.columns(4)
        with a1:
            styles.render_kpi_card("Total", total)
        with a2:
            styles.render_kpi_card("Confirmed", confirmed)
        with a3:
            styles.render_kpi_card("Completed", completed)
        with a4:
            styles.render_kpi_card("Cancelled", cancelled)

        prop_counts = {}
        for a in appointments:
            prop = a.get("property_name") or "General Visit"
            prop_counts[prop] = prop_counts.get(prop, 0) + 1
        if prop_counts:
            prop_df = pd.DataFrame(list(prop_counts.items()), columns=["Property", "Appointments"])
            st.dataframe(prop_df, width="stretch", hide_index=True)
    else:
        styles.render_empty_state("No appointment records yet", "Confirmed visits appear here.")
