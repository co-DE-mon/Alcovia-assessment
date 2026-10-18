"""Number, money and date text for the dashboard and the verdict reasons. Pure functions; a missing value (None or NaN) always reads as a dash."""
import pandas as pd

DASH = "–"


def missing(x):
    return x is None or x != x          # None or NaN (pandas turns a missing number into NaN)


def inr(x):
    """Rupees with Indian digit grouping: 1234567 -> ₹12,34,567."""
    if missing(x):
        return DASH
    n = int(round(x))
    sign, digits = ("-" if n < 0 else ""), str(abs(n))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}" if groups else f"{sign}₹{tail}"


def pct(x, digits=1):
    return DASH if missing(x) else f"{x * 100:.{digits}f}%"


def dec(x, digits=2):
    return DASH if missing(x) else f"{x:.{digits}f}"


def change(x, digits=1):
    """A fractional change with its sign: -0.153 -> -15.3%."""
    return DASH if missing(x) else f"{x * 100:+.{digits}f}%"


def date(x):
    """A date or timestamp as 12 Oct 2026; a missing one is a dash."""
    return DASH if missing(x) else f"{pd.Timestamp(x):%d %b %Y}"


def num(x):
    return DASH if missing(x) else f"{int(round(x)):,}"
