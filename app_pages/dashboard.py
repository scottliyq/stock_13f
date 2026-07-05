import streamlit as st

from stock_13f.ui.data_access import load_manager_profiles
from stock_13f.ui.data_access import load_movers
from stock_13f.ui.data_access import load_recent_13dg
from stock_13f.ui.data_access import load_recent_8k
from stock_13f.ui.formatters import format_int
from stock_13f.ui.formatters import format_usd


report_period = st.session_state.get("global_report_period", "")
search_text = st.session_state.get("global_ticker_search", "")

top_holdings = load_movers(report_period, "stock", "top_total_holding_value", 8, search_text)
recent_8k = load_recent_8k(search_text=search_text, limit=8)
recent_13dg = load_recent_13dg(search_text=search_text, limit=8)
manager_profiles = load_manager_profiles()

with st.container(horizontal=True):
    st.metric(
        "Latest 13F rows",
        format_int(len(top_holdings)),
        border=True,
    )
    st.metric(
        "Recent 8-K filings",
        format_int(len(recent_8k)),
        border=True,
    )
    st.metric(
        "Recent 13D/G filings",
        format_int(len(recent_13dg)),
        border=True,
    )
    st.metric(
        "Tracked managers",
        format_int(len(manager_profiles)),
        border=True,
    )

col1, col2 = st.columns([1.4, 1.0], vertical_alignment="top")

with col1:
    with st.container(border=True):
        st.subheader("13F leader preview")
        if top_holdings:
            preview_rows = [
                {
                    "Ticker": row.get("ticker", "-"),
                    "Issuer": row.get("issuer", "-"),
                    "Institutions": row.get("holder_manager_count", 0),
                    "Total value": format_usd(row.get("total_holding_value_usd", 0)),
                    "New managers": row.get("new_manager_count", 0),
                }
                for row in top_holdings
            ]
            st.dataframe(preview_rows, use_container_width=True, hide_index=True)
            st.page_link("app_pages/thirteenf.py", label="Open 13F research page", icon=":material/arrow_forward:")
        else:
            st.info("No 13F movers found for the selected report period.", icon=":material/info:")

    with st.container(border=True):
        st.subheader("Quarterly movers preview")
        if top_holdings:
            movers_preview = [
                {
                    "Rank": row.get("rank", "-"),
                    "Ticker": row.get("ticker", "-"),
                    "New value": format_usd(row.get("new_entry_total_value_usd", 0)),
                    "Reduced value": format_usd(row.get("reduced_total_value_usd", 0)),
                    "Business summary": row.get("business_summary", "-"),
                }
                for row in top_holdings[:6]
            ]
            st.dataframe(movers_preview, use_container_width=True, hide_index=True)
            st.page_link(
                "app_pages/quarterly_movers.py",
                label="Open quarterly movers page",
                icon=":material/arrow_forward:",
            )
        else:
            st.info("Quarterly movers will appear here after Supabase data is available.", icon=":material/info:")

with col2:
    with st.container(border=True):
        st.subheader("Recent 8-K events")
        if recent_8k:
            st.dataframe(
                [
                    {
                        "Date": row.get("filing_date", "-"),
                        "Ticker": row.get("ticker", "-"),
                        "Form": row.get("form", "-"),
                        "Company": row.get("company_name", "-"),
                    }
                    for row in recent_8k
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.page_link("app_pages/eightk.py", label="Open 8-K feed", icon=":material/arrow_forward:")
        else:
            st.caption("No 8-K rows in the current raw table.")

    with st.container(border=True):
        st.subheader("Recent 13D/G events")
        if recent_13dg:
            st.dataframe(
                [
                    {
                        "Date": row.get("filing_date", "-"),
                        "Ticker": row.get("ticker", "-"),
                        "Form": row.get("form", "-"),
                        "Company": row.get("company_name", "-"),
                    }
                    for row in recent_13dg
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.page_link("app_pages/thirteendg.py", label="Open 13D/G feed", icon=":material/arrow_forward:")
        else:
            st.caption("Current 30-day sync returned no 13D/G rows.")
