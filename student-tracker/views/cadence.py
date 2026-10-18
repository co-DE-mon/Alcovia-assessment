"""One page per cadence: the three lenses at the top, then every activity with its KPIs."""
import streamlit as st

import data
import insights
import scorecard
import ui
from views.common import kpi_frame, kpi_with_drill, open_pending_record, record_table, show, window_of, window_text


def by_activity(rows):
    """{activity: {lens: [kpi rows]}} in catalogue order."""
    out = {}
    for r in rows:
        out.setdefault(r["activity"], {l: [] for l in scorecard.LENSES})[r["lens"]].append(r)
    return out


def trends(end):
    quiz, focus = data.daily_trends(end)
    show(ui.h2("Trend", "One line each, on its own scale. A gap means no quiz was held that day."))
    left, right = st.columns(2)
    with left:
        st.caption("Share of active students who started the quiz")
        st.line_chart(quiz, height=230, color="#6b86e8")
    with right:
        st.caption("Valid focus minutes per active student (completed sessions only)")
        st.line_chart(focus, height=230, color="#6b86e8")
    with st.expander("Table view of the trend"):
        from views.common import record_table
        record_table(quiz.join(focus).reset_index().to_dict("records"), "daily-trend", end=data.as_of())


def page(cadence):
    cfg, end = data.config(), data.as_of()
    open_pending_record()
    out = data.front(end)
    rows = [r for r in out["kpis"] if r["cadence"] == cadence]
    show(ui.page_header(ui.CADENCE_LABEL[cadence], ui.CADENCE_BLURB[cadence]))
    show(f'<div class="sv-sub" style="margin:-.4rem 0 .9rem">{window_text(cfg, end, window_of(cadence))}</div>')
    show(ui.legend(cfg))

    measurable = insights.with_data(rows)
    on = sum(r["status"] == "on_track" for r in measurable)
    show(ui.verdict_card(insights.summary(rows, cfg), scorecard.status(on / len(measurable) if measurable else None, cfg)))
    counts = {lens: sum(r["lens"] == lens for r in rows) for lens in scorecard.LENSES}
    show('<div class="sv-sub" style="margin:.1rem 0 .9rem">' + f"{len(rows)} KPIs: " + " · ".join(f"{ui.LENS_LABEL[l]} {counts[l]}" for l in scorecard.LENSES)
         + ". In each card the three columns run left to right: "
         + " ".join(f"<b>{ui.LENS_LABEL[l]}</b> ({ui.LENS_QUESTION[l].lower()}) {ui.LENS_HOWTO[l]}" for l in scorecard.LENSES) + "</div>")

    for activity, lenses in by_activity(rows).items():
        with st.container(border=True):
            status, text = insights.activity_verdict([k for lens in lenses.values() for k in lens], cfg)
            show(f'<div class="sv-act-head"><div class="sv-h2">{ui.e(activity)}</div>{ui.chip(status)}</div><div class="sv-act-text">{ui.e(text)}</div>')
            cols = st.columns(3)
            for col, lens in zip(cols, scorecard.LENSES):
                with col:
                    kp = lenses[lens]
                    if not kp:
                        show('<div class="sv-sub sv-muted">No KPI for this lens yet</div>')
                        continue
                    for k in kp:
                        kpi_with_drill(k, cfg, f'drill-{cadence}-{k["activity"]}-{k["kpi"]}')

    if cadence == "daily":
        trends(end)
    with st.expander("Table view"):
        record_table(kpi_frame(rows, cfg).to_dict("records"), f"cadence-kpis-{cadence}", end, level=2)
