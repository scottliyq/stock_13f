import pandas as pd
import streamlit as st

from stock_13f.ui.data_access import build_security_history_digest
from stock_13f.ui.data_access import load_movers
from stock_13f.ui.data_access import load_recent_8k
from stock_13f.ui.data_access import load_security_history
from stock_13f.ui.data_access import load_security_period_rows
from stock_13f.ui.data_access import summarize_8k_row
from stock_13f.ui.formatters import format_int
from stock_13f.ui.formatters import format_usd
from stock_13f.ui.selection import resolve_selected_index


RANKING_OPTIONS = {
    "Top new managers": "top_new_manager_count",
    "Top holding value": "top_total_holding_value",
    "Top reduced managers": "top_reduced_manager_count",
}
RANKING_LABEL_TO_METRIC = {
    "Top new managers": "new_manager_count",
    "Top holding value": "holder_manager_count",
    "Top reduced managers": "reduced_manager_count",
}
RANKING_LABELS = {
    "top_new_manager_count": "Top new managers",
    "top_total_holding_value": "Top holding value",
    "top_reduced_manager_count": "Top reduced managers",
}


def _coalesce_choice(value: str | None, default: str) -> str:
    return value if value is not None else default


def _build_mover_headline(selected_row: dict[str, object], ranking_label: str) -> str:
    if ranking_label == "Top new managers":
        return (
            f"Rank #{int(selected_row.get('rank', 0))} because {format_int(selected_row.get('new_manager_count', 0))}"
            f" managers newly appeared this quarter with {format_usd(selected_row.get('new_entry_total_value_usd', 0))}"
            " of fresh disclosed value."
        )
    if ranking_label == "Top reduced managers":
        return (
            f"Rank #{int(selected_row.get('rank', 0))} because {format_int(selected_row.get('reduced_manager_count', 0))}"
            f" managers reduced exposure, trimming {format_usd(selected_row.get('reduced_total_value_usd', 0))}."
        )
    return (
        f"Rank #{int(selected_row.get('rank', 0))} on total holding value with"
        f" {format_usd(selected_row.get('total_holding_value_usd', 0))} disclosed across"
        f" {format_int(selected_row.get('holder_manager_count', 0))} managers."
    )


report_period = st.session_state.get("global_report_period", "")
search_text = st.session_state.get("global_ticker_search", "")

with st.container(border=True):
    col1, col2, col3, col4 = st.columns([0.75, 1.15, 0.72, 0.9], vertical_alignment="center")
    with col1:
        security_type = _coalesce_choice(
            st.segmented_control(
                "Asset type",
                options=["stock", "etf"],
                default="stock",
                format_func=lambda value: value.upper(),
                key="quarterly_movers_asset_type",
            ),
            "stock",
        )
    with col2:
        ranking_label = _coalesce_choice(
            st.segmented_control(
                "Ranking type",
                options=list(RANKING_OPTIONS),
                default="Top new managers",
                key="quarterly_movers_ranking_type",
            ),
            "Top new managers",
        )
    with col3:
        top_n = st.selectbox("Top N", options=[10, 20, 50, 100], index=3, key="quarterly_movers_top_n")
    with col4:
        threshold_label = {
            "Top new managers": "Min new managers",
            "Top holding value": "Min holders",
            "Top reduced managers": "Min reduced managers",
        }[ranking_label]
        threshold = st.selectbox(threshold_label, options=[0, 1, 3, 5, 10], index=0, key="quarterly_movers_threshold")

rows = load_movers(report_period, security_type, RANKING_OPTIONS[ranking_label], 100, search_text)
metric_name = RANKING_LABEL_TO_METRIC[ranking_label]
filtered_rows = [row for row in rows if int(row.get(metric_name, 0)) >= threshold][:top_n]
total_new_value = sum(int(row.get("new_entry_total_value_usd", 0)) for row in filtered_rows)
total_reduced_value = sum(int(row.get("reduced_total_value_usd", 0)) for row in filtered_rows)
holder_sum = sum(int(row.get("holder_manager_count", 0)) for row in filtered_rows)
best_rank = min((int(row.get("rank", 10_000)) for row in filtered_rows), default=0)

with st.container(horizontal=True):
    st.metric("Visible movers", format_int(len(filtered_rows)), border=True)
    st.metric("Visible new value", format_usd(total_new_value), border=True)
    st.metric("Visible reduced value", format_usd(total_reduced_value), border=True)
    st.metric("Holder managers sum", format_int(holder_sum), border=True)
    st.metric("Best visible rank", format_int(best_rank), border=True)

left_col, right_col = st.columns([1.55, 0.95], vertical_alignment="top")

with left_col:
    with st.container(border=True):
        st.subheader("Quarterly movers table")
        st.caption(
            "This page stays quarter-first: scan the cross-section, compare the current ranking, then jump into"
            " a single name only when the table gives you a reason."
        )
        if filtered_rows:
            movers_df = pd.DataFrame(
                [
                    {
                        "Rank": int(row.get("rank", 0)),
                        "Ticker": row.get("ticker", "-"),
                        "Issuer": row.get("issuer", "-"),
                        "CUSIP": row.get("cusip", "-"),
                        "Business summary": row.get("business_summary", "-"),
                        "New managers": int(row.get("new_manager_count", 0)),
                        "New entry value": format_usd(row.get("new_entry_total_value_usd", 0)),
                        "Reduced managers": int(row.get("reduced_manager_count", 0)),
                        "Reduced value": format_usd(row.get("reduced_total_value_usd", 0)),
                        "Holder managers": int(row.get("holder_manager_count", 0)),
                        "Total holding value": format_usd(row.get("total_holding_value_usd", 0)),
                    }
                    for row in filtered_rows
                ]
            )
            table_event = st.dataframe(
                movers_df,
                use_container_width=True,
                hide_index=True,
                key="quarterly_movers_table",
                on_select="rerun",
                selection_mode="single-row",
            )
            selected_index = resolve_selected_index("quarterly_movers_selected_index", len(filtered_rows), table_event)
            st.caption(
                f"Report period {report_period or '-'} · {security_type.upper()} universe"
                f" · {ranking_label.lower()} · rows {len(filtered_rows)}"
            )
            st.caption(f"Click a row to refresh the mover brief. Current selection #{selected_index + 1}.")
        else:
            st.info("No rows match the current quarterly movers filters.", icon=":material/info:")

with right_col:
    with st.container(border=True):
        st.subheader("Mover brief")
        if filtered_rows:
            selected_row = filtered_rows[st.session_state.get("quarterly_movers_selected_index", 0)]
            st.markdown(f"**{selected_row.get('issuer', '-') }**")
            st.caption(
                f"{selected_row.get('ticker', '-') or '-'} · {selected_row.get('cusip', '-')}"
                f" · {security_type.upper()} · {ranking_label}"
            )
            with st.container(horizontal=True):
                st.metric("Rank", format_int(selected_row.get("rank", 0)), border=True)
                st.metric("Signal", format_int(selected_row.get(metric_name, 0)), border=True)
                st.metric("Total value", format_usd(selected_row.get("total_holding_value_usd", 0)), border=True)
            st.info(_build_mover_headline(selected_row, ranking_label), icon=":material/insights:")
            st.caption(selected_row.get("business_summary", "No business summary."))
            detail_view = _coalesce_choice(
                st.segmented_control(
                    "Detail view",
                    options=["Why this quarter", "Appearances", "Links"],
                    default="Why this quarter",
                    key="quarterly_movers_detail_view",
                ),
                "Why this quarter",
            )

            if detail_view == "Why this quarter":
                period_rows = load_security_period_rows(
                    report_period,
                    str(selected_row.get("cusip", "")),
                    str(selected_row.get("security_type", "")),
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Ranking": RANKING_LABELS.get(str(row.get("ranking_type", "")), row.get("ranking_type", "-")),
                                "Rank": int(row.get("rank", 0)),
                                "New entry value": format_usd(row.get("new_entry_total_value_usd", 0)),
                                "Reduced value": format_usd(row.get("reduced_total_value_usd", 0)),
                                "Holder managers": int(row.get("holder_manager_count", 0)),
                                "Total holding value": format_usd(row.get("total_holding_value_usd", 0)),
                            }
                            for row in sorted(period_rows, key=lambda row: int(row.get("rank", 10_000)))
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                balance_df = pd.DataFrame(
                    [
                        {"metric": "New entry value", "value_usd": int(selected_row.get("new_entry_total_value_usd", 0))},
                        {"metric": "Reduced value", "value_usd": int(selected_row.get("reduced_total_value_usd", 0))},
                        {"metric": "Total value", "value_usd": int(selected_row.get("total_holding_value_usd", 0))},
                    ]
                )
                st.bar_chart(balance_df, x="metric", y="value_usd", use_container_width=True)
            elif detail_view == "Appearances":
                history_rows = load_security_history(
                    str(selected_row.get("cusip", "")),
                    str(selected_row.get("security_type", "")),
                )
                history_digest = build_security_history_digest(history_rows)
                if history_digest:
                    st.dataframe(
                        pd.DataFrame(
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
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(
                        f"Appeared in {len(history_digest)} tracked quarter(s). This tab stays lightweight on purpose;"
                        " use the 13F page for full single-name research."
                    )
                else:
                    st.caption("No quarter appearance history found for this mover.")
            else:
                st.page_link("app_pages/thirteenf.py", label="Open full 13F research page", icon=":material/open_in_new:")
                if security_type == "stock" and selected_row.get("ticker"):
                    related_8k = [
                        summarize_8k_row(row) for row in load_recent_8k(search_text=str(selected_row.get("ticker", "")), limit=5)
                    ]
                    if related_8k:
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Date": row.get("filing_date", "-"),
                                        "Form": row.get("form", "-"),
                                        "Items": ", ".join(row.get("item_codes", [])[:2]) or "-",
                                    }
                                    for row in related_8k
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("No recent 8-K rows for this ticker in the raw table.")
                else:
                    st.caption("8-K linkage is shown for stock mode only.")
        else:
            st.caption("Choose a report period and ranking to inspect movers.")
