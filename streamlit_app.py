from pathlib import Path
import sys

import streamlit as st


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stock_13f.ui.data_access import get_settings
from stock_13f.ui.data_access import get_supabase_client
from stock_13f.ui.data_access import load_checkpoint_statuses
from stock_13f.ui.data_access import load_report_periods
from stock_13f.ui.data_access import prewarm_core_ui_cache


st.set_page_config(
    page_title="13F research terminal",
    page_icon=":material/query_stats:",
    layout="wide",
)


def initialize_state() -> None:
    report_periods = load_report_periods()
    default_period = report_periods[0] if report_periods else ""
    st.session_state.setdefault("global_report_period", default_period)
    st.session_state.setdefault("global_ticker_search", "")
    if default_period:
        prewarm_core_ui_cache(default_period)


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(164, 196, 255, 0.16), transparent 28%),
                linear-gradient(180deg, #f5f7fb 0%, #eef3f8 100%);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
            border-right: 1px solid rgba(15, 23, 42, 0.08);
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }
        .research-kicker {
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-size: 0.75rem;
            font-weight: 700;
            color: #355c7d;
        }
        .research-note {
            color: #5b6472;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    settings = get_settings()
    client = get_supabase_client()
    statuses = load_checkpoint_statuses()
    with st.sidebar:
        st.markdown("**Research workspace**")
        st.caption("13F / 8-K / 13D-G institution monitor")
        st.caption(f"Repo: `{settings.paths.repo_root.name}`")
        st.caption(f"Supabase: {'connected' if client is not None else 'missing config'}")
        if statuses:
            st.caption("Latest jobs")
            for status in sorted(statuses, key=lambda item: str(item.get("finished_at", "")), reverse=True)[:4]:
                st.caption(
                    f"{status.get('job_name', '-')}: {status.get('status', '-')}"
                    f" · {status.get('finished_at', '-')}"
                )
        else:
            st.caption("No sync status recorded yet.")
        st.caption("Version: UI skeleton v1")


def render_global_filters(page_title: str) -> None:
    report_periods = load_report_periods()
    supported_pages = {"Dashboard", "13F", "Quarterly movers", "Managers"}
    if page_title not in supported_pages:
        return
    with st.container(border=True):
        col1, col2, col3 = st.columns([1.2, 1.3, 1.0], vertical_alignment="center")
        with col1:
            if report_periods:
                current_period = st.session_state.get("global_report_period", report_periods[0])
                if current_period not in report_periods:
                    current_period = report_periods[0]
                selected_period = st.selectbox(
                    "Report period",
                    options=report_periods,
                    index=report_periods.index(current_period),
                    key="global_report_period_select",
                )
                st.session_state["global_report_period"] = selected_period
            else:
                st.text_input("Report period", value="No period available", disabled=True)
        with col2:
            st.session_state["global_ticker_search"] = st.text_input(
                "Ticker search",
                value=st.session_state.get("global_ticker_search", ""),
                placeholder="AAPL, NVDA, Amazon, semiconductor...",
            )
        with col3:
            st.markdown('<div class="research-kicker">Focus</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="research-note">Use the shared report period to keep dashboard, 13F and manager research aligned.</div>',
                unsafe_allow_html=True,
            )


initialize_state()
inject_app_styles()

pages = {
    "Research": [
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
        st.Page("app_pages/thirteenf.py", title="13F", icon=":material/stacked_line_chart:"),
        st.Page("app_pages/quarterly_movers.py", title="Quarterly movers", icon=":material/table_chart:"),
    ],
    "Events": [
        st.Page("app_pages/eightk.py", title="8-K", icon=":material/news:"),
        st.Page("app_pages/thirteendg.py", title="13D/G", icon=":material/flag:"),
    ],
    "Coverage": [
        st.Page("app_pages/managers.py", title="Managers", icon=":material/groups:"),
    ],
}

page = st.navigation(pages, position="sidebar")
render_sidebar()
st.title(f"{page.icon} {page.title}")
render_global_filters(page.title)
page.run()
