from pathlib import Path

import streamlit as st

from stock_13f.ui.data_access import list_markdown_reports


report_paths = list_markdown_reports()

left_col, right_col = st.columns([0.95, 1.15], vertical_alignment="top")

with left_col:
    with st.container(border=True):
        st.subheader("Markdown reports")
        if report_paths:
            st.dataframe(
                [
                    {
                        "Name": path.name,
                        "Directory": str(path.parent.relative_to(Path.cwd())),
                    }
                    for path in report_paths
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No markdown reports were found under the reports directory.", icon=":material/info:")

with right_col:
    with st.container(border=True):
        st.subheader("Preview")
        if report_paths:
            options = {str(path.relative_to(Path.cwd())): path for path in report_paths}
            selected_label = st.selectbox("Report", options=list(options))
            selected_path = options[selected_label]
            st.caption(str(selected_path))
            st.markdown(selected_path.read_text(encoding="utf-8"))
        else:
            st.caption("Select a report after markdown outputs are generated.")
