import streamlit as st

from stock_13f.ui.data_access import load_recent_8k
from stock_13f.ui.data_access import summarize_8k_row
from stock_13f.ui.selection import resolve_selected_index


global_search = st.session_state.get("global_ticker_search", "")

with st.container(border=True):
    col1, col2 = st.columns([1.1, 0.9], vertical_alignment="center")
    with col1:
        page_search = st.text_input("Ticker or company search", value=global_search, key="eightk_search")
    with col2:
        row_limit = st.selectbox("Rows", options=[25, 50, 100, 200], index=1)

rows = load_recent_8k(search_text=page_search, limit=row_limit)

left_col, right_col = st.columns([1.15, 1.0], vertical_alignment="top")

with left_col:
    with st.container(border=True):
        st.subheader("8-K event feed")
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
                key="eightk_feed_table",
                on_select="rerun",
                selection_mode="single-row",
            )
            selected_index = resolve_selected_index("eightk_selected_index", len(rows), table_event)
            st.caption(f"Click a row to update the right-side filing detail. Current selection #{selected_index + 1}.")
        else:
            st.info("No 8-K rows match the current filter.", icon=":material/info:")

with right_col:
    with st.container(border=True):
        st.subheader("Filing detail")
        if rows:
            selected_row = rows[st.session_state.get("eightk_selected_index", 0)]
            detail = summarize_8k_row(selected_row)
            st.markdown(f"**{detail.get('company_name', '-') }**")
            st.caption(
                f"Ticker: {detail.get('ticker', '-') or '-'}"
                f" · Form: {detail.get('form', '-')}"
                f" · Filing date: {detail.get('filing_date', '-')}"
            )
            with st.container(horizontal=True):
                st.metric("Items", len(detail.get("item_codes", [])), border=True)
                st.metric("Attachments", len(detail.get("exhibits", [])), border=True)
                st.metric("Press release", "Yes" if detail.get("has_press_release") else "No", border=True)
                st.metric("Earnings", "Yes" if detail.get("has_earnings") else "No", border=True)
            st.caption(detail.get("summary_text", ""))
            if detail.get("period_of_report") or detail.get("date_of_report"):
                st.caption(
                    f"Period of report: {detail.get('period_of_report', '-') or '-'}"
                    f" · Date of report: {detail.get('date_of_report', '-') or '-'}"
                )
            if detail.get("filing_url"):
                st.link_button("Open SEC filing", str(detail["filing_url"]), use_container_width=True)

            items_tab, exhibits_tab = st.tabs(["Items", "Attachments"])
            with items_tab:
                if detail.get("items"):
                    for item in detail["items"]:
                        with st.expander(str(item.get("code", "Item")), expanded=False):
                            st.write(item.get("text", ""))
                elif detail.get("item_codes"):
                    st.write(", ".join(str(code) for code in detail["item_codes"]))
                    st.info("This filing has item codes, but the synced payload does not yet include full item text.")
                else:
                    st.info("No parsed item text is available for this filing yet.", icon=":material/info:")
            with exhibits_tab:
                if detail.get("exhibits"):
                    st.dataframe(
                        [
                            {
                                "Seq": exhibit.get("sequence_number", "-"),
                                "Document": exhibit.get("document", "-"),
                                "Type": exhibit.get("document_type", "-"),
                                "Description": exhibit.get("description", "-"),
                                "Purpose": exhibit.get("purpose", "-"),
                            }
                            for exhibit in detail["exhibits"]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("No attachment metadata was parsed for this filing.")
        else:
            st.caption("Select a row on the left to inspect the filing detail.")
