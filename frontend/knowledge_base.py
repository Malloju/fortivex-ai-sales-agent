"""
frontend/knowledge_base.py - Modern SaaS Knowledge Base & Property Inventory Page
"""
import csv
import pandas as pd
import streamlit as st
from backend import rag_service
from frontend import styles
import config


def show():
    """Render the Knowledge Base page."""
    stats = rag_service.get_knowledge_base_stats()
    is_indexed = rag_service.is_knowledge_base_indexed()

    styles.render_page_header(
        title="Knowledge Base & Inventory",
        subtitle="Semantic ChromaDB vector store and fictional DreamHome Realty property portfolio.",
        badge_text="Indexed" if is_indexed else "Not Indexed",
        badge_variant="green" if is_indexed else "amber",
    )

    k1, k2, k3 = st.columns([1, 1, 1.4])
    with k1:
        styles.render_kpi_card("Knowledge Chunks", stats.get("knowledge_chunks", 0), "company_knowledge.txt")
    with k2:
        styles.render_kpi_card("Property Vectors", stats.get("property_documents", 0), "properties.csv")
    with k3:
        st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🔄 Index Missing", type="primary", width="stretch"):
                with st.spinner("Indexing knowledge documents..."):
                    try:
                        counts = rag_service.index_knowledge_base(force_reindex=False)
                        st.success(f"Indexed: {counts.get('knowledge', 0)} chunks, {counts.get('properties', 0)} properties.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Indexing failed: {e}")
        with b2:
            if st.button("🔃 Force Reindex", width="stretch"):
                with st.spinner("Rebuilding ChromaDB collections..."):
                    try:
                        counts = rag_service.index_knowledge_base(force_reindex=True)
                        st.success(f"Reindexed: {counts.get('knowledge', 0)} chunks, {counts.get('properties', 0)} properties.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reindex failed: {e}")

    st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

    tab_search, tab_properties, tab_knowledge = st.tabs(
        ["Semantic Search & Filters", "Property Catalog", "Company Knowledge"]
    )

    with tab_search:
        search_query = st.text_input(
            "Semantic Query",
            placeholder="e.g., 2 BHK apartment in Phagwara under 50 lakh, or refund policy",
        )
        if search_query:
            with st.spinner("Searching ChromaDB..."):
                try:
                    docs, metas = rag_service.retrieve_relevant_docs(search_query)
                    if docs:
                        st.success(f"Found {len(docs)} relevant matches")
                        for i, (doc, meta) in enumerate(zip(docs, metas)):
                            source = (meta or {}).get("source", "unknown")
                            detail = (meta or {}).get("property_name") or (meta or {}).get("section") or ""
                            label = f"Match {i+1} · {source}" + (f" ({detail})" if detail else "")
                            with st.expander(label):
                                st.write(doc)
                    else:
                        styles.render_empty_state("No matches found", "Try rephrasing your query.")
                except Exception as e:
                    st.error(f"Search error: {e}")

        st.markdown("---")
        st.subheader("Filter Structured Properties")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            location = st.selectbox("City", ["All", "Phagwara", "Jalandhar", "Ludhiana", "Nawanshahr", "Adampur"])
        with f2:
            prop_type = st.selectbox("Property Type", ["All", "Apartment", "Independent House", "Villa"])
        with f3:
            bedrooms = st.selectbox("Bedrooms (BHK)", ["Any", 1, 2, 3, 4])
        with f4:
            max_budget_lakh = st.number_input("Max Budget (Lakh)", min_value=0, max_value=300, value=0, step=5)

        if st.button("Apply Property Filter", type="primary"):
            results = rag_service.search_properties_by_criteria(
                location=None if location == "All" else location,
                property_type=None if prop_type == "All" else prop_type,
                bedrooms=None if bedrooms == "Any" else int(bedrooms),
                max_budget=int(max_budget_lakh) * 100_000 if max_budget_lakh > 0 else None,
                top_k=24,
            )
            if results:
                st.success(f"{len(results)} matching properties")
                for prop in results:
                    price_inr = int(prop.get("price_inr", 0))
                    price_str = (
                        f"₹{price_inr/10_000_000:.2f} Crore"
                        if price_inr >= 10_000_000
                        else f"₹{price_inr/100_000:.1f} Lakh"
                    )
                    with st.expander(f"{prop.get('property_name')} — {price_str}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write(f"**Location:** {prop.get('location')}")
                            st.write(f"**Type:** {prop.get('property_type')} ({prop.get('bedrooms')} BHK)")
                            st.write(f"**Area:** {prop.get('area_sqft')} sqft · {prop.get('furnishing')}")
                        with c2:
                            st.write(f"**Price:** {price_str}")
                            st.write(f"**Status:** {prop.get('possession_status')}")
                            st.write(f"**Contact:** {prop.get('contact_information')}")
                        st.write(f"**Amenities:** {prop.get('amenities')}")
                        st.write(f"**Description:** {prop.get('description')}")
            else:
                styles.render_empty_state("No matching properties", "Adjust city, type, or budget filters.")

    with tab_properties:
        if config.PROPERTIES_CSV.exists():
            with open(config.PROPERTIES_CSV, encoding="utf-8") as f:
                properties = list(csv.DictReader(f))
            if properties:
                display_props = []
                for p in properties:
                    price = int(p.get("price_inr", 0))
                    price_str = f"₹{price/10_000_000:.2f} Cr" if price >= 10_000_000 else f"₹{price/100_000:.0f}L"
                    display_props.append({
                        "ID": p.get("property_id"),
                        "Name": p.get("property_name"),
                        "Type": p.get("property_type"),
                        "Location": p.get("location"),
                        "Price": price_str,
                        "BHK": p.get("bedrooms"),
                        "Area (sqft)": p.get("area_sqft"),
                        "Furnishing": p.get("furnishing"),
                        "Possession": p.get("possession_status"),
                    })
                st.dataframe(pd.DataFrame(display_props), width="stretch", hide_index=True)
                st.caption(f"{len(properties)} fictional properties loaded from `{config.PROPERTIES_CSV.name}`.")
        else:
            st.error(f"Properties file not found at {config.PROPERTIES_CSV}")

    with tab_knowledge:
        if config.KNOWLEDGE_TXT.exists():
            knowledge_text = config.KNOWLEDGE_TXT.read_text(encoding="utf-8")
            sections = [s.strip() for s in knowledge_text.split("====") if len(s.strip()) > 20]
            for section in sections:
                lines = section.strip().splitlines()
                if lines:
                    with st.expander(lines[0].strip()[:80]):
                        st.text("\n".join(lines[1:]) if len(lines) > 1 else section)
        else:
            st.error(f"Knowledge file not found at {config.KNOWLEDGE_TXT}")
