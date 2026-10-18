"""Everything the tracker holds about one student, grouped into the sections of the student dialog. Pure functions with no Streamlit import."""
import metrics
import scorecard

# tab title -> the queries in sql/metrics/profile.sql shown under it, with a heading each
SECTIONS = {
    "Quizzes": [("Last {days} days of 8pm quizzes", "profile_quizzes")],
    "Focus": [("Focus sessions, last {days} days", "profile_focus")],
    "To-dos": [("To-dos due in the last {days} days", "profile_todos")],
    "Events and sessions": [("Events, sessions and calls this quarter", "profile_events"), ("Feedback the student gave this quarter", "profile_feedback")],
    "Roadmaps": [("Roadmap items", "profile_roadmap"), ("Advisor duties this quarter", "profile_advisor_inputs")],
    "Academics": [("Chapters and the stage each has reached", "profile_chapters"), ("Study hours this quarter", "profile_study_hours"), ("Exam targets and scores", "profile_exams")],
    "Wearable": [("Wearable and sleep data, last {days} days", "profile_wearable")],
}


def fetch(con, cfg, end, student_id):
    """{'identity': {heading: value} or None, 'sections': {tab: [(heading, rows)]}} for one student."""
    period_start, _ = scorecard.windows(cfg, end)
    prm = {**metrics.params(cfg, period_start, end), "student_id": student_id}
    ident = metrics.run(con, "profile", "profile_identity", prm)
    days = cfg["scorecard"]["window_days"]
    return {"identity": ident[0] if ident else None,
            "sections": {tab: [(heading.format(days=days), metrics.run(con, "profile", q, prm)) for heading, q in parts] for tab, parts in SECTIONS.items()}}
