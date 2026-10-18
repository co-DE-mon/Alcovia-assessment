"""Helpers shared by the pages."""
import pandas as pd
import streamlit as st

import data
import drill
import metrics
import scorecard
import ui


def show(html):
    st.markdown(html, unsafe_allow_html=True)


def table_height(n, cap=520):
    """Pixel height of a dataframe with n rows, capped so a long table scrolls instead of stretching the page."""
    return min(35 * (n + 1) + 3, cap)


def window_of(cadence):
    return next(k.window for k in scorecard.KPIS if k.cadence == cadence)


def window_text(cfg, end, window):
    start, q_start = scorecard.windows(cfg, end)
    if window == "period":
        return f"Last {cfg['scorecard']['window_days']} days: {ui.fmt_short(start)} – {ui.fmt_date(end)}"
    quarter = metrics.quarter_for(end, cfg)[2].replace("-Q", " Q")
    return f"Quarter so far ({quarter}): {ui.fmt_short(q_start)} – {ui.fmt_date(end)}"


def kpi_frame(rows, cfg):
    """The accessible table twin of every chart: one row per KPI."""
    return pd.DataFrame([{
        "Cadence": ui.CADENCE_LABEL[r["cadence"]], "Activity": r["activity"], "Lens": ui.LENS_LABEL[r["lens"]], "KPI": r["kpi"],
        "Value": ui.pct(r["value"], cfg), "Change": ui.delta_parts(r.get("delta"))[1] or "–", "Counts": r.get("detail") or "", "Status": f'{ui.STATUS[r["status"]][1]} {ui.STATUS[r["status"]][0]}', "Source query": r["source"],
    } for r in rows])


TONE_STATUS = {"good": "on_track", "partial": "watch", "bad": "off_track"}


def _tint(text):
    """A soft background in the status colour (translucent), for one Result cell."""
    tone = drill.result_tone(text)
    if tone is None:
        return ""
    fill = ui.STATUS[TONE_STATUS[tone]][2]
    r, g, b = (int(fill[i:i + 2], 16) for i in (1, 3, 5))
    return f"background-color: rgba({r},{g},{b},0.28)"


def _drill_dialog(row, end):
    @st.dialog(f'{row["activity"]} · {row["kpi"]}', width="large")
    def body():
        cfg = data.config()
        out = data.drill(end, row["activity"], row["kpi"])
        show(f'<div class="sv-sub" style="margin:0 0 .5rem">{ui.e(ui.plain_text(row["kpi"], cfg))}</div>')
        if out["kind"] == "ratio":
            tail = f'{out["counted"]:g} of {out["base"]:g} counted'
            show(f'<div class="sv-h2" style="margin:.2rem 0">{ui.pct(out["headline"], cfg)} {ui.chip(scorecard.status(out["headline"], cfg))} <span class="sv-muted" style="font-weight:400;font-size:.9rem">· {tail}</span></div>')
        elif out["kind"] == "mean":
            show(f'<div class="sv-h2" style="margin:.2rem 0">{ui.pct(out["headline"], cfg)} {ui.chip(scorecard.status(out["headline"], cfg))} <span class="sv-muted" style="font-weight:400;font-size:.9rem">· average {out["value"]:.2f} over {sum(r[out["spec"].value] is not None for r in out["rows"])} records</span></div>')
        elif row.get("detail"):
            show(f'<div class="sv-h2" style="margin:.2rem 0">{ui.e(row["detail"])}</div>')
        if not out["rows"]:
            st.info("No records behind this KPI in its window.")
            return
        rows = drill.table(out)
        if out["kind"] == "ratio":
            only = st.toggle("Only rows that pulled the number down", key=f'only-{row["activity"]}-{row["kpi"]}')
            rows = [r for r in rows if not only or not r["Result"].startswith(("✓", "–"))]
        st.caption(f"{len(rows)} of {len(out['rows'])} rows")
        frame = pd.DataFrame(rows).round(2)      # drill queries return exact values so totals reconcile; show two decimals
        st.dataframe(tinted(frame), hide_index=True, width="stretch", height=table_height(len(rows)))
    body()


def kpi_with_drill(row, cfg, key):
    """The KPI row, and under it a button that opens the records behind the number (which student, which event, which to-do)."""
    with st.container(gap="xxsmall"):
        show(ui.kpi_row(row, cfg))
        if st.button("See the records ▸", key=key, type="tertiary"):
            _drill_dialog(row, data.as_of())


def tinted(frame, column="Result"):
    """The frame with its Result column tinted in the status colours, as in the records dialog."""
    return frame.style.map(_tint, subset=[column]) if column in frame else frame
