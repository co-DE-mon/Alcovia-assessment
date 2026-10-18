"""Every active student, who needs attention and why, and a page per student."""
import pandas as pd
import streamlit as st

import data
import ui
from views.common import record_table, show, table_height


def frame(rows, cfg):
    n = cfg["scorecard"]["lookback_days"]
    def share(v):
        return None if v is None else round(v * 100)

    def tick(v):
        return "–" if v is None else "✓ Yes" if v else "✕ No"

    return pd.DataFrame([{
        "Student": r["name"], "Advisor": r["advisor_id"].replace("DEMO-", ""),
        "Attention": f'✕ {len(r["reasons"])} reasons' if r["listed"] else ("✓ OK" if not r["reasons"] else "✓ 1 reason"),
        "Last active": ui.ago(r["days_since_activity"]),
        f"Quizzes ({n} d)": f'{r["quizzes_started"]} of {r["quizzes_due"]}',
        f"Focus min ({n} d)": round(r["focus_minutes"]),
        "Syllabus %": None if r["syllabus_pct"] is None else round(r["syllabus_pct"]),
        "On pace": tick(r["syllabus_on_track"]),
        "To-dos %": share(r["task_completion_rate"]),
        "Roadmap on time %": None if r["roadmap_pct"] is None else round(r["roadmap_pct"]),
    } for r in rows])


def detail(s, end, cfg):
    sc = cfg["scorecard"]
    days = sc["window_days"]
    reasons = ui.reason_tags(s["reasons"], s["explanations"]) or '<span class="sv-muted">No reason to look at this student.</span>'
    new = '<span class="sv-tag sv-tag-new">New student</span>' if s["new_student"] else ""
    show(f'<div class="sv-h2" style="margin-top:.6rem">{ui.e(s["name"])} <span class="sv-muted" style="font-weight:400;font-size:.9rem">· {ui.e(s["student_id"])} · {ui.e(s["advisor_id"])} · enrolled {s["days_enrolled"]} days</span></div>')
    show(f'<div class="sv-tags" style="margin:.3rem 0 .8rem">{reasons}{new}</div>')
    pace = "" if s["syllabus_pace_pct"] is None else f'should be at {s["syllabus_pace_pct"]:.0f}% by now'
    show(ui.tile_row([
        ui.tile("Syllabus completed", ui.pct(None if s["syllabus_pct"] is None else s["syllabus_pct"] / 100), pace,
                "" if s["syllabus_on_track"] is None else ui.chip("on_track" if s["syllabus_on_track"] else "off_track", "On pace" if s["syllabus_on_track"] else "Behind")),
        ui.tile("To-dos done", ui.pct(s["task_completion_rate"], cfg), "" if s["deadline_adherence"] is None else f'of to-dos due in {cfg["scorecard"]["window_days"]} days · {ui.pct(s["deadline_adherence"], cfg)} of those finished on time'),
        ui.tile("Roadmap items on time", ui.pct(None if s["roadmap_pct"] is None else s["roadmap_pct"] / 100, cfg), f'of items due, done by deadline · on track at {round(cfg["roadmap"]["on_track_pct"])}%',
                "" if s["roadmap_on_track"] is None else ui.chip("on_track" if s["roadmap_on_track"] else "off_track", "On track" if s["roadmap_on_track"] else "Behind")),
        ui.tile("Chapter readiness", ui.pct(s["readiness_score"], cfg), "average of the five stages, from reading to exam accuracy"),
    ]))

    tl = data.timeline(end, s["student_id"])
    show(ui.h2(f"Last {days} days", "The quiz record and the valid focus minutes each day."))
    if tl:
        show(ui.quiz_strip(tl))
        df = pd.DataFrame(tl).set_index("day")[["focus_minutes"]].rename(columns={"focus_minutes": "Valid focus minutes"})
        st.caption("Valid focus minutes per day (completed sessions only)")
        if df["Valid focus minutes"].sum() > 0:
            st.bar_chart(df, height=200, color="#6b86e8")
        else:
            st.info(f"No valid focus minutes in the last {days} days.")
        with st.expander("Table view"):
            record_table([{"Day": r["day"], **{k: v for k, v in r.items() if k != "day"}} for r in tl],
                         f'student-timeline-{s["student_id"]}', end)
    else:
        st.info("This student has no days in the window.")


def records(profile, end, key, *, level=0):
    """The tabs of the student dialog: every section's records, or a note when a section has none."""
    tabs = st.tabs(list(profile["sections"]))
    for tab, parts in zip(tabs, profile["sections"].values()):
        with tab:
            for i, (heading, rows) in enumerate(parts):
                st.caption(f"{heading}: {len(rows)} record{'s' if len(rows) != 1 else ''}")
                if rows:
                    record_table(rows, f"{key}-{tab}-{i}", end, cap=360, level=level)


def open_student(s, end, cfg):
    @st.dialog(f'{s["name"]} · {s["student_id"]}', width="large", on_dismiss="rerun")
    def body():
        detail(s, end, cfg)
        profile = data.profile(end, s["student_id"])
        if profile["identity"]:
            with st.expander("Profile"):
                st.dataframe(pd.DataFrame([{"Field": k, "Value": "–" if v is None else str(v)} for k, v in profile["identity"].items()]), hide_index=True, width="stretch")
        show(ui.h2("All records", "Everything the tracker holds about this student."))
        records(profile, end, f'person-{s["student_id"]}')
    body()


def page():
    cfg, end = data.config(), data.as_of()
    rows = data.students(end)
    show(ui.page_header("Students", f"{len(rows)} active students · as of {ui.fmt_date(end)}"))

    left, right = st.columns([2, 3], vertical_alignment="bottom")
    advisors = ["All advisors"] + sorted({r["advisor_id"] for r in rows})
    advisor = left.selectbox("Advisor", advisors)
    only = right.toggle("Only students who need attention", value=False)
    shown = [r for r in rows if (advisor == "All advisors" or r["advisor_id"] == advisor) and (r["listed"] or not only)]
    st.caption(f"{len(shown)} of {len(rows)} students. Flagged students come first, longest silent first.")
    n, need = cfg["scorecard"]["lookback_days"], cfg["scorecard"]["off_track_min_reasons"]
    with st.expander("How to read this table"):
        st.markdown(
            f"- **Attention**: a student is flagged when {need} or more of these warning signs apply: "
            f"no quiz started in the last {n} days, no valid focus minutes in the last {n} days, behind the syllabus pace, "
            "roadmap items past their deadline, or fewer than half of their to-dos done.\n"
            f"- **Quizzes ({n} d)**: quizzes started out of quizzes held in the last {n} days.\n"
            f"- **Focus min ({n} d)**: minutes of completed focus sessions in the last {n} days (abandoned sessions don't count).\n"
            f"- **Syllabus %** and **On pace**: share of the syllabus covered, and whether that matches the {cfg['syllabus']['quarter_target_pct']}%-a-quarter pace for today's date.\n"
            f"- **To-dos %**: share of to-dos that fell due in the last {cfg['scorecard']['window_days']} days that the student finished.\n"
            "- **Roadmap %**: share of roadmap items due so far that were done by their deadline.")
    st.session_state.setdefault("students_table", 0)
    picked = st.dataframe(frame(shown, cfg), hide_index=True, width="stretch", height=table_height(len(shown), 760),
                          key=f'students-{st.session_state["students_table"]}', on_select="rerun", selection_mode="single-cell", column_config={
        "Student": st.column_config.TextColumn(width="medium"),
        "Syllabus %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%", width="small"),
        "To-dos %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%", width="small"),
        "Roadmap on time %": st.column_config.ProgressColumn("Roadmap %", min_value=0, max_value=100, format="%d%%", width="small"),
        **{k: st.column_config.TextColumn(width="small") for k in ("Advisor", "Attention", "Last active", f"Quizzes ({n} d)", "On pace")},
        f"Focus min ({n} d)": st.column_config.NumberColumn("Focus min", width="small"),
    })

    st.caption("Click any student to open them: summary, charts and every record we hold.")
    if picked.selection.cells:
        st.session_state["students_table"] += 1      # a fresh table next run, so the cell is not still selected when the dialog is closed
        open_student(shown[picked.selection.cells[0][0]], end, cfg)    # a cell is (row position, column): the row is the student
