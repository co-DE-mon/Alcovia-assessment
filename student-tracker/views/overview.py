"""The front page, read like a product owner would: the verdict, how engaged students are, the biggest gaps, who to act on, and whether the data can be trusted.
The full cadence-by-lens scorecard sits at the bottom for anyone who wants every number."""
import pandas as pd
import streamlit as st

import data
import insights
import nav
import scorecard
import ui
from views import health, students
from views.common import drill_content, kpi_frame, kpi_with_drill, record_table, show, table_height, window_of, window_text


def _table(frame, caption):
    st.caption(caption)
    st.dataframe(frame, hide_index=True, width="stretch", height=table_height(len(frame)))


@st.dialog("Active students", width="large")
def _active_dialog(people):
    record_table([{"Student": s["name"], "ID": s["student_id"], "Advisor": s["advisor_id"], "Days enrolled": s["days_enrolled"],
                          "Last active": ui.ago(s["days_since_activity"]), "New": "Yes" if s["new_student"] else "",
                          "Needs attention": "Yes" if s["listed"] else "No"} for s in people], "overview-active", data.as_of())


@st.dialog("Students who need attention", width="large")
def _attention_dialog(listed, cfg):
    st.caption(f"{len(listed)} students with {cfg['scorecard']['off_track_min_reasons']} or more warning signs, most first")
    record_table([{"Student": s["name"], "ID": s["student_id"], "Advisor": s["advisor_id"], "Last active": ui.ago(s["days_since_activity"]), "Warning signs": len(s["reasons"]),
                   "What is wrong": "; ".join(s["explanations"])} for s in listed], "overview-attention", data.as_of())


@st.dialog("Every KPI", width="large")
def _kpis_dialog(rows, cfg):
    only = st.toggle("Only KPIs that are not on track", key="overview-kpis-only")
    shown = [r for r in rows if not only or r["status"] != "on_track"]
    st.caption(f"{len(shown)} of {len(rows)} KPIs. Change is against the previous {cfg['scorecard']['window_days']} days.")
    selected = record_table(kpi_frame(shown, cfg).to_dict("records"), f"overview-kpis-{only}", data.as_of(), level=2)
    if selected:
        row = next(r for r in shown if r["activity"] == selected["Activity"] and r["kpi"] == selected["KPI"])
        drill_content(row, data.as_of(), f"overview-kpi-{selected['Activity']}-{selected['KPI']}")


@st.dialog("Data sources", width="large")
def _sources_dialog(freshness, end):
    record_table([{"Source": r["source"], "State": "✕ Stale" if r["stale"] else "✓ Fresh",
                          "Last successful run": "never" if r["last_ok_at"] is None else f'{r["last_ok_at"]:%d %b %H:%M}',
                          "Hours since": r["hours_since_ok"], "Latest run": r["last_status"] or "never run",
                          "Failed (7 d)": r["failed_7d"], "Partial (7 d)": r["partial_7d"]} for r in freshness], "overview-sources", end)
    health.affected(end)


@st.dialog("Who shows this behaviour", width="large")
def _engagement_dialog(item):
    st.markdown(f"**{item['label']}**: {item['note']}.")
    rows = [{"Result": "–" if ok is None else "✓ Yes" if ok else "✕ No", "Student": s["name"], "ID": s["student_id"], "Advisor": s["advisor_id"], "Detail": number}
            for s, ok, number in sorted(item["who"], key=lambda w: (w[1] is not False, w[1] is None, w[0]["name"]))]
    only = st.toggle("Only students who do not", key=f"overview-eng-{item['label']}")
    shown = [r for r in rows if not only or r["Result"].startswith("✕")]
    st.caption(f"{item['count']} of {item['base']} students show it. Showing {len(shown)} rows, students who do not first.")
    record_table(shown, f"overview-engagement-{item['label']}-{only}", data.as_of(), style=True)


def page():
    cfg, end = data.config(), data.as_of()
    out, people = data.front(end), data.students(end)
    rows = out["kpis"]
    listed = [s for s in people if s["listed"]]
    stale = [r for r in out["freshness"] if r["stale"]]
    measurable = insights.with_data(rows)
    on_track = [r for r in measurable if r["status"] == "on_track"]
    before = out["attention_before"]
    days = cfg["scorecard"]["window_days"]

    show(ui.page_header("Student progress", f"{len(people)} active students · as of {ui.fmt_date(end)}"))

    lead = f"{len(listed)} of {len(people)} students need attention, and {len(on_track)} of {len(measurable)} KPIs are on track."
    sentences = [lead] + insights.summary(rows, cfg)[1:]
    if stale:
        sentences.append(f"{len(stale)} data source{'s are' if len(stale) != 1 else ' is'} stale, so some numbers may be out of date.")
    show(ui.verdict_card(sentences, scorecard.status(len(on_track) / len(measurable) if measurable else None, cfg)))

    move = insights.movement(rows)
    new = sum(1 for s in people if s["new_student"])
    freshness_chip = ui.chip("off_track", f"{len(stale)} stale") if stale else ui.chip("on_track", "All fresh")
    attention_sub = f"of {len(people)} students have {cfg['scorecard']['off_track_min_reasons']}+ warning signs"
    if before is not None:
        attention_sub += f" · {before} {days} days ago"
    show(ui.tile_row([
        ui.tile("Active students", len(people), f"{new} joined in the last {days} days"),
        ui.tile("Need attention", len(listed), attention_sub,
                title=f"A warning sign is something like no quiz or focus time in the last {cfg['scorecard']['lookback_days']} days, or being behind the syllabus. See the Students page for the reasons."),
        ui.tile("KPIs on track", f"{len(on_track)} of {len(measurable)}",
                (f"up on {move[0]}, down on {move[1]} vs {days} days ago" if move else f"measurable KPIs at {round(cfg['scorecard']['on_track_min'] * 100)}% or better")
                + f" · {len(rows) - len(measurable)} have no data yet",
                title="Each KPI is one measurement, e.g. 'quizzes held / days'. See the cadence pages for what each one means."),
        ui.tile("Data sources", f"{len(out['freshness']) - len(stale)} of {len(out['freshness'])} fresh", "feeds that updated recently enough to trust", freshness_chip),
    ]))

    cols = st.columns(4)
    if cols[0].button("See the students ▸", key="see-overview-active", type="tertiary"):
        _active_dialog(people)
    if cols[1].button("See who needs attention ▸", key="see-overview-attention", type="tertiary"):
        _attention_dialog(listed, cfg)
    if cols[2].button("See every KPI ▸", key="see-overview-kpis", type="tertiary"):
        _kpis_dialog(rows, cfg)
    if cols[3].button("See the sources ▸", key="see-overview-sources", type="tertiary"):
        _sources_dialog(out["freshness"], end)

    show(ui.h2("How engaged are students?", "How many students show each behaviour. A short bar is where the programme is losing them. Open one to see who."))
    with st.container(border=True):
        for x in insights.engagement(people, cfg):
            show(ui.engagement_row(x["label"], x["count"], x["base"], x["note"], scorecard.status(x["count"] / x["base"] if x["base"] else None, cfg), cfg))
            if st.button("See who ▸", key=f'see-overview-eng-{x["label"]}', type="tertiary"):
                _engagement_dialog(x)

    left, right = st.columns(2)
    with left:
        show(ui.h2("Biggest gaps", "The KPIs furthest from on track. Open the records to see who or what is behind each."))
        for k in insights.gaps(rows):
            with st.container(border=True):
                show(f'<div class="sv-sub">{ui.e(k["activity"])} · {ui.CADENCE_LABEL[k["cadence"]]}</div>')
                kpi_with_drill(k, cfg, f'drill-overview-gap-{k["activity"]}-{k["kpi"]}')
    with right:
        show(ui.h2("Bright spots", "What is working."))
        for k in insights.bright_spots(rows):
            with st.container(border=True):
                show(f'<div class="sv-sub">{ui.e(k["activity"])} · {ui.CADENCE_LABEL[k["cadence"]]}</div>')
                kpi_with_drill(k, cfg, f'drill-overview-bright-{k["activity"]}-{k["kpi"]}')

    show(ui.h2("Needs attention", f"Students with {cfg['scorecard']['off_track_min_reasons']} or more warning signs, grouped by advisor, longest silent first."))
    if not listed:
        st.success(f"No student has {cfg['scorecard']['off_track_min_reasons']} or more reasons to look at right now.")
    for advisor, group in insights.by_advisor(listed):
        show(ui.advisor_header(advisor, len(group)))
        for s in group:
            row, button = st.columns([9, 1], vertical_alignment="center")
            with row:
                show(ui.attention_row(s))
            if button.button("Open ▸", key=f'see-overview-student-{s["student_id"]}', type="tertiary"):
                students.open_student(s, end, cfg)
    nav.link("students", "Open the Students page")

    show(ui.h2("Is the data fresh?", "A source is stale when it has no fully successful run inside the freshness window."))
    show(ui.tile_row([ui.source_card(r) for r in out["freshness"]]))
    nav.link("health", "Pipeline details")

    with st.expander("Full scorecard: every cadence by every lens"):
        show('<div class="sv-sub" style="margin:0 0 .5rem">Each cell is the average of its KPIs, with the count in each status underneath. '
             'Conducted = did Alcovia run it, Liked = did students like it, Performed = how students did.</div>')
        show(ui.legend(cfg))
        windows = {c: window_text(cfg, end, window_of(c)).split(": ")[0].replace("Last ", "last ") for c in scorecard.CADENCES}
        show(ui.scorecard_grid(out["cells"], scorecard.CADENCES, cfg, windows))
        cols = st.columns([1.1] + [1] * len(scorecard.CADENCES), vertical_alignment="center")
        cols[0].caption("Open the details:")
        for col, c in zip(cols[1:], scorecard.CADENCES):
            with col:
                nav.link(c, ui.CADENCE_LABEL[c])

    with st.expander("Table view of every KPI"):
        selected = record_table(kpi_frame(rows, cfg).to_dict("records"), "overview-kpis-full", end, level=2)
        if selected:
            row = next(r for r in rows if r["activity"] == selected["Activity"] and r["kpi"] == selected["KPI"])
            drill_content(row, end, f"overview-full-{selected['Activity']}-{selected['KPI']}")
