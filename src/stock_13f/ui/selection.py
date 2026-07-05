"""Helpers for single-row selection state across Streamlit pages."""

from typing import Any

import streamlit as st


def resolve_selected_index(
    state_key: str,
    row_count: int,
    dataframe_event: Any,
) -> int:
    """Keep a stable selected row index across reruns and filter changes."""

    if row_count <= 0:
        st.session_state.pop(state_key, None)
        return 0
    selected_rows = getattr(getattr(dataframe_event, "selection", None), "rows", []) or []
    if selected_rows:
        index = int(selected_rows[0])
        st.session_state[state_key] = max(0, min(index, row_count - 1))
        return st.session_state[state_key]
    current_index = int(st.session_state.get(state_key, 0) or 0)
    if current_index >= row_count:
        current_index = 0
    st.session_state[state_key] = current_index
    return current_index
