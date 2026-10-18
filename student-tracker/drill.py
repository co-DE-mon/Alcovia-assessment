"""The records behind a KPI: which student, which event, which to-do. Pure functions with no Streamlit import, so they can be tested.

Each KPI maps to a query in sql/metrics/drill.sql and says which of that query's columns are the KPI's numerator and denominator
(kind "ratio"), which column is averaged (kind "mean"), or that the rows are only a list (kind "list": the KPI compares a count with a
policy or target, so no row-level share exists). tests/test_drill.py checks that ratio and mean drills add up to the KPI's headline value.
"""
from collections import namedtuple

import metrics
import scorecard

# counted / base: column names of the numerator and denominator (base None = every row counts once). value: the averaged column.
Spec = namedtuple("Spec", "query kind counted base value params", defaults=(None, None, None, None, None, None))


def ratio(query, counted, base=None, **params):
    return Spec(query, "ratio", counted, base, None, params)


def mean(query, value, **params):
    return Spec(query, "mean", None, None, value, params)


def listing(query, counted=None, **params):
    return Spec(query, "list", counted, None, None, params)


SPECS = {
    ("8pm quiz", "Quizzes held / days"): ratio("quiz_by_day", "Held"),
    ("8pm quiz", "Quizzes finished / started (proxy)"): ratio("quiz_by_student", "Finished", "Started"),
    ("8pm quiz", "Regular quiz takers (proxy)"): ratio("quiz_regular_takers_by_student", "Regular taker"),
    ("8pm quiz", "Started inside the entry window"): ratio("quiz_by_student", "Started on time", "Quizzes held"),
    ("Focus time", "Student-days with a session"): ratio("focus_by_student", "Days with a session", "Active days"),
    ("Focus time", "Sessions not given up (proxy)"): ratio("focus_by_student", "Sessions not given up", "Sessions"),
    ("Focus time", "Student-days at the focus target"): ratio("focus_by_student", "Days at the focus target", "Active days"),
    ("Timetable", "Student-days with a to-do due"): ratio("timetable_by_student", "Days with a to-do due", "Active days"),
    ("Timetable", "Calendar still connected (proxy)"): ratio("connection_by_student", "Still connected", "Connected long enough to judge", kind="calendar"),
    ("Timetable", "To-dos done on their due date"): ratio("timetable_by_student", "Done on the due date", "To-dos due"),
    ("Active minutes", "Student-days with wearable strain"): ratio("wearable_by_student", "Days with strain data", "Active days"),
    ("Active minutes", "Wearable still connected (proxy)"): ratio("connection_by_student", "Still connected", "Connected long enough to judge", kind="wearable"),
    ("Active minutes", "Strain inside the target band"): ratio("wearable_by_student", "Days inside the strain band", "Days with strain data"),
    ("Syllabus completion", "Monthly syllabus reviews done"): ratio("advisor_input_kind_rows", "Done", input_kind="syllabus_review"),
    ("Syllabus completion", "Roadmap check-in: pace of progress (average / 5)"): mean("roadmap_feedback_rows", "Pace of progress"),
    ("Syllabus completion", "Chapters covered against the syllabus pace"): ratio("syllabus_by_student", "Chapters done", "Chapters expected by now"),
    ("Rigour of completion", "Rigour checks done by the advisor"): ratio("advisor_input_kind_rows", "Done", input_kind="rigour_check"),
    ("Rigour of completion", "Sprints made when a timeline was missed"): ratio("advisor_input_kind_rows", "Done", input_kind="sprint_made"),
    ("Rigour of completion", "Students still working through their chapters (proxy)"): ratio("chapter_activity_by_student", "Updated a chapter recently"),
    ("Rigour of completion", "Chapters from past months fully complete"): ratio("rigour_closed_by_student", "Fully complete", "Chapters planned"),
    ("Summer program closure", "Application support sessions held / scheduled"): ratio("events_list", "Held", "Scheduled", kind="summer_support"),
    ("Summer program closure", "Summer support rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="summer_support"),
    ("Summer program closure", "Students who submitted an application"): ratio("summer_applications_by_student", "Applied"),
    ("Recovery", "Student-days with a recovery reading"): ratio("wearable_by_student", "Days with recovery data", "Active days"),
    ("Recovery", "Whoop students still syncing (proxy)"): ratio("whoop_sync_by_student", "Still syncing"),
    ("Recovery", "Sleep at or above target"): ratio("wearable_by_student", "Nights at the sleep target", "Nights with sleep data"),
    ("Academic roadmap", "Study-hour plan set"): ratio("study_plan_by_student", "Plan set"),
    ("Academic roadmap", "Roadmap check-in: pace of progress (average / 5)"): mean("roadmap_feedback_rows", "Pace of progress"),
    ("Academic roadmap", "Students on the syllabus pace"): ratio("syllabus_by_student", "On pace"),
    ("Academic roadmap", "Task completion rate"): ratio("todos_by_student", "Done", "To-dos due"),
    ("Academic roadmap", "Deadline adherence"): ratio("todos_by_student", "Done on time", "Done"),
    ("Academic roadmap", "Time estimation accuracy"): mean("time_estimation_rows", "Accuracy"),
    ("Academic roadmap", "Chapter readiness score"): ratio("readiness_by_student", "Stage points reached", "Stage points possible"),
    ("Academic roadmap", "Monthly rigour adherence"): ratio("rigour_by_student", "Reached the last stage", "Chapters planned this month"),
    ("Advisor input", "Advisor-assigned to-dos done"): ratio("advisor_todos_rows", "Done"),
    ("Advisor input", "Academic session rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="academic_session"),
    ("Advisor input", "Advisor-assigned to-dos done on time"): ratio("advisor_todos_rows", "Done on time"),
    ("Advisor input", "Students filling in their inputs"): ratio("input_cadence_by_student", "Filled in inputs"),
    ("Academic sessions", "Academic sessions held vs policy"): listing("events_list", "Held", kind="academic_session"),
    ("Academic sessions", "Session feedback (average rating / 5)"): mean("session_feedback_rows", "Average rating"),
    ("Academic sessions", "Academic sessions attended"): ratio("attendance_rows", "Attended", "Attendance recorded", kind="academic_session"),
    ("Workshops", "Workshops held vs expected"): listing("events_list", "Held", kind="workshop"),
    ("Workshops", "Workshop rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="workshop"),
    ("Workshops", "Workshop NPS (/ 10)"): mean("event_nps_rows", "NPS (out of 10)", kind="workshop"),
    ("Workshops", "Workshop attendance"): ratio("attendance_rows", "Attended", "Invited", kind="workshop"),
    ("Pod session", "Pods held vs expected"): listing("events_list", "Held", kind="pod"),
    ("Pod session", "Pod rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="pod"),
    ("Pod session", "Pod attendance"): ratio("attendance_rows", "Attended", "Invited", kind="pod"),
    ("Peer session", "Peer sessions held vs expected"): listing("events_list", "Held", kind="peer_session"),
    ("Peer session", "Peer session rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="peer_session"),
    ("Peer session", "Peer session attendance"): ratio("attendance_rows", "Attended", "Invited", kind="peer_session"),
    ("Mentor call", "Mentor calls held vs expected"): listing("events_list", "Held", kind="mentor_call"),
    ("Mentor call", "Mentor call rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="mentor_call"),
    ("Mentor call", "Mentor call attendance"): ratio("attendance_rows", "Attended", "Invited", kind="mentor_call"),
    ("Personal branding", "Shoots held / scheduled"): ratio("events_list", "Held", "Scheduled", kind="branding_shoot"),
    ("Personal branding", "Posted clips reaching the view target (proxy)"): ratio("clip_reach_rows", "Reached the view target", "Posted", kind="branding_shoot"),
    ("Personal branding", "Shoots posted"): ratio("posted_rows", "Posted", kind="branding_shoot"),
    ("Podcast", "Podcasts held / scheduled"): ratio("events_list", "Held", "Scheduled", kind="podcast"),
    ("Podcast", "Podcast rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="podcast"),
    ("Podcast", "Episodes posted"): ratio("posted_rows", "Posted", kind="podcast"),
    ("Competition prep", "Students assigned a competition"): ratio("competition_by_student", "Assigned a competition"),
    ("Competition prep", "Competition rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="competition"),
    ("Competition prep", "Assigned students who entered"): ratio("competition_by_student", "Entered", "Result recorded"),
    ("Parent-child bonding", "Parent workshop held"): ratio("events_list", "Held", "Scheduled", kind="parent_workshop"),
    ("Parent-child bonding", "Parent workshop rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="parent_workshop"),
    ("Parent-child bonding", "Parent workshop attendance"): ratio("attendance_rows", "Attended", "Invited", kind="parent_workshop"),
    ("Out-of-city trip", "Trip held"): ratio("events_list", "Held", "Scheduled", kind="trip"),
    ("Out-of-city trip", "Trip rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="trip"),
    ("Out-of-city trip", "Trip attendance"): ratio("attendance_rows", "Attended", "Invited", kind="trip"),
    ("Social work", "Social work activities held / scheduled"): ratio("events_list", "Held", "Scheduled", kind="social_work"),
    ("Social work", "Groups formed"): listing("social_work_group_rows"),
    ("Social work", "Social work rating (average / 5)"): mean("event_feedback_rows", "Average rating", kind="social_work"),
    ("Social work", "Social work attendance"): ratio("attendance_rows", "Attended", "Invited", kind="social_work"),
    ("Social work", "Theme milestones done by deadline"): ratio("roadmap_items_due", "Done by the deadline", roadmap="social_work"),
    ("Entrepreneurship", "Students with a startup plan"): ratio("roadmap_coverage_by_student", "Has a roadmap", roadmap="entrepreneurship"),
    ("Entrepreneurship", "Entrepreneurship rating (average / 5)"): mean("entrepreneurship_rating_rows", "Rating"),
    ("Entrepreneurship", "Theme milestones done by deadline"): ratio("roadmap_items_due", "Done by the deadline", roadmap="entrepreneurship"),
    ("Career", "Students with a career roadmap"): ratio("roadmap_coverage_by_student", "Has a roadmap", roadmap="career"),
    ("Career", "Check-in: confidence the roadmap leads to the goals (average / 5)"): mean("roadmap_feedback_rows", "Confidence in the quarterly goals"),
    ("Career", "Career roadmap items done"): ratio("roadmap_completion_rows", "Done", roadmap="career"),
    ("Personal", "Students with monthly milestones"): ratio("roadmap_coverage_by_student", "Has a roadmap", roadmap="personal"),
    ("Personal", "Check-in: how invested students feel (average / 5)"): mean("roadmap_feedback_rows", "How invested"),
    ("Personal", "Milestones done by deadline"): ratio("roadmap_items_due", "Done by the deadline", roadmap="personal"),
    ("Academic", "Students with an academic roadmap"): ratio("roadmap_coverage_by_student", "Has a roadmap", roadmap="academic"),
    ("Academic", "Advisor inputs done"): ratio("advisor_input_rows", "Done"),
    ("Academic", "Roadmap check-in rating (average / 5)"): mean("roadmap_feedback_rows", "Average rating"),
    ("Academic", "Academic items done by deadline"): ratio("roadmap_items_due", "Done by the deadline", roadmap="academic"),
    ("Academic", "Exam scores at or above target"): ratio("exam_rows", "Met the target", "Scored", exam_type="formative"),
}


def _kpi(activity, name):
    return next(k for k in scorecard.KPIS if (k.activity, k.name) == (activity, name))


def fetch(con, cfg, end, activity, name):
    """The rows behind one KPI and their totals.
    Returns {kind, rows, columns, counted, base, value, headline}: counted and base are the totals of a ratio drill, value the average of
    a mean drill, headline the 0-1 number these rows add up to (None for a list), which equals the KPI's own value."""
    spec, k = SPECS[(activity, name)], _kpi(activity, name)
    period_start, quarter_start = scorecard.windows(cfg, end)
    prm = metrics.params(cfg, period_start if k.window == "period" else quarter_start, end)
    rows = metrics.run(con, "drill", spec.query, {**prm, **spec.params})
    out = {"kind": spec.kind, "rows": rows, "columns": list(rows[0]) if rows else [], "spec": spec,
           "counted": None, "base": None, "value": None, "headline": None}
    if spec.kind == "ratio":
        out["counted"] = sum(r[spec.counted] or 0 for r in rows)
        out["base"] = sum(r[spec.base] or 0 for r in rows) if spec.base else len(rows)
        out["headline"] = out["counted"] / out["base"] if out["base"] else None
    elif spec.kind == "mean":
        vals = [r[spec.value] for r in rows if r[spec.value] is not None]
        out["value"] = sum(vals) / len(vals) if vals else None
        out["headline"] = None if out["value"] is None else out["value"] / k.scale
    return out


def row_result(spec, row):
    """(counted, base) of one row for a ratio drill, so the dialog can show 'two of three' per student; None for other kinds."""
    if spec.kind != "ratio":
        return None
    return row[spec.counted] or 0, (row[spec.base] or 0) if spec.base else 1


def _result(counted, base, single):
    if single:
        return "✓ Yes" if counted else "✕ No"
    return "–" if not base else f"{'✓' if counted >= base else '✕'} {counted:g} of {base:g}"


def table(out):
    """The dialog's rows: for a ratio drill a leading Result column says what each row did for the KPI, and rows that pulled the number
    down come first when they are people (a list of dates keeps its order). Other kinds come back as they are."""
    spec, rows = out["spec"], out["rows"]
    if spec.kind != "ratio":
        return rows
    shown = []
    for r in rows:
        c, b = row_result(spec, r)
        shown.append(({"Result": _result(c, b, spec.base is None), **r}, c, b))
    if rows and "Student" in rows[0]:
        shown.sort(key=lambda t: (t[2] == 0, (t[1] / t[2]) if t[2] else 0))
    return [r for r, _, _ in shown]


def result_tone(text):
    """good / partial / bad for a Result cell, None when there was nothing to judge, so the dialog can tint it. The ✓ or ✕ stays in the text."""
    if text.startswith("✓"):
        return "good"
    if text.startswith("✕"):
        return "bad" if text.startswith(("✕ No", "✕ 0 of")) else "partial"
    return None
