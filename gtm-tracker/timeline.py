"""The shared timeline selector's choices, resolved to an inclusive (start, end) day range. Pure functions, no Streamlit."""
from datetime import timedelta

CHOICES = ["Last 7 days", "Last 30 days", "Last 90 days", "This month", "Last month", "Custom"]
DEFAULT_CHOICE = "Last 30 days"
_LAST = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}


def resolve(choice, as_of, custom=None):
    """(start, end) for a choice; `as_of` is the newest day with data. Custom needs (start, end) with start <= end <= as_of, else ValueError."""
    if choice in _LAST:
        return as_of - timedelta(days=_LAST[choice] - 1), as_of
    if choice == "This month":
        return as_of.replace(day=1), as_of
    if choice == "Last month":
        end = as_of.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if choice == "Custom":
        if not custom or len(custom) != 2:
            raise ValueError("Pick a start and an end day.")
        start, end = custom
        if start > end:
            raise ValueError("The start day is after the end day.")
        if end > as_of:
            raise ValueError(f"The data ends on {as_of:%d %b %Y}; pick an end day on or before it.")
        return start, end
    raise ValueError(f"Unknown timeline choice {choice!r}")
