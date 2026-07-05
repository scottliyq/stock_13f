"""Formatting helpers for the Streamlit research UI."""


def format_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "-"


def format_percent(value: object) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "-"


def format_usd(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    abs_number = abs(number)
    if abs_number >= 1_000_000_000:
        return f"${number / 1_000_000_000:.1f}B"
    if abs_number >= 1_000_000:
        return f"${number / 1_000_000:.1f}M"
    if abs_number >= 1_000:
        return f"${number / 1_000:.1f}K"
    return f"${number:,.0f}"


def normalize_text(value: object) -> str:
    return str(value or "").strip().lower()
