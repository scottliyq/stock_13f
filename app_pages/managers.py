import pandas as pd
import streamlit as st

from stock_13f.ui import selection as selection_state
from stock_13f.ui.data_access import build_manager_13dg_monitor_rows
from stock_13f.ui.data_access import load_manager_profiles
from stock_13f.ui.data_access import load_manager_rebalance_snapshot
from stock_13f.ui.data_access import load_manager_snapshot
from stock_13f.ui.data_access import load_recent_13dg_by_manager
from stock_13f.ui.data_access import prewarm_manager_ui_cache
from stock_13f.ui.formatters import format_int
from stock_13f.ui.formatters import format_percent
from stock_13f.ui.formatters import format_usd


MANAGER_13DG_PAGE_LIMIT = 100


def _coalesce_choice(value: str | None, default: str) -> str:
    return value if value is not None else default


def _matches_rebalance_lens(row: dict[str, object], rebalance_lens: str) -> bool:
    status = str(row.get("status", "")).strip().lower()
    if rebalance_lens == "add":
        return status in {"new", "increased"}
    if rebalance_lens == "trim":
        return status in {"decreased", "exited"}
    return True


def _format_rebalance_status(status: object) -> str:
    mapping = {
        "new": "New",
        "increased": "Increased",
        "decreased": "Decreased",
        "exited": "Exited",
        "unchanged": "Unchanged",
    }
    return mapping.get(str(status).strip().lower(), str(status or "-"))


def _format_13dg_change_status(status: object) -> str:
    mapping = {
        "new": "New / initiated",
        "increased": "Increased",
        "decreased": "Decreased",
        "unchanged": "Unchanged",
    }
    return mapping.get(str(status).strip().lower(), str(status or "-"))


def _summarize_tickers(rows: list[dict[str, object]], limit: int = 5) -> str:
    tickers = [str(row.get("ticker", "")).strip().upper() for row in rows if str(row.get("ticker", "")).strip()]
    return ", ".join(tickers[:limit]) if tickers else "-"


def _manager_key(profile: dict[str, object]) -> str:
    return str(profile.get("manager_cik", "") or "").strip()


def _resolve_manager_selection(
    available_keys: list[str],
    selected_keys: list[object],
    *,
    allow_empty: bool,
) -> list[str]:
    resolver = getattr(selection_state, "resolve_multi_selection", None)
    if callable(resolver):
        return resolver(available_keys, selected_keys, allow_empty=allow_empty)

    available_set = set(available_keys)
    selected = [str(value).strip() for value in selected_keys if str(value).strip() in available_set]
    return selected if selected or allow_empty else available_keys


def _table_height(row_count: int, min_height: int = 180, max_height: int = 520) -> int:
    estimated_height = 44 + max(row_count, 1) * 36
    return min(max(estimated_height, min_height), max_height)


def _load_manager_card(
    profile: dict[str, object],
    selected_report_period: str,
    rebalance_lens: str,
) -> dict[str, object]:
    manager_cik = _manager_key(profile)
    rebalance_snapshot = load_manager_rebalance_snapshot(selected_report_period, manager_cik, top_n=None)
    changed_rows = [
        row
        for row in rebalance_snapshot.get("rows", [])
        if isinstance(row, dict) and _matches_rebalance_lens(row, rebalance_lens)
    ]
    changed_tickers = {
        str(row.get("ticker", "")).strip().upper()
        for row in changed_rows
        if str(row.get("ticker", "")).strip()
    }
    manager_13dg_rows = load_recent_13dg_by_manager(
        str(profile.get("manager_name", "") or ""),
        manager_cik,
        limit=MANAGER_13DG_PAGE_LIMIT,
    )
    status_counts = rebalance_snapshot.get("status_counts", {})
    return {
        "profile": profile,
        "rebalance_snapshot": rebalance_snapshot,
        "changed_rows": changed_rows,
        "changed_tickers": changed_tickers,
        "manager_13dg_rows": manager_13dg_rows,
        "new_or_add_count": int(status_counts.get("new", 0)) + int(status_counts.get("increased", 0)),
        "trim_count": int(status_counts.get("decreased", 0)) + int(status_counts.get("exited", 0)),
        "previous_report_period": str(rebalance_snapshot.get("previous_report_date", "") or "-"),
    }


def _build_combined_changed_rows(manager_cards: list[dict[str, object]]) -> list[dict[str, object]]:
    combined_rows: list[dict[str, object]] = []
    for card in manager_cards:
        profile = card["profile"]
        for row in card["changed_rows"]:
            combined_rows.append(
                {
                    "manager_name": str(profile.get("manager_name", "") or ""),
                    "manager_cik": _manager_key(profile),
                    **row,
                }
            )
    combined_rows.sort(
        key=lambda row: (
            -abs(int(row.get("value_change_usd", 0) or 0)),
            str(row.get("manager_name", "")),
            str(row.get("ticker", "")),
        )
    )
    return combined_rows


def _build_combined_monitor_rows(
    manager_cards: list[dict[str, object]],
    selected_report_period: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    monitor_rows: list[dict[str, object]] = []
    overlap_rows: list[dict[str, object]] = []
    for card in manager_cards:
        profile = card["profile"]
        manager_rows = build_manager_13dg_monitor_rows(
            card["manager_13dg_rows"],
            card["changed_rows"],
            selected_report_period,
            _manager_key(profile),
        )
        for row in manager_rows:
            enriched_row = {
                "manager_name": str(profile.get("manager_name", "") or ""),
                "manager_cik": _manager_key(profile),
                **row,
            }
            monitor_rows.append(enriched_row)
            if str(row.get("ticker", "")).strip().upper() in card["changed_tickers"]:
                overlap_rows.append(enriched_row)
    monitor_rows.sort(
        key=lambda row: (
            str(row.get("filing_date", "")),
            str(row.get("manager_name", "")),
            str(row.get("ticker", "")),
        ),
        reverse=True,
    )
    overlap_rows.sort(
        key=lambda row: (
            str(row.get("filing_date", "")),
            str(row.get("manager_name", "")),
            str(row.get("ticker", "")),
        ),
        reverse=True,
    )
    return monitor_rows, overlap_rows


def _build_manager_13dg_monitor_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Manager": row.get("manager_name", "-"),
                "Date": row.get("filing_date", "-"),
                "Ticker": row.get("ticker", "-"),
                "Form": row.get("form", "-"),
                "Company": row.get("company_name", "-"),
                "13D/G change": _format_13dg_change_status(row.get("filing_change_status", "")),
                "13D/G delta shares": format_int(row.get("filing_change_delta_shares", 0)),
                "13D/G delta %": format_percent(row.get("filing_change_delta_percent")),
                "Reported shares": format_int(row.get("reported_shares", 0)),
                "Ownership %": format_percent(row.get("reported_percent")),
                "13F action": _format_rebalance_status(row.get("rebalance_status", "")),
                "13F delta value": format_usd(row.get("rebalance_value_change_usd")),
                "13F current value": format_usd(row.get("rebalance_current_value_usd")),
            }
            for row in rows
        ]
    )


report_period = st.session_state.get("global_report_period", "")

profiles = load_manager_profiles()
snapshot = load_manager_snapshot()
manager_refs = tuple(
    (
        str(row.get("manager_name", "") or ""),
        str(row.get("manager_cik", "") or ""),
    )
    for row in profiles
    if _manager_key(row)
)
if report_period and manager_refs:
    prewarm_manager_ui_cache(report_period, manager_refs)

with st.container(border=True):
    col1, col2 = st.columns([1.25, 0.75], vertical_alignment="center")
    with col1:
        manager_search = st.text_input(
            "Manager search",
            value=st.session_state.get("managers_search", ""),
            placeholder="Ackman, Coatue, ARK, AI infra...",
            key="managers_search",
        )
    with col2:
        rebalance_lens = _coalesce_choice(
            st.segmented_control(
                "Rebalance lens",
                options=["all", "add", "trim"],
                default="all",
                format_func=lambda value: value.upper(),
                key="managers_rebalance_lens",
            ),
            "all",
        )

filtered_profiles = [
    row
    for row in profiles
    if manager_search.strip().lower() in str(row.get("manager_name", "")).lower()
    or manager_search.strip().lower() in str(row.get("focus_areas", "")).lower()
    or not manager_search.strip()
]

with st.container(horizontal=True):
    st.metric("Tracked managers", format_int(len(profiles)), border=True)
    st.metric("Filtered managers", format_int(len(filtered_profiles)), border=True)
    st.metric("Latest report period", str(snapshot.get("latest_report_period", "-") or "-"), border=True)
    available_periods = snapshot.get("available_report_periods", [])
    st.metric("Available periods", format_int(len(available_periods) if isinstance(available_periods, list) else 0), border=True)

left_col, right_col = st.columns([1.08, 1.17], vertical_alignment="top")

allow_empty_selection = bool(st.session_state.get("managers_allow_empty_selection", False))
selected_ciks = _resolve_manager_selection(
    [_manager_key(row) for row in filtered_profiles],
    st.session_state.get("managers_selected_ciks", []),
    allow_empty=allow_empty_selection,
)
st.session_state["managers_selected_ciks"] = selected_ciks

with left_col:
    with st.container(border=True):
        st.subheader("Tracked managers")
        if filtered_profiles:
            action_col1, action_col2, action_col3 = st.columns([0.9, 0.8, 1.5], vertical_alignment="center")
            with action_col1:
                if st.button("Select all filtered", use_container_width=True, key="managers_select_all"):
                    st.session_state["managers_selected_ciks"] = [_manager_key(row) for row in filtered_profiles]
                    st.session_state["managers_allow_empty_selection"] = False
                    st.rerun()
            with action_col2:
                if st.button("Clear", use_container_width=True, key="managers_clear_selection"):
                    st.session_state["managers_selected_ciks"] = []
                    st.session_state["managers_allow_empty_selection"] = True
                    st.rerun()
            with action_col3:
                st.caption(
                    f"Selected {len(st.session_state.get('managers_selected_ciks', []))} / {len(filtered_profiles)} manager(s)"
                )

            selection_df = pd.DataFrame(
                [
                    {
                        "Select": _manager_key(row) in st.session_state.get("managers_selected_ciks", []),
                        "CIK": row.get("manager_cik", "-"),
                        "Manager": row.get("manager_name", "-"),
                        "Focus areas": row.get("focus_areas", "-"),
                    }
                    for row in filtered_profiles
                ]
            )
            edited_df = st.data_editor(
                selection_df,
                use_container_width=True,
                hide_index=True,
                key="managers_table_editor",
                disabled=["CIK", "Manager", "Focus areas"],
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select"),
                },
            )
            selected_ciks = [
                str(row["CIK"]).strip()
                for _, row in edited_df.iterrows()
                if bool(row["Select"]) and str(row["CIK"]).strip()
            ]
            st.session_state["managers_selected_ciks"] = selected_ciks
            st.session_state["managers_allow_empty_selection"] = not bool(selected_ciks)
            st.caption("Use the checkbox column to compare one or multiple managers on the right.")
        else:
            st.info("No manager matches the current search.", icon=":material/info:")

selected_profiles = [row for row in filtered_profiles if _manager_key(row) in st.session_state.get("managers_selected_ciks", [])]

with right_col:
    with st.container(border=True):
        st.subheader("Latest manager rebalance")
        if selected_profiles:
            selected_report_period = report_period or str(snapshot.get("latest_report_period", "") or "")
            manager_cards = [_load_manager_card(profile, selected_report_period, rebalance_lens) for profile in selected_profiles]
            combined_changed_rows = _build_combined_changed_rows(manager_cards)
            unique_changed_tickers = {
                str(row.get("ticker", "")).strip().upper()
                for row in combined_changed_rows
                if str(row.get("ticker", "")).strip()
            }
            total_new_or_add = sum(int(card["new_or_add_count"]) for card in manager_cards)
            total_trim = sum(int(card["trim_count"]) for card in manager_cards)
            total_recent_13dg = sum(len(card["manager_13dg_rows"]) for card in manager_cards)

            if len(selected_profiles) == 1:
                selected_row = selected_profiles[0]
                manager_card = manager_cards[0]
                st.markdown(f"**{selected_row.get('manager_name', '-') }**")
                st.caption(
                    f"SEC CIK: {selected_row.get('manager_cik', '-')}"
                    f" · 13F compare: {selected_report_period or '-'} vs {manager_card['previous_report_period']}"
                )
            else:
                selected_names = [str(profile.get("manager_name", "") or "") for profile in selected_profiles]
                st.markdown(f"**{len(selected_profiles)} managers selected**")
                st.caption(
                    f"Combined view for {', '.join(selected_names[:4])}"
                    + (" ..." if len(selected_names) > 4 else "")
                    + f" · report period {selected_report_period or '-'}"
                )

            metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
            metric_col1.metric("Changed tickers", format_int(len(unique_changed_tickers)), border=True)
            metric_col2.metric("New / increased", format_int(total_new_or_add), border=True)
            metric_col3.metric("Reduced / exited", format_int(total_trim), border=True)
            metric_col4.metric("Recent 13D/G", format_int(total_recent_13dg), border=True)

            detail_view = _coalesce_choice(
                st.segmented_control(
                    "Detail view",
                    options=["Summary", "13F tickers", "13D/G monitor"],
                    default="Summary",
                    key="managers_detail_view",
                ),
                "Summary",
            )

            if detail_view == "Summary":
                if len(selected_profiles) == 1:
                    manager_card = manager_cards[0]
                    changed_rows = manager_card["changed_rows"]
                    manager_13dg_rows = manager_card["manager_13dg_rows"]
                    changed_tickers = manager_card["changed_tickers"]
                    if changed_rows:
                        add_rows = [
                            row for row in changed_rows if str(row.get("status", "")).strip().lower() in {"new", "increased"}
                        ]
                        trim_rows = [
                            row for row in changed_rows if str(row.get("status", "")).strip().lower() in {"decreased", "exited"}
                        ]
                        st.markdown("**13F rebalance readout**")
                        st.write(
                            f"Selected manager shows {len(changed_rows)} recent rebalance tickers for {selected_report_period or '-'} "
                            f"versus {manager_card['previous_report_period']}. New/increased: {_summarize_tickers(add_rows)}. "
                            f"Reduced/exited: {_summarize_tickers(trim_rows)}."
                        )
                        if manager_13dg_rows:
                            manager_event_tickers = sorted(
                                {
                                    str(row.get("ticker", "")).strip().upper()
                                    for row in manager_13dg_rows
                                    if str(row.get("ticker", "")).strip()
                                }
                            )
                            st.write("Recent manager 13D/G filings: " + ", ".join(manager_event_tickers[:8]) + ".")
                            matched_tickers = sorted(changed_tickers.intersection(manager_event_tickers))
                            if matched_tickers:
                                st.write("Recent 13D/G overlap on changed tickers: " + ", ".join(matched_tickers[:8]) + ".")
                            else:
                                st.caption("Recent manager 13D/G filings were found, but none overlap with the current 13F rebalance ticker set.")
                        else:
                            st.caption("No recent manager 13D/G rows were found for the selected institution.")
                    else:
                        st.caption("No rebalance tickers matched the selected manager and current lens.")
                else:
                    manager_13dg_monitor_rows, _ = _build_combined_monitor_rows(
                        manager_cards,
                        selected_report_period,
                    )
                    st.markdown("**All selected manager 13D/G timeline**")
                    st.write(
                        f"Showing recent 13D/G filings for all selected managers with the same fields as the single-manager view, ordered by filing date for report period {selected_report_period or '-'}."
                    )
                    if manager_13dg_monitor_rows:
                        manager_13dg_monitor_df = _build_manager_13dg_monitor_df(manager_13dg_monitor_rows)
                        st.dataframe(
                            manager_13dg_monitor_df,
                            use_container_width=True,
                            hide_index=True,
                            height=_table_height(len(manager_13dg_monitor_df), min_height=260, max_height=520),
                        )
                    else:
                        st.caption("No recent manager 13D/G rows were found for the selected manager set.")

            elif detail_view == "13F tickers":
                if combined_changed_rows:
                    rebalance_df = pd.DataFrame(
                        [
                            {
                                "Manager": row.get("manager_name", "-"),
                                "Ticker": row.get("ticker", "-"),
                                "Issuer": row.get("issuer", "-"),
                                "Action": _format_rebalance_status(row.get("status", "")),
                                "Prev value": format_usd(row.get("previous_value_usd", 0)),
                                "Current value": format_usd(row.get("current_value_usd", 0)),
                                "Delta": format_usd(row.get("value_change_usd", 0)),
                            }
                            for row in combined_changed_rows
                        ]
                    )
                    st.dataframe(
                        rebalance_df,
                        use_container_width=True,
                        hide_index=True,
                        height=_table_height(len(rebalance_df), min_height=240, max_height=560),
                    )
                    chart_df = pd.DataFrame(
                        [
                            {
                                "label": f"{row.get('manager_name', '-')}: {row.get('ticker', '-')}",
                                "value_change_usd": int(row.get("value_change_usd", 0)),
                            }
                            for row in combined_changed_rows[:12]
                        ]
                    )
                    st.bar_chart(chart_df, x="label", y="value_change_usd", use_container_width=True)
                else:
                    st.caption("No rebalance tickers matched the selected managers and current lens.")
            else:
                manager_13dg_monitor_rows, related_13dg_monitor_rows = _build_combined_monitor_rows(
                    manager_cards,
                    selected_report_period,
                )
                if manager_13dg_monitor_rows:
                    st.markdown("**Recent manager 13D/G filings**")
                    st.caption("13D/G rows show current disclosed shares and ownership %. 13F columns are cross-checked against the latest report-period holding for the same manager and ticker. `Not reported` means the ticker was not found in the latest 13F quarter.")
                    manager_13dg_monitor_df = _build_manager_13dg_monitor_df(manager_13dg_monitor_rows)
                    st.dataframe(
                        manager_13dg_monitor_df,
                        use_container_width=True,
                        hide_index=True,
                        height=_table_height(len(manager_13dg_monitor_df), min_height=260, max_height=520),
                    )
                    if related_13dg_monitor_rows:
                        st.markdown("**Overlap with current 13F rebalance tickers**")
                        related_13dg_monitor_df = _build_manager_13dg_monitor_df(related_13dg_monitor_rows)
                        st.dataframe(
                            related_13dg_monitor_df,
                            use_container_width=True,
                            hide_index=True,
                            height=_table_height(len(related_13dg_monitor_df), min_height=220, max_height=420),
                        )
                    else:
                        st.caption("No manager 13D/G filings currently overlap with the selected 13F rebalance tickers.")
                else:
                    st.caption("No recent manager 13D/G rows were found for the selected manager set.")
        else:
            st.caption("Select one or more managers to inspect the latest rebalance analysis.")
