"""Altair charts in one style. Colours are the validated categorical order (blue, orange, aqua, yellow, magenta, green), assigned to an entity in a fixed
order and never cycled; status colours are reserved for ui.chip and never used here. Every chart is paired with a table view by table_view()."""
import altair as alt
import pandas as pd
import streamlit as st

SERIES = ["#6b97d4", "#e8845c", "#38aea6", "#d4a038", "#d98ab0", "#74a468"]       # soft categorical palette; charts also use labels and table views
INK, MUTED, GRID = "#2a3a4d", "#5d6b7c", "#edf0f5"
KIND_DOMAIN = ["program", "workshop"]            # program is always blue, workshop always orange


def short(campaign_id):
    return str(campaign_id).replace("DEMO-C-", "")


def bridge_steps(parts):
    """The path from this period's sign-ups to the achieved number, from the rows of the cash_breakdown query:
    contract value of the new sign-ups, minus what is not collected yet, plus what earlier students paid, plus workshop seats, equals Achieved.
    Each step has a label, a kind (total, down or up), start, end and the signed value."""
    students = [p for p in parts if p["stream"] != "Workshop seats"]
    workshop = sum(p["amount"] for p in parts if p["stream"] == "Workshop seats")
    contract = sum(p["contract"] for p in students)
    not_collected = sum(p["not_collected"] for p in students)
    earlier = sum(p["earlier"] for p in students)
    steps, level = [dict(label="Contract value of new sign-ups", kind="total", start=0, end=contract, value=contract)], contract
    for label, kind, value in (("Not collected yet", "down", -not_collected), ("Paid by earlier students", "up", earlier), ("Workshop seats", "up", workshop)):
        steps.append(dict(label=label, kind=kind, start=level, end=level + value, value=value))
        level += value
    steps.append(dict(label="Achieved", kind="total", start=0, end=level, value=level))
    return steps


LAKH_AXIS = "format(datum.value / 100000, ',.0f') + 'L'"       # axis labels in lakhs, as everywhere else on the page


def bridge_bar_rows(steps):
    """Plain bars for bridge_steps: every bar is its own amount, drawn from zero (not a running total). Totals are the contract value and Achieved;
    the three parts in between are shown as positive amounts, and the caption says which are taken away and which are added."""
    return [dict(label=s["label"], amount=abs(s["value"]), role="total" if s["kind"] == "total" else "part",
                 text=f"₹{abs(s['value']) / 100000:,.1f}L") for s in steps]


def bridge_bars(steps):
    """The bridge as zero-based bars with a value label on each: blue for the two totals, teal for the three parts between them."""
    df = pd.DataFrame(bridge_bar_rows(steps))
    order = list(df["label"])
    base = alt.Chart(df).encode(x=alt.X("label:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, labelLimit=170)))
    bars = base.mark_bar(size=54, cornerRadiusEnd=4).encode(
        y=alt.Y("amount:Q", title=None, axis=alt.Axis(labelExpr=LAKH_AXIS, tickMinStep=100000)),
        color=alt.Color("role:N", scale=alt.Scale(domain=["total", "part"], range=[SERIES[0], SERIES[2]]), legend=None),
        tooltip=[alt.Tooltip("label:N"), alt.Tooltip("text:N", title="Amount")])
    labels = base.mark_text(dy=-9, color=INK, fontSize=12).encode(y="amount:Q", text="text:N")
    show(bars + labels, height=300)


def label_format(fmt):
    """The format for the value written at the end of a bar: SI-style amounts (~s) get three significant figures, so 89281.5 reads 89.3k, not 89.2815k."""
    return ".3~s" if fmt == "~s" else fmt


def whole_ticks(values):
    """True when every value is a whole number and the largest is small (10 or less): the axis then ticks on 1, 2, 3 rather than 0.2, 0.4."""
    values = [v for v in values if v is not None]
    return bool(values) and max(values) <= 10 and all(float(v).is_integer() for v in values)


def _axis(values, fmt, grid=True):
    return alt.Axis(grid=grid, format="d", tickMinStep=1) if whole_ticks(values) else alt.Axis(grid=grid, format=fmt)


def show(chart, height=240):
    chart = (chart.properties(height=height).configure_view(stroke=None).configure(background="transparent")
             .configure_axis(domain=False, ticks=False, gridColor=GRID, labelColor=MUTED, titleColor=MUTED, labelFontSize=12, titleFontSize=12, labelLimit=260)
             .configure_legend(orient="bottom", labelColor=INK, labelFontSize=12, title=None, symbolType="stroke"))
    st.altair_chart(chart, width="stretch", theme=None)


def hbars(df, label, value, text=None, color=None, domain=None, fmt=","):
    """Horizontal bars in the frame's row order, each with a value label at its end, with air between the bars. `color` names a column that picks the fixed hue."""
    if df.empty:
        st.info("Nothing to chart for this period.")
        return
    base = alt.Chart(df).encode(y=alt.Y(f"{label}:N", sort=None, title=None, scale=alt.Scale(paddingInner=0.45, paddingOuter=0.15)),
                                x=alt.X(f"{value}:Q", title=None, axis=_axis(list(df[value]), fmt)))
    enc = {}
    if color:
        enc["color"] = alt.Color(f"{color}:N", scale=alt.Scale(domain=domain, range=SERIES[:len(domain)]), legend=None)
    bars = base.mark_bar(size=24, cornerRadiusEnd=4, color=SERIES[0]).encode(**enc, tooltip=list(df.columns))
    labels = base.mark_text(align="left", dx=6, color=INK, fontSize=12).encode(text=alt.Text(f"{text or value}:{'N' if text else 'Q'}", format=label_format(fmt) if not text else ""))
    show(bars + labels, height=56 * len(df) + 40)


def columns(df, x, y, fmt=","):
    """Vertical bars over an ordered label column."""
    if df.empty:
        st.info("Nothing to chart for this period.")
        return
    base = alt.Chart(df).encode(x=alt.X(f"{x}:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y(f"{y}:Q", title=None, axis=_axis(list(df[y]), fmt)))
    bars = base.mark_bar(size=36, cornerRadiusEnd=4, color=SERIES[0]).encode(tooltip=list(df.columns))
    show(bars, height=240)


def lines(df, x, y, series, fmt=".1%"):
    """One line per series, hues in the order the series appear. The legend names every line."""
    if df.empty:
        st.info("Nothing to chart for this period.")
        return
    domain = list(dict.fromkeys(df[series]))
    chart = alt.Chart(df).mark_line(strokeWidth=2).encode(
        x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%d %b")), y=alt.Y(f"{y}:Q", title=None, axis=alt.Axis(format=fmt)),
        color=alt.Color(f"{series}:N", scale=alt.Scale(domain=domain, range=SERIES[:len(domain)])), tooltip=list(df.columns))
    show(chart, height=280)


def table_view(df, label="Table view"):
    with st.expander(label):
        st.dataframe(df, hide_index=True, width="stretch")
