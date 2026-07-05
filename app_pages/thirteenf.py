import pandas as pd
import streamlit as st

from stock_13f.ui.data_access import build_security_history_digest
from stock_13f.ui.data_access import load_latest_13dg_change_summary
from stock_13f.ui.data_access import load_recent_13dg
from stock_13f.ui.data_access import load_recent_8k
from stock_13f.ui.data_access import load_security_candidates
from stock_13f.ui.data_access import load_security_history
from stock_13f.ui.data_access import load_security_period_rows
from stock_13f.ui.data_access import summarize_13dg_row
from stock_13f.ui.data_access import summarize_8k_row
from stock_13f.ui.formatters import format_int
from stock_13f.ui.formatters import format_usd
from stock_13f.ui.selection import resolve_selected_index


SORT_OPTIONS = {
    "Largest ownership": "total_holding_value_usd",
    "Most new managers": "new_manager_count",
    "Most reduced managers": "reduced_manager_count",
}
RANKING_LABELS = {
    "top_new_manager_count": "Top new managers",
    "top_total_holding_value": "Top holding value",
    "top_reduced_manager_count": "Top reduced managers",
}


def _coalesce_choice(value: str | None, default: str) -> str:
    return value if value is not None else default


report_period = st.session_state.get("global_report_period", "")
search_text = st.session_state.get("global_ticker_search", "")

with st.container(border=True):
    col1, col2, col3, col4 = st.columns([0.72, 1.15, 0.72, 0.9], vertical_alignment="center")
    with col1:
        security_type = _coalesce_choice(
            st.segmented_control(
                "Universe",
                options=["stock", "etf"],
                default="stock",
                format_func=lambda value: value.upper(),
                key="thirteenf_universe",
            ),
            "stock",
        )
    with col2:
        sort_label = _coalesce_choice(
            st.segmented_control(
                "Research lens",
                options=list(SORT_OPTIONS),
                default="Largest ownership",
                key="thirteenf_sort_lens",
            ),
            "Largest ownership",
        )
    with col3:
        candidate_limit = st.selectbox("Candidates", options=[12, 24, 48, 96], index=1, key="thirteenf_candidate_limit")
    with col4:
        min_holders = st.selectbox(
            "Min institutions",
            options=[0, 100, 300, 500, 1000],
            index=0,
            key="thirteenf_min_holders",
        )

candidates = load_security_candidates(
    report_period,
    security_type,
    search_text,
    min_holders,
    SORT_OPTIONS[sort_label],
    candidate_limit,
)
visible_value_sum = sum(int(row.get("total_holding_value_usd", 0)) for row in candidates)
visible_institutions = sum(int(row.get("holder_manager_count", 0)) for row in candidates)
multi_signal_count = sum(1 for row in candidates if int(row.get("signal_count", 0)) >= 2)
top10_signal_count = sum(1 for row in candidates if int(row.get("best_rank", 10_000)) <= 10)

with st.container(horizontal=True):
    st.metric("Research candidates", format_int(len(candidates)), border=True)
    st.metric("Visible total value", format_usd(visible_value_sum), border=True)
    st.metric("Institution sum", format_int(visible_institutions), border=True)
    st.metric("Multi-signal names", format_int(multi_signal_count), border=True)
    st.metric("Top-10 signals", format_int(top10_signal_count), border=True)

left_col, right_col = st.columns([0.95, 1.45], vertical_alignment="top")

with left_col:
    with st.container(border=True):
        st.subheader("Research queue")
        st.caption(
            "One row per security for the selected quarter. Use this page to pick a name, then read the full"
            " positioning and event context on the right."
        )
        if candidates:
            queue_df = pd.DataFrame(
                [
                    {
                        "Ticker": row.get("ticker", "-"),
                        "Issuer": row.get("issuer", "-"),
                        "Institutions": int(row.get("holder_manager_count", 0)),
                        "Total value": format_usd(row.get("total_holding_value_usd", 0)),
                        "New mgrs": int(row.get("new_manager_count", 0)),
                        "Reduced mgrs": int(row.get("reduced_manager_count", 0)),
                        "Signals": int(row.get("signal_count", 0)),
                    }
                    for row in candidates
                ]
            )
            table_event = st.dataframe(
                queue_df,
                use_container_width=True,
                hide_index=True,
                key="thirteenf_research_queue",
                on_select="rerun",
                selection_mode="single-row",
            )
            selected_index = resolve_selected_index("thirteenf_selected_index", len(candidates), table_event)
            st.caption(
                f"Report period {report_period or '-'} · {security_type.upper()} universe · {sort_label.lower()} ·"
                f" queue size {len(candidates)}"
            )
            st.caption(f"Click a row to switch the research panel. Current selection #{selected_index + 1}.")
        else:
            st.info("No matching research candidates for the current filters.", icon=":material/info:")

with right_col:
    with st.container(border=True):
        st.subheader("Security research")
        if not candidates:
            st.caption("Choose a report period or widen the filters to inspect a security.")
        else:
            selected_row = candidates[st.session_state.get("thirteenf_selected_index", 0)]
            st.markdown(f"**{selected_row.get('issuer', '-') }**")
            st.caption(
                f"Ticker: {selected_row.get('ticker', '-') or '-'}"
                f" · CUSIP: {selected_row.get('cusip', '-')}"
                f" · Type: {selected_row.get('security_type', '-')}"
                f" · Signals this quarter: {selected_row.get('ranking_summary', 'No ranking summary')}"
            )
            with st.container(horizontal=True):
                st.metric("Institutions", format_int(selected_row.get("holder_manager_count", 0)), border=True)
                st.metric("Total value", format_usd(selected_row.get("total_holding_value_usd", 0)), border=True)
                st.metric("New managers", format_int(selected_row.get("new_manager_count", 0)), border=True)
                st.metric("Reduced managers", format_int(selected_row.get("reduced_manager_count", 0)), border=True)
                st.metric("Signal count", format_int(selected_row.get("signal_count", 0)), border=True)
            st.caption(selected_row.get("business_summary", "No business summary."))

            detail_view = _coalesce_choice(
                st.segmented_control(
                    "Detail view",
                    options=["Current setup", "Trend", "Events"],
                    default="Current setup",
                    key="thirteenf_detail_view",
                ),
                "Current setup",
            )

            if detail_view == "Current setup":
                period_rows = load_security_period_rows(
                    report_period,
                    str(selected_row.get("cusip", "")),
                    str(selected_row.get("security_type", "")),
                )
                if period_rows:
                    setup_df = pd.DataFrame(
                        [
                            {
                                "Ranking": RANKING_LABELS.get(str(row.get("ranking_type", "")), row.get("ranking_type", "-")),
                                "Rank": int(row.get("rank", 0)),
                                "Institutions": int(row.get("holder_manager_count", 0)),
                                "Total value": format_usd(row.get("total_holding_value_usd", 0)),
                                "New value": format_usd(row.get("new_entry_total_value_usd", 0)),
                                "Reduced value": format_usd(row.get("reduced_total_value_usd", 0)),
                            }
                            for row in sorted(period_rows, key=lambda row: int(row.get("rank", 10_000)))
                        ]
                    )
                    st.dataframe(setup_df, use_container_width=True, hide_index=True)
                    comparison_df = pd.DataFrame(
                        [
                            {
                                "ranking": RANKING_LABELS.get(str(row.get("ranking_type", "")), row.get("ranking_type", "-")),
                                "value_usd": int(row.get("total_holding_value_usd", 0)),
                            }
                            for row in period_rows
                        ]
                    )
                    st.bar_chart(comparison_df, x="ranking", y="value_usd", use_container_width=True)
                else:
                    st.caption("No current-period setup rows found for this security.")
            elif detail_view == "Trend":
                history_rows = load_security_history(
                    str(selected_row.get("cusip", "")),
                    str(selected_row.get("security_type", "")),
                )
                history_digest = build_security_history_digest(history_rows)
                if history_digest:
                    chart_df = pd.DataFrame(
                        [
                            {
                                "report_date": str(row.get("report_date", "")),
                                "total_holding_value_usd": int(row.get("total_holding_value_usd", 0)),
                                "holder_manager_count": int(row.get("holder_manager_count", 0)),
                            }
                            for row in history_digest
                        ]
                    ).sort_values("report_date")
                    st.line_chart(
                        chart_df.set_index("report_date")[["total_holding_value_usd", "holder_manager_count"]],
                        use_container_width=True,
                    )
                    trend_df = pd.DataFrame(
                        [
                            {
                                "Report period": row.get("report_date", "-"),
                                "Best rank": int(row.get("best_rank", 10_000)),
                                "Signals": int(row.get("signal_count", 0)),
                                "Institutions": int(row.get("holder_manager_count", 0)),
                                "Total value": format_usd(row.get("total_holding_value_usd", 0)),
                                "Ranking map": row.get("ranking_summary", "-"),
                            }
                            for row in history_digest
                        ]
                    )
                    st.dataframe(trend_df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No quarter history available for this security.")
            else:
                if security_type == "stock" and selected_row.get("ticker"):
                    related_8k = [
                        summarize_8k_row(row)
                        for row in load_recent_8k(search_text=str(selected_row.get("ticker", "")), limit=8)
                    ]
                    latest_13dg_change = load_latest_13dg_change_summary(str(selected_row.get("ticker", "")))
                    related_13dg = [
                        summarize_13dg_row(row)
                        for row in load_recent_13dg(search_text=str(selected_row.get("ticker", "")), limit=8)
                    ]
                    st.markdown("**8-K event feed**")
                    if related_8k:
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Date": row.get("filing_date", "-"),
                                        "Form": row.get("form", "-"),
                                        "Items": ", ".join(row.get("item_codes", [])[:2]) or "-",
                                        "Takeaway": str(row.get("summary_text", "-"))[:120],
                                    }
                                    for row in related_8k
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("No matching 8-K rows in the current raw filings table.")

                    st.markdown("**Latest 13D/G change**")
                    if latest_13dg_change:
                        latest_detail = latest_13dg_change.get("latest_detail", {})
                        previous_detail = latest_13dg_change.get("previous_detail", {})
                        status_counts = latest_13dg_change.get("status_counts", {})
                        with st.container(border=True):
                            st.caption(
                                f"{latest_detail.get('filing_date', '-')}"
                                f" · {latest_detail.get('form', '-')}"
                                f" · issuer {latest_detail.get('issuer_name', '-') or latest_detail.get('company_name', '-')}"
                            )
                            st.write(latest_13dg_change.get("summary_text", ""))
                            change_col1, change_col2, change_col3, change_col4 = st.columns(4)
                            with change_col1:
                                st.metric("New persons", format_int(status_counts.get("new", 0)), border=True)
                            with change_col2:
                                st.metric("Increased", format_int(status_counts.get("increased", 0)), border=True)
                            with change_col3:
                                st.metric("Decreased", format_int(status_counts.get("decreased", 0)), border=True)
                            with change_col4:
                                st.metric("Exited", format_int(status_counts.get("exited", 0)), border=True)
                            if previous_detail:
                                st.caption(
                                    f"Compared with previous filing on {previous_detail.get('filing_date', '-')}"
                                    f" ({previous_detail.get('form', '-')})"
                                )
                            changes = latest_13dg_change.get("changes", [])
                            if changes:
                                st.dataframe(
                                    pd.DataFrame(
                                        [
                                            {
                                                "Name": row.get("name", "-"),
                                                "Status": row.get("status", "-"),
                                                "Current %": (
                                                    f"{float(row['current_percent']):g}%"
                                                    if row.get("current_percent") is not None
                                                    else "-"
                                                ),
                                                "Previous %": (
                                                    f"{float(row['previous_percent']):g}%"
                                                    if row.get("previous_percent") is not None
                                                    else "-"
                                                ),
                                                "Delta shares": f"{int(row['delta_shares']):+,}",
                                            }
                                            for row in changes[:6]
                                        ]
                                    ),
                                    use_container_width=True,
                                    hide_index=True,
                                )
                    else:
                        st.caption("No structured 13D/G change summary is available for this ticker yet.")

                    st.markdown("**13D/G event feed**")
                    if related_13dg:
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Date": row.get("filing_date", "-"),
                                        "Form": row.get("form", "-"),
                                        "Company": row.get("company_name", "-"),
                                        "Summary": str(row.get("summary_text", "-"))[:120],
                                    }
                                    for row in related_13dg
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("No recent 13D/G events for this ticker in the current raw table.")

                    links_col1, links_col2 = st.columns(2)
                    with links_col1:
                        st.page_link("app_pages/eightk.py", label="Open full 8-K page", icon=":material/open_in_new:")
                    with links_col2:
                        st.page_link("app_pages/thirteendg.py", label="Open full 13D/G page", icon=":material/open_in_new:")
                else:
                    st.caption("Event linkage is shown for stock mode only. ETFs stay on the ownership research path.")
