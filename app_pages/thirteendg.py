import streamlit as st

from stock_13f.ui.data_access import build_13dg_reporting_person_changes
from stock_13f.ui.data_access import load_13dg_chain
from stock_13f.ui.data_access import load_recent_13dg
from stock_13f.ui.data_access import summarize_13dg_row
from stock_13f.ui.selection import resolve_selected_index


global_search = st.session_state.get("global_ticker_search", "")

with st.container(border=True):
    col1, col2 = st.columns([1.1, 0.9], vertical_alignment="center")
    with col1:
        page_search = st.text_input("Ticker or company search", value=global_search, key="thirteendg_search")
    with col2:
        row_limit = st.selectbox("Rows", options=[25, 50, 100, 200], index=1, key="thirteendg_rows")

rows = load_recent_13dg(search_text=page_search, limit=row_limit)

left_col, right_col = st.columns([1.15, 1.0], vertical_alignment="top")

with left_col:
    with st.container(border=True):
        st.subheader("13D/G event feed")
        if rows:
            table_event = st.dataframe(
                [
                    {
                        "Date": row.get("filing_date", "-"),
                        "Ticker": row.get("ticker", "-"),
                        "Form": row.get("form", "-"),
                        "Company": row.get("company_name", "-"),
                    }
                    for row in rows
                ],
                use_container_width=True,
                hide_index=True,
                key="thirteendg_feed_table",
                on_select="rerun",
                selection_mode="single-row",
            )
            selected_index = resolve_selected_index("thirteendg_selected_index", len(rows), table_event)
            st.caption(f"Click a row to update the right-side filing detail. Current selection #{selected_index + 1}.")
        else:
            st.info("The current 30-day sync returned no 13D/G rows.", icon=":material/info:")

with right_col:
    with st.container(border=True):
        st.subheader("Beneficial ownership detail")
        if rows:
            selected_row = rows[st.session_state.get("thirteendg_selected_index", 0)]
            detail = summarize_13dg_row(selected_row)
            chain_rows = load_13dg_chain(
                str(detail.get("ticker", "")),
                str(detail.get("form_family", "")),
                str(detail.get("issuer_cusip", "")),
                str(detail.get("issuer_name", "")),
                limit=20,
            )
            selected_accession = str(detail.get("accession_number", ""))
            selected_chain_index = 0
            for index, chain_row in enumerate(chain_rows):
                if str(chain_row.get("accession_number", "")) == selected_accession:
                    selected_chain_index = index
                    break
            previous_detail = chain_rows[selected_chain_index + 1] if selected_chain_index + 1 < len(chain_rows) else None
            reporting_person_changes = build_13dg_reporting_person_changes(detail, previous_detail)
            st.markdown(f"**{detail.get('company_name', '-') }**")
            st.caption(
                f"Ticker: {detail.get('ticker', '-') or '-'}"
                f" · Form: {detail.get('form', '-')}"
                f" · Filing date: {detail.get('filing_date', '-')}"
            )
            top_col1, top_col2, top_col3, top_col4 = st.columns(4)
            with top_col1:
                st.metric(
                    "Total beneficial shares",
                    f"{int(detail['total_shares']):,}" if detail.get("total_shares") else "-",
                    border=True,
                )
            with top_col2:
                st.metric(
                    "Percent of class",
                    f"{float(detail['total_percent']):g}%" if detail.get("total_percent") is not None else "-",
                    border=True,
                )
            with top_col3:
                st.metric("Reporting persons", len(detail.get("reporting_persons", [])), border=True)
            with top_col4:
                st.metric("Passive flag", "Yes" if detail.get("is_passive_investor") else "No", border=True)

            st.info(
                str(detail.get("summary_text", "Beneficial ownership event synced from Schedule 13D/G feed.")),
                icon=":material/insights:",
            )
            if detail.get("filing_url"):
                st.link_button("Open SEC filing", str(detail["filing_url"]), use_container_width=True)

            overview_tab, persons_tab, purpose_tab, chain_tab = st.tabs(
                ["Overview", "Reporting persons", "Purpose", "Amendment chain"]
            )

            with overview_tab:
                meta_parts = []
                if detail.get("issuer_name"):
                    meta_parts.append(str(detail.get("issuer_name")))
                if detail.get("issuer_cik"):
                    meta_parts.append(f"Issuer CIK {detail.get('issuer_cik')}")
                if detail.get("issuer_cusip"):
                    meta_parts.append(f"CUSIP {detail.get('issuer_cusip')}")
                if detail.get("security_title"):
                    meta_parts.append(str(detail.get("security_title")))
                if detail.get("event_date"):
                    meta_parts.append(f"Event date {detail.get('event_date')}")
                if detail.get("rule_designation"):
                    meta_parts.append(str(detail.get("rule_designation")))
                if detail.get("is_amendment"):
                    amendment_text = "Amendment"
                    if detail.get("amendment_number"):
                        amendment_text += f" #{detail.get('amendment_number')}"
                    meta_parts.append(amendment_text)
                if meta_parts:
                    st.caption(" · ".join(meta_parts))
                st.dataframe(
                    [
                        {"Field": "Issuer", "Value": detail.get("issuer_name", "-") or "-"},
                        {"Field": "Issuer CIK", "Value": detail.get("issuer_cik", "-") or "-"},
                        {"Field": "CUSIP", "Value": detail.get("issuer_cusip", "-") or "-"},
                        {"Field": "Security title", "Value": detail.get("security_title", "-") or "-"},
                        {"Field": "Rule", "Value": detail.get("rule_designation", "-") or "-"},
                        {"Field": "Event date", "Value": detail.get("event_date", "-") or "-"},
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

            with persons_tab:
                reporting_persons = detail.get("reporting_persons", [])
                if reporting_persons:
                    st.dataframe(
                        [
                            {
                                "Name": person.get("name", "-"),
                                "Type": person.get("type_of_reporting_person", "-") or "-",
                                "Percent": f"{float(person['percent_of_class']):g}%" if person.get("percent_of_class") is not None else "-",
                                "Shares": f"{int(person['aggregate_amount']):,}" if person.get("aggregate_amount") else "-",
                                "Sole vote": f"{int(person['sole_voting_power']):,}" if person.get("sole_voting_power") else "-",
                                "Shared vote": f"{int(person['shared_voting_power']):,}" if person.get("shared_voting_power") else "-",
                            }
                            for person in reporting_persons
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                    for person in reporting_persons:
                        extra_parts = []
                        if person.get("citizenship"):
                            extra_parts.append(f"Citizenship {person.get('citizenship')}")
                        if person.get("sole_dispositive_power"):
                            extra_parts.append(f"Sole dispositive {int(person['sole_dispositive_power']):,}")
                        if person.get("shared_dispositive_power"):
                            extra_parts.append(f"Shared dispositive {int(person['shared_dispositive_power']):,}")
                        if person.get("comment"):
                            extra_parts.append(str(person.get("comment")))
                        if extra_parts:
                            st.caption(f"{person.get('name', '-')}: " + " · ".join(extra_parts))
                else:
                    st.caption("No structured reporting-person detail is available for this filing yet.")

            with purpose_tab:
                if detail.get("purpose_text"):
                    st.write(str(detail.get("purpose_text")))
                else:
                    st.caption("This filing does not include a parsed Item 4 / purpose summary in the current payload.")

            with chain_tab:
                if chain_rows:
                    st.dataframe(
                        [
                            {
                                "Selected": "Yes" if index == selected_chain_index else "",
                                "Filing date": chain_row.get("filing_date", "-"),
                                "Form": chain_row.get("form", "-"),
                                "Event date": chain_row.get("event_date", "-"),
                                "Rule": chain_row.get("rule_designation", "-"),
                                "Amendment": "Yes" if chain_row.get("is_amendment") else "No",
                                "Percent": (
                                    f"{float(chain_row['total_percent']):g}%"
                                    if chain_row.get("total_percent") is not None
                                    else "-"
                                ),
                                "Reporting persons": len(chain_row.get("reporting_persons", [])),
                            }
                            for index, chain_row in enumerate(chain_rows)
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                    if previous_detail is not None:
                        st.markdown("**Reporting person delta vs previous filing**")
                        st.caption(
                            f"Comparing {detail.get('filing_date', '-')} against previous filing {previous_detail.get('filing_date', '-')}"
                        )
                        st.dataframe(
                            [
                                {
                                    "Name": row.get("name", "-"),
                                    "Type": row.get("type_of_reporting_person", "-") or "-",
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
                                    "Delta %": (
                                        f"{float(row['delta_percent']):+.2f}pp"
                                        if row.get("delta_percent") is not None
                                        else "-"
                                    ),
                                    "Current shares": f"{int(row['current_shares']):,}" if row.get("current_shares") else "-",
                                    "Previous shares": f"{int(row['previous_shares']):,}" if row.get("previous_shares") else "-",
                                    "Delta shares": f"{int(row['delta_shares']):+,}" if row.get("delta_shares") else "-",
                                }
                                for row in reporting_person_changes
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("No older filing from the same 13D/G family is available yet, so there is no amendment comparison baseline.")
                else:
                    st.caption("No amendment chain could be constructed for this filing.")
        else:
            st.caption("Select a row on the left once 13D/G rows are available.")
