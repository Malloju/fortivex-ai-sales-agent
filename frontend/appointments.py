"""
frontend/appointments.py - Modern SaaS Appointment Scheduling & Management Page
"""
import html
import pandas as pd
import streamlit as st
from backend import database as db
from backend import appointment_service
from frontend import styles
import config


def show():
    """Render the Appointments page."""
    styles.render_page_header(
        title="Appointments & Site Visits",
        subtitle=f"Business hours: Mon–Sat, {config.BUSINESS_HOURS_START}:00–{config.BUSINESS_HOURS_END}:00 ({config.TIMEZONE}). Double-booking is blocked automatically.",
        badge_text="Asia/Kolkata",
        badge_variant="blue",
    )

    tab_upcoming, tab_all, tab_book = st.tabs(
        ["Upcoming Confirmed", "All Appointments", "Book New Visit"]
    )

    with tab_upcoming:
        appointments = db.list_appointments(status="confirmed")
        if appointments:
            display_data = [
                {
                    "ID": a["id"],
                    "Code": a.get("confirmation_code") or "—",
                    "Date": a.get("appointment_date") or "—",
                    "Time": a.get("appointment_time") or "—",
                    "Customer": a.get("customer_name") or "Prospect",
                    "Phone": a.get("customer_phone") or "—",
                    "Property": a.get("property_name") or "Property Visit",
                    "Duration": f"{a.get('duration_minutes', 60)} min",
                }
                for a in appointments
            ]
            st.dataframe(pd.DataFrame(display_data), width="stretch", hide_index=True)

            appt_map = {
                f"#{a['id']} ({a.get('confirmation_code', '—')}) — {a.get('customer_name') or 'Prospect'} · {a.get('appointment_date')} {a.get('appointment_time')}": a
                for a in appointments
            }
            selected_label = st.selectbox("Select Appointment to Inspect or Cancel", list(appt_map.keys()))
            appt = appt_map[selected_label]

            st.markdown(f"""
            <div class="dh-card" style="border-left:4px solid #10B981;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <span style="font-weight:700; color:#0F172A;">Confirmed Site Visit</span>
                    <span class="dh-pill dh-pill-green">{html.escape(str(appt.get('confirmation_code')))}</span>
                </div>
                <div style="font-size:0.88rem; color:#334155; line-height:1.6;">
                    <b>Date &amp; Time:</b> {html.escape(str(appt.get('appointment_date')))} at {html.escape(str(appt.get('appointment_time')))} IST<br>
                    <b>Customer:</b> {html.escape(str(appt.get('customer_name') or 'Prospect'))} ({html.escape(str(appt.get('customer_phone') or 'No phone'))})<br>
                    <b>Property:</b> {html.escape(str(appt.get('property_name') or 'Property Visit'))}<br>
                    <b>Duration:</b> {appt.get('duration_minutes', 60)} minutes
                    {f"<br><b>Notes:</b> {html.escape(str(appt.get('notes')))}" if appt.get('notes') else ""}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"Cancel Appointment #{appt['id']}", type="secondary"):
                if appointment_service.cancel_appointment(appt["id"]):
                    st.success(f"Appointment #{appt['id']} ({appt.get('confirmation_code')}) cancelled.")
                    st.rerun()
        else:
            styles.render_empty_state(
                "No upcoming appointments",
                "Book a site visit conversationally in AI Sales Agent or use the Book New Visit tab.",
            )

    with tab_all:
        all_appointments = db.list_appointments()
        if all_appointments:
            display_all = [
                {
                    "ID": a["id"],
                    "Code": a.get("confirmation_code") or "—",
                    "Status": str(a.get("status", "")).upper(),
                    "Date": a.get("appointment_date"),
                    "Time": a.get("appointment_time"),
                    "Customer": a.get("customer_name") or "Prospect",
                    "Property": a.get("property_name") or "—",
                    "Created": str(a.get("created_at", ""))[:10],
                }
                for a in all_appointments
            ]
            st.dataframe(pd.DataFrame(display_all), width="stretch", hide_index=True)

            total = len(all_appointments)
            confirmed = sum(1 for a in all_appointments if a.get("status") == "confirmed")
            cancelled = sum(1 for a in all_appointments if a.get("status") == "cancelled")
            m1, m2, m3 = st.columns(3)
            with m1:
                styles.render_kpi_card("Total Appointments", total)
            with m2:
                styles.render_kpi_card("Confirmed", confirmed)
            with m3:
                styles.render_kpi_card("Cancelled", cancelled)
        else:
            styles.render_empty_state(
                "No appointments recorded yet",
                "All confirmed and cancelled site visits will appear here.",
            )

    with tab_book:
        customers = db.list_customers()
        if not customers:
            styles.render_empty_state(
                "No customers in CRM yet",
                "Start a conversation in AI Sales Agent to create a customer record before booking.",
            )
            return

        customer_options = {
            f"{c['name']} (ID: {c['id']}, Phone: {c.get('phone') or 'N/A'})": c["id"]
            for c in customers
        }
        slots = appointment_service.get_available_slots()
        if not slots:
            styles.render_empty_state("No open slots available", "Check existing appointments or business hours.")
            return

        slot_options = {s["display"]: s for s in slots}
        with st.form("manual_booking"):
            c1, c2 = st.columns(2)
            with c1:
                selected_customer = st.selectbox("Customer", list(customer_options.keys()))
            with c2:
                selected_slot = st.selectbox("Available Time Slot", list(slot_options.keys()))
            prop_name = st.text_input("Property Name", placeholder="e.g., Sunrise Apartments - 2BHK")
            notes = st.text_area("Notes", placeholder="Special requests or preferences...")

            if st.form_submit_button("Confirm Appointment", type="primary"):
                customer_id = customer_options[selected_customer]
                slot = slot_options[selected_slot]
                result = appointment_service.book_appointment(
                    customer_id=customer_id,
                    appointment_date=slot["date"],
                    appointment_time=slot["time"],
                    property_name=prop_name or None,
                    notes=notes or None,
                )
                if result["success"]:
                    st.success(result["message"])
                    st.rerun()
                else:
                    st.error(result["message"])
