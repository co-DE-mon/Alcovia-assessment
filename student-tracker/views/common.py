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
        drill_content(row, end, "dialog")
    body()


def drill_content(row, end, key):
    """Render KPI evidence inside either its dialog or an already-open table panel."""
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
        only = st.toggle("Only rows that pulled the number down", key=f'only-{key}-{row["activity"]}-{row["kpi"]}')
        rows = [r for r in rows if not only or not r["Result"].startswith(("✓", "–"))]
    st.caption(f"{len(rows)} of {len(out['rows'])} rows")
    record_table(rows, f'{key}-rows-{row["activity"]}-{row["kpi"]}-{len(rows)}', end, style=True)


def kpi_with_drill(row, cfg, key, *, card=False):
    """The KPI row, and under it a button that opens the records behind the number (which student, which event, which to-do)."""
    with st.container(border=card, gap="xxsmall"):
        show(ui.kpi_row(row, cfg))
        if st.button("See the records ▸", key=key, type="tertiary"):
            _drill_dialog(row, data.as_of())


def tinted(frame, column="Result"):
    """The frame with its Result column tinted in the status colours, as in the records dialog."""
    return frame.style.map(_tint, subset=[column]) if column in frame else frame


def record_table(rows, key, end, *, style=False, cap=520, level=0):
    """Click a cell to open its row and related records in a dialog."""
    if not rows:
        st.info("No records for this selection.")
        return None
    frame = pd.DataFrame(rows)
    st.caption("Click any cell to open its row and related records.")
    counter = f"_sv_record_table_{key}"
    st.session_state.setdefault(counter, 0)
    picked = st.dataframe(tinted(frame) if style else frame, hide_index=True, width="stretch",
                          height=table_height(len(rows), cap), on_select="rerun", selection_mode="single-cell",
                          key=f"{key}-{st.session_state[counter]}")
    if picked.selection.cells:
        st.session_state[counter] += 1
        st.session_state["_sv_pending_record"] = (rows[picked.selection.cells[0][0]], key, end, level)
        st.rerun()
    return None


def open_pending_record():
    """Open a cell-picked record on the page rerun, replacing any current dialog."""
    pending = st.session_state.pop("_sv_pending_record", None)
    if pending is None:
        return
    selected, key, end, level = pending
    if "Activity" in selected and "KPI" in selected and "Source query" in selected:
        row = next((r for r in data.front(end)["kpis"] if r["activity"] == selected["Activity"] and r["kpi"] == selected["KPI"]), None)
        if row is not None:
            _drill_dialog(row, end)
            return
    label = selected.get("Student") or selected.get("Item") or selected.get("Event ID") or selected.get("Run ID") or "Record details"

    @st.dialog(str(label), width="large", on_dismiss="rerun")
    def body():
        _record_content(selected, key, end, level)

    body()


def _record_content(selected, key, end, level):
    st.caption("Fields and related records")
    st.dataframe(pd.DataFrame([{"Field": k, "Value": "—" if pd.isna(v) else str(v)} for k, v in selected.items()]),
                 hide_index=True, width="stretch", height=table_height(len(selected), 360))
    if level >= 3:
        return
    event_id = selected.get("Event ID")
    if isinstance(event_id, str) and event_id:
        event = data.event(end, event_id)
        if event["detail"]:
            with st.expander("Event, attendance and feedback", expanded=True):
                st.dataframe(pd.DataFrame(event["detail"]), hide_index=True, width="stretch")
                st.caption(f'{len(event["people"])} attendance records')
                if event["people"]:
                    record_table(event["people"], f"{key}-event-people-{event_id}", end, level=level + 1)
                if event["feedback"]:
                    st.caption(f'{len(event["feedback"])} feedback records')
                    record_table(event["feedback"], f"{key}-event-feedback-{event_id}", end, level=level + 1)
    group_id = selected.get("Group")
    if isinstance(group_id, str) and group_id:
        with st.expander("Events in this group", expanded=True):
            record_table(data.group(end, group_id), f"{key}-group-{group_id}", end, level=level + 1)
    selected_day = selected.get("Day")
    if selected_day is not None and not event_id:
        from datetime import date
        if isinstance(selected_day, date) and selected_day <= end:
            evidence = data.day_records(end, selected_day)
            with st.expander("Activity on this day", expanded=True):
                st.caption("Events")
                if evidence["events"]:
                    record_table(evidence["events"], f"{key}-day-events-{selected_day}", end, level=level + 1)
                else:
                    st.caption("No events recorded.")
                st.caption("Focus sessions")
                if evidence["focus"]:
                    record_table(evidence["focus"], f"{key}-day-focus-{selected_day}", end, level=level + 1)
                else:
                    st.caption("No focus sessions recorded.")
    student_id = selected.get("ID")
    if isinstance(student_id, str) and student_id and level < 2:
        from views import students
        person = next((s for s in data.students(end) if s["student_id"] == student_id), None)
        profile = data.profile(end, student_id)
        if profile["identity"]:
            with st.expander(f'Student profile · {profile["identity"]["Name"]}', expanded=True):
                if not person:
                    st.caption("This student is outside the active cohort on the selected date.")
                    st.dataframe(pd.DataFrame([{"Field": k, "Value": str(v)} for k, v in profile["identity"].items()]),
                                 hide_index=True, width="stretch")
                else:
                    students.detail(person, end, data.config())
                students.records(profile, end, f"{key}-profile-{student_id}", level=2)
