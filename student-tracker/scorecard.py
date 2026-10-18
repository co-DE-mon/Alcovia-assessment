"""The cohort scorecard and the off-track list: the dashboard's front page.

Every number comes from a named query in sql/metrics, so a KPI has one definition. This module only picks the rate that stands for a KPI,
turns it into a status with the thresholds in config.yaml, and rolls the statuses up by cadence and lens.

Status of a KPI: on_track at or above scorecard.on_track_min, watch at or above scorecard.watch_min, otherwise off_track, and no_data when
there is nothing to measure (an unmeasured KPI is never shown as a failure). A cadence-by-lens cell takes the status of the average of its KPIs
that have data, and keeps the count of KPIs in each status, so one failing KPI stays visible without turning the whole cell red [A57].
"""
from collections import namedtuple
from datetime import timedelta

import metrics

LENSES = ("conducted", "liked", "performed")
CADENCES = ("daily", "weekly", "monthly", "quarterly", "roadmaps")

# window: "period" = the last scorecard.window_days days; "quarter" = the quarter so far.
# scale: what to divide by so the value is a 0-1 share (a 1-5 star rating is divided by 5, an NPS out of 10 by 10 [A57]).
Kpi = namedtuple("Kpi", "cadence activity lens name file query pick window scale", defaults=(None, "period", 1.0))


def _sel(rows, where):
    return [r for r in rows if all(r.get(k) == v for k, v in where.items())]


def field(name, **where):
    """Pick one field from the first row that matches, or None when the query returned no such row."""
    return lambda rows: (lambda r: None if r is None else r.get(name))((_sel(rows, where) or [None])[0])


def ratio(num, den, **where):
    """Sum of one field over the matching rows divided by the sum of another; None when the denominator is 0."""
    def pick(rows):
        sel = _sel(rows, where)
        d = sum(r[den] for r in sel)
        return sum(r[num] for r in sel) / d if d else None
    return pick


def one_minus(pick):
    return lambda rows: (lambda v: None if v is None else 1 - v)(pick(rows))


KPIS = [
    # --- daily ---
    Kpi("daily", "8pm quiz", "conducted", "Quizzes held / days", "daily", "quiz_summary", field("held_rate")),
    Kpi("daily", "8pm quiz", "liked", "Quizzes finished / started (proxy)", "daily", "quiz_summary", field("completion_rate")),
    Kpi("daily", "8pm quiz", "liked", "Regular quiz takers (proxy)", "daily", "quiz_regular_takers", field("regular_taker_rate")),
    Kpi("daily", "8pm quiz", "performed", "Started inside the entry window", "daily", "quiz_summary", field("in_window_rate")),
    Kpi("daily", "Focus time", "conducted", "Student-days with a session", "daily", "focus_summary", field("reach_rate")),
    Kpi("daily", "Focus time", "liked", "Sessions not given up (proxy)", "daily", "focus_summary", one_minus(field("give_up_rate"))),
    Kpi("daily", "Focus time", "performed", "Student-days at the focus target", "daily", "focus_summary", field("share_meeting_target")),
    Kpi("daily", "Timetable", "conducted", "Student-days with a to-do due", "daily", "timetable_summary", field("logged_rate")),
    Kpi("daily", "Timetable", "liked", "Calendar still connected (proxy)", "daily", "connection_retention", field("retention_rate", kind="calendar")),
    Kpi("daily", "Timetable", "performed", "To-dos done on their due date", "daily", "timetable_summary", field("done_same_day_rate")),
    Kpi("daily", "Active minutes", "conducted", "Student-days with wearable strain", "daily", "wearable_summary", field("strain_coverage")),
    Kpi("daily", "Active minutes", "liked", "Wearable still connected (proxy)", "daily", "connection_retention", field("retention_rate", kind="wearable")),
    Kpi("daily", "Active minutes", "performed", "Strain inside the target band", "daily", "wearable_summary", field("strain_in_band_rate")),
    Kpi("daily", "Recovery", "conducted", "Student-days with a recovery reading", "daily", "wearable_summary", ratio("recovery_days", "student_days")),
    Kpi("daily", "Recovery", "liked", "Whoop students still syncing (proxy)", "daily", "whoop_syncing", field("sync_rate")),
    Kpi("daily", "Recovery", "performed", "Sleep at or above target", "daily", "wearable_summary", field("sleep_target_rate")),
    # --- weekly ---
    Kpi("weekly", "Academic roadmap", "conducted", "Study-hour plan set", "weekly", "study_plan_set", field("plan_set_rate")),
    Kpi("weekly", "Academic roadmap", "liked", "Roadmap check-in: pace of progress (average / 5)", "roadmaps", "roadmap_feedback", field("avg_pace"), scale=5.0),
    Kpi("weekly", "Academic roadmap", "performed", "Students on the syllabus pace", "weekly", "syllabus_pace", field("on_track_rate")),
    Kpi("weekly", "Academic roadmap", "performed", "Task completion rate", "given", "task_metrics", field("task_completion_rate")),
    Kpi("weekly", "Academic roadmap", "performed", "Deadline adherence", "given", "task_metrics", field("deadline_adherence")),
    Kpi("weekly", "Academic roadmap", "performed", "Time estimation accuracy", "given", "time_estimation", field("avg_accuracy")),
    Kpi("weekly", "Academic roadmap", "performed", "Chapter readiness score", "given", "chapter_readiness", field("readiness_score")),
    Kpi("weekly", "Academic roadmap", "performed", "Monthly rigour adherence", "given", "rigour_adherence", field("adherence")),
    Kpi("weekly", "Advisor input", "conducted", "Advisor-assigned to-dos done", "weekly", "advisor_todos", field("done_rate")),
    Kpi("weekly", "Advisor input", "liked", "Academic session rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="academic_session"), scale=5.0),
    Kpi("weekly", "Advisor input", "performed", "Advisor-assigned to-dos done on time", "weekly", "advisor_todos", field("on_time_rate")),
    Kpi("weekly", "Advisor input", "performed", "Students filling in their inputs", "weekly", "student_input_cadence", field("filled_rate")),
    Kpi("weekly", "Academic sessions", "conducted", "Academic sessions held vs policy", "weekly", "session_delivery", field("delivered_vs_policy", kind="academic_session")),
    Kpi("weekly", "Academic sessions", "liked", "Session feedback (average rating / 5)", "weekly", "session_feedback", field("avg_composite"), scale=5.0),
    Kpi("weekly", "Academic sessions", "performed", "Academic sessions attended", "weekly", "session_delivery", field("attended_rate", kind="academic_session")),
    # --- monthly ---
    Kpi("monthly", "Workshops", "conducted", "Workshops held vs expected", "events", "event_delivery", field("delivered_vs_expected", kind="workshop")),
    Kpi("monthly", "Workshops", "liked", "Workshop rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="workshop"), scale=5.0),
    Kpi("monthly", "Workshops", "liked", "Workshop NPS (/ 10)", "events", "event_feedback", field("avg_nps", kind="workshop"), scale=10.0),
    Kpi("monthly", "Workshops", "performed", "Workshop attendance", "events", "event_attendance_rates", field("attended_rate", kind="workshop")),
    Kpi("monthly", "Pod session", "conducted", "Pods held vs expected", "events", "event_delivery", field("delivered_vs_expected", kind="pod")),
    Kpi("monthly", "Pod session", "liked", "Pod rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="pod"), scale=5.0),
    Kpi("monthly", "Pod session", "performed", "Pod attendance", "events", "event_attendance_rates", field("attended_rate", kind="pod")),
    Kpi("monthly", "Peer session", "conducted", "Peer sessions held vs expected", "events", "event_delivery", field("delivered_vs_expected", kind="peer_session")),
    Kpi("monthly", "Peer session", "liked", "Peer session rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="peer_session"), scale=5.0),
    Kpi("monthly", "Peer session", "performed", "Peer session attendance", "events", "event_attendance_rates", field("attended_rate", kind="peer_session")),
    Kpi("monthly", "Mentor call", "conducted", "Mentor calls held vs expected", "events", "event_delivery", field("delivered_vs_expected", kind="mentor_call")),
    Kpi("monthly", "Mentor call", "liked", "Mentor call rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="mentor_call"), scale=5.0),
    Kpi("monthly", "Mentor call", "performed", "Mentor call attendance", "events", "event_attendance_rates", field("attended_rate", kind="mentor_call")),
    Kpi("monthly", "Personal branding", "conducted", "Shoots held / scheduled", "events", "event_delivery", field("held_rate", kind="branding_shoot")),
    Kpi("monthly", "Personal branding", "liked", "Posted clips reaching the view target (proxy)", "events", "clip_reach", field("reach_rate", kind="branding_shoot")),
    Kpi("monthly", "Personal branding", "performed", "Shoots posted", "events", "posted_clips", field("posted_rate", kind="branding_shoot")),
    # --- quarterly ---
    Kpi("quarterly", "Podcast", "conducted", "Podcasts held / scheduled", "events", "event_delivery", field("held_rate", kind="podcast"), "quarter"),
    Kpi("quarterly", "Podcast", "liked", "Podcast rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="podcast"), "quarter", 5.0),
    Kpi("quarterly", "Podcast", "performed", "Episodes posted", "events", "posted_clips", field("posted_rate", kind="podcast"), "quarter"),
    Kpi("quarterly", "Competition prep", "conducted", "Students assigned a competition", "quarterly", "competition_outcomes", field("assigned_rate"), "quarter"),
    Kpi("quarterly", "Competition prep", "liked", "Competition rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="competition"), "quarter", 5.0),
    Kpi("quarterly", "Competition prep", "performed", "Assigned students who entered", "quarterly", "competition_outcomes", field("entered_rate"), "quarter"),
    Kpi("quarterly", "Parent-child bonding", "conducted", "Parent workshop held", "events", "event_delivery", field("held_rate", kind="parent_workshop"), "quarter"),
    Kpi("quarterly", "Parent-child bonding", "liked", "Parent workshop rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="parent_workshop"), "quarter", 5.0),
    Kpi("quarterly", "Parent-child bonding", "performed", "Parent workshop attendance", "events", "event_attendance_rates", field("attended_rate", kind="parent_workshop"), "quarter"),
    Kpi("quarterly", "Out-of-city trip", "conducted", "Trip held", "events", "event_delivery", field("held_rate", kind="trip"), "quarter"),
    Kpi("quarterly", "Out-of-city trip", "liked", "Trip rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="trip"), "quarter", 5.0),
    Kpi("quarterly", "Out-of-city trip", "performed", "Trip attendance", "events", "event_attendance_rates", field("attended_rate", kind="trip"), "quarter"),
    Kpi("quarterly", "Social work", "conducted", "Social work activities held / scheduled", "quarterly", "social_work_groups", field("held_rate"), "quarter"),
    Kpi("quarterly", "Social work", "conducted", "Groups formed", "quarterly", "social_work_groups", field("groups_formed_rate"), "quarter"),
    Kpi("quarterly", "Social work", "liked", "Social work rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="social_work"), "quarter", 5.0),
    Kpi("quarterly", "Social work", "performed", "Social work attendance", "quarterly", "social_work_groups", field("attended_rate"), "quarter"),
    Kpi("quarterly", "Social work", "performed", "Theme milestones done by deadline", "roadmaps", "roadmap_status", ratio("done_by_deadline", "items_due", roadmap="social_work"), "quarter"),
    Kpi("quarterly", "Summer program closure", "conducted", "Application support sessions held / scheduled", "events", "event_delivery", field("held_rate", kind="summer_support"), "quarter"),
    Kpi("quarterly", "Summer program closure", "liked", "Summer support rating (average / 5)", "events", "event_feedback", field("avg_composite", kind="summer_support"), "quarter", 5.0),
    Kpi("quarterly", "Summer program closure", "performed", "Students who submitted an application", "quarterly", "summer_applications", field("applied_rate"), "quarter"),
    Kpi("quarterly", "Entrepreneurship", "conducted", "Students with a startup plan", "roadmaps", "roadmap_coverage", field("coverage_rate", roadmap="entrepreneurship"), "quarter"),
    Kpi("quarterly", "Entrepreneurship", "liked", "Entrepreneurship rating (average / 5)", "quarterly", "entrepreneurship_rating", field("avg_composite"), "quarter", 5.0),
    Kpi("quarterly", "Entrepreneurship", "performed", "Theme milestones done by deadline", "roadmaps", "roadmap_status", ratio("done_by_deadline", "items_due", roadmap="entrepreneurship"), "quarter"),
    # --- roadmaps ---
    Kpi("roadmaps", "Career", "conducted", "Students with a career roadmap", "roadmaps", "roadmap_coverage", field("coverage_rate", roadmap="career"), "quarter"),
    Kpi("roadmaps", "Career", "liked", "Check-in: confidence the roadmap leads to the goals (average / 5)", "roadmaps", "roadmap_feedback", field("avg_confidence"), "quarter", 5.0),
    Kpi("roadmaps", "Career", "performed", "Career roadmap items done", "roadmaps", "roadmap_completion", field("completion_rate", roadmap="career"), "quarter"),
    Kpi("roadmaps", "Personal", "conducted", "Students with monthly milestones", "roadmaps", "roadmap_coverage", field("coverage_rate", roadmap="personal"), "quarter"),
    Kpi("roadmaps", "Personal", "liked", "Check-in: how invested students feel (average / 5)", "roadmaps", "roadmap_feedback", field("avg_invested"), "quarter", 5.0),
    Kpi("roadmaps", "Personal", "performed", "Milestones done by deadline", "roadmaps", "roadmap_status", ratio("done_by_deadline", "items_due", roadmap="personal"), "quarter"),
    Kpi("roadmaps", "Syllabus completion", "conducted", "Monthly syllabus reviews done", "roadmaps", "advisor_inputs_by_kind", field("done_rate", input_kind="syllabus_review"), "quarter"),
    Kpi("roadmaps", "Syllabus completion", "liked", "Roadmap check-in: pace of progress (average / 5)", "roadmaps", "roadmap_feedback", field("avg_pace"), "quarter", 5.0),
    Kpi("roadmaps", "Syllabus completion", "performed", "Chapters covered against the syllabus pace", "weekly", "syllabus_progress", field("pace_ratio"), "quarter"),
    Kpi("roadmaps", "Rigour of completion", "conducted", "Rigour checks done by the advisor", "roadmaps", "advisor_inputs_by_kind", field("done_rate", input_kind="rigour_check"), "quarter"),
    Kpi("roadmaps", "Rigour of completion", "conducted", "Sprints made when a timeline was missed", "roadmaps", "advisor_inputs_by_kind", field("done_rate", input_kind="sprint_made"), "quarter"),
    Kpi("roadmaps", "Rigour of completion", "liked", "Students still working through their chapters (proxy)", "given", "chapter_activity", field("working_rate"), "quarter"),
    Kpi("roadmaps", "Rigour of completion", "performed", "Chapters from past months fully complete", "given", "rigour_closed_months", field("closed_month_rate"), "quarter"),
    Kpi("roadmaps", "Academic", "conducted", "Students with an academic roadmap", "roadmaps", "roadmap_coverage", field("coverage_rate", roadmap="academic"), "quarter"),
    Kpi("roadmaps", "Academic", "conducted", "Advisor inputs done", "roadmaps", "advisor_inputs_by_kind", ratio("inputs_done", "inputs_due"), "quarter"),
    Kpi("roadmaps", "Academic", "liked", "Roadmap check-in rating (average / 5)", "roadmaps", "roadmap_feedback", field("avg_composite"), "quarter", 5.0),
    Kpi("roadmaps", "Academic", "performed", "Academic items done by deadline", "roadmaps", "roadmap_status", ratio("done_by_deadline", "items_due", roadmap="academic"), "quarter"),
    Kpi("roadmaps", "Academic", "performed", "Exam scores at or above target", "roadmaps", "exam_score_vs_target", field("met_target_rate", exam_type="formative"), "quarter"),
]


def _n(x):
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def of(num, den, tail, **where):
    """'29 of 30 days': sums of two fields over the matching rows, then a plain-words tail. None when the denominator is 0."""
    def detail(rows):
        sel = _sel(rows, where)
        n, d = sum(r[num] or 0 for r in sel), sum(r[den] or 0 for r in sel)
        return f"{_n(n)} of {_n(d)} {tail}" if d else None
    return detail


def share(rate, den, tail, **where):
    """Like of(), for a query that returns the rate and its denominator but not the numerator: numerator = rate x denominator."""
    def detail(rows):
        r = (_sel(rows, where) or [None])[0]
        return None if r is None or r[rate] is None or not r[den] else f"{_n(r[rate] * r[den])} of {_n(r[den])} {tail}"
    return detail


def note(text, **where):
    """A one-off sentence from the first matching row: text(row) -> str or None."""
    return lambda rows: (lambda r: None if r is None else text(r))((_sel(rows, where) or [None])[0])


def rating(field, scale, count, tail, **where):
    """'average 3.9 of 5, from 51 ratings': for a KPI that is an average, not a share."""
    return note(lambda r: None if r[field] is None else f"average {r[field]:.1f} of {scale}, from {_n(r[count])} {tail}", **where)


# The counts behind each KPI's percentage, in plain words: (activity, KPI name) -> function of the rows the KPI is read from.
DETAIL = {
    ("8pm quiz", "Quizzes held / days"): of("quizzes_held", "days_in_period", "days had a quiz"),
    ("8pm quiz", "Quizzes finished / started (proxy)"): of("completed", "started", "started quizzes were finished"),
    ("8pm quiz", "Regular quiz takers (proxy)"): of("regular_takers", "eligible_students", "students are regular takers"),
    ("8pm quiz", "Started inside the entry window"): of("started_in_window", "student_quizzes_due", "student-quizzes started on time"),
    ("Focus time", "Student-days with a session"): of("student_days_with_session", "student_days", "student-days had a session"),
    ("Focus time", "Sessions not given up (proxy)"): note(lambda r: None if not r["sessions"] or r["give_up_rate"] is None else
                                                       f'{_n(r["sessions"] * (1 - r["give_up_rate"]))} of {_n(r["sessions"])} sessions were not given up'),
    ("Focus time", "Student-days at the focus target"): share("share_meeting_target", "student_days", "student-days reached the focus target"),
    ("Timetable", "Student-days with a to-do due"): of("student_days_with_todo", "student_days", "student-days had a to-do due"),
    ("Timetable", "Calendar still connected (proxy)"): of("retained", "eligible", "students still have it connected", kind="calendar"),
    ("Timetable", "To-dos done on their due date"): of("done_same_day", "todos_due", "to-dos were done on their due date"),
    ("Active minutes", "Student-days with wearable strain"): of("strain_days", "student_days", "student-days had wearable data"),
    ("Active minutes", "Wearable still connected (proxy)"): of("retained", "eligible", "students still have it connected", kind="wearable"),
    ("Active minutes", "Strain inside the target band"): share("strain_in_band_rate", "strain_days", "days with data were in the band"),
    ("Recovery", "Sleep at or above target"): share("sleep_target_rate", "sleep_days", "nights with data met the sleep target"),
    ("Academic roadmap", "Study-hour plan set"): of("plan_set", "active_students", "students have a study-hour plan"),
    ("Academic roadmap", "Students on the syllabus pace"): of("on_track", "students", "students are on the syllabus pace"),
    ("Academic roadmap", "Task completion rate"): of("todos_done", "todos_due", "to-dos due were done"),
    ("Academic roadmap", "Deadline adherence"): of("done_on_time", "todos_done", "finished to-dos were on time"),
    ("Academic roadmap", "Time estimation accuracy"): note(lambda r: None if r["avg_accuracy"] is None else f'average accuracy {r["avg_accuracy"]:.0%} over {_n(r["measured"])} student-subjects'),
    ("Academic roadmap", "Chapter readiness score"): note(lambda r: None if r["readiness_score"] is None else f'average readiness {r["readiness_score"]:.0%} over {_n(r["chapters"])} chapters'),
    ("Academic roadmap", "Monthly rigour adherence"): of("chapters_complete", "chapters_planned", "planned chapters are complete"),
    ("Advisor input", "Advisor-assigned to-dos done"): of("done", "assigned", "assigned to-dos were done"),
    ("Advisor input", "Advisor-assigned to-dos done on time"): of("done_on_time", "assigned", "assigned to-dos were done on time"),
    ("Advisor input", "Students filling in their inputs"): of("filled_inputs", "active_students", "students filled in their inputs"),
    ("Academic sessions", "Academic sessions held vs policy"): note(lambda r: None if r["delivered_vs_policy"] is None else
                                                                   f'{_n(r["held"])} held against {_n(r["policy_expected"])} expected by the monthly policy', kind="academic_session"),
    ("Academic sessions", "Session feedback (average rating / 5)"): rating("avg_composite", 5, "responses", "ratings"),
    ("Academic sessions", "Academic sessions attended"): of("attended", "held", "held student-sessions were attended", kind="academic_session"),
    ("Workshops", "Workshops held vs expected"): note(lambda r: None if r["delivered_vs_expected"] is None else f'{_n(r["held"])} held against {_n(r["expected"])} expected', kind="workshop"),
    ("Workshops", "Workshop rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="workshop"),
    ("Workshops", "Workshop NPS (/ 10)"): note(lambda r: None if r["avg_nps"] is None else f'average {r["avg_nps"]:.1f} of 10', kind="workshop"),
    ("Workshops", "Workshop attendance"): of("attended", "invited", "invited students attended", kind="workshop"),
    ("Pod session", "Pods held vs expected"): note(lambda r: None if r["delivered_vs_expected"] is None else f'{_n(r["held"])} held against {_n(r["expected"])} expected', kind="pod"),
    ("Pod session", "Pod rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="pod"),
    ("Pod session", "Pod attendance"): of("attended", "invited", "invited students attended", kind="pod"),
    ("Peer session", "Peer sessions held vs expected"): note(lambda r: None if r["delivered_vs_expected"] is None else f'{_n(r["held"])} held against {_n(r["expected"])} expected', kind="peer_session"),
    ("Peer session", "Peer session rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="peer_session"),
    ("Peer session", "Peer session attendance"): of("attended", "invited", "invited students attended", kind="peer_session"),
    ("Mentor call", "Mentor calls held vs expected"): note(lambda r: None if r["delivered_vs_expected"] is None else f'{_n(r["held"])} held against {_n(r["expected"])} expected', kind="mentor_call"),
    ("Mentor call", "Mentor call rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="mentor_call"),
    ("Mentor call", "Mentor call attendance"): of("attended", "invited", "invited students attended", kind="mentor_call"),
    ("Personal branding", "Shoots held / scheduled"): of("held", "scheduled", "scheduled shoots were held", kind="branding_shoot"),
    ("Personal branding", "Shoots posted"): of("posted", "held", "held shoots were posted", kind="branding_shoot"),
    ("Podcast", "Podcasts held / scheduled"): of("held", "scheduled", "scheduled shoots were held", kind="podcast"),
    ("Podcast", "Podcast rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="podcast"),
    ("Podcast", "Episodes posted"): of("posted", "held", "shot episodes were posted", kind="podcast"),
    ("Competition prep", "Students assigned a competition"): of("assigned_students", "active_students", "students were assigned a competition"),
    ("Competition prep", "Competition rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="competition"),
    ("Competition prep", "Assigned students who entered"): of("entries", "assigned_students", "assigned students entered"),
    ("Parent-child bonding", "Parent workshop held"): of("held", "scheduled", "scheduled workshops were held", kind="parent_workshop"),
    ("Parent-child bonding", "Parent workshop rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="parent_workshop"),
    ("Parent-child bonding", "Parent workshop attendance"): of("attended", "invited", "invited attended", kind="parent_workshop"),
    ("Out-of-city trip", "Trip held"): of("held", "scheduled", "scheduled trips were held", kind="trip"),
    ("Out-of-city trip", "Trip rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="trip"),
    ("Out-of-city trip", "Trip attendance"): of("attended", "invited", "invited students attended", kind="trip"),
    ("Social work", "Social work activities held / scheduled"): of("activities_held", "activities_scheduled", "scheduled activities were held"),
    ("Social work", "Groups formed"): of("groups_formed", "groups_expected", "expected groups were formed"),
    ("Social work", "Social work rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="social_work"),
    ("Social work", "Social work attendance"): of("attended", "invited", "invited students attended"),
    ("Social work", "Theme milestones done by deadline"): of("done_by_deadline", "items_due", "milestones were done by their deadline", roadmap="social_work"),
    ("Entrepreneurship", "Theme milestones done by deadline"): of("done_by_deadline", "items_due", "milestones were done by their deadline", roadmap="entrepreneurship"),
    ("Career", "Students with a career roadmap"): of("students_with_roadmap", "active_students", "students have a career roadmap", roadmap="career"),
    ("Career", "Career roadmap items done"): of("items_done", "items", "roadmap items are done", roadmap="career"),
    ("Personal", "Students with monthly milestones"): of("students_with_roadmap", "active_students", "students have monthly milestones", roadmap="personal"),
    ("Personal", "Milestones done by deadline"): of("done_by_deadline", "items_due", "milestones were done by their deadline", roadmap="personal"),
    ("Academic", "Students with an academic roadmap"): of("students_with_roadmap", "active_students", "students have an academic roadmap", roadmap="academic"),
    ("Academic", "Advisor inputs done"): of("inputs_done", "inputs_due", "advisor inputs are done"),
    ("Academic", "Academic items done by deadline"): of("done_by_deadline", "items_due", "items were done by their deadline", roadmap="academic"),
    ("Academic", "Exam scores at or above target"): share("met_target_rate", "n_scored", "scored student-subjects met their target", exam_type="formative"),
    ("Syllabus completion", "Monthly syllabus reviews done"): of("inputs_done", "inputs_due", "monthly syllabus reviews were done", input_kind="syllabus_review"),
    ("Syllabus completion", "Roadmap check-in: pace of progress (average / 5)"): rating("avg_pace", 5, "responses", "check-ins"),
    ("Syllabus completion", "Chapters covered against the syllabus pace"): of("chapters_done", "chapters_expected", "chapters expected by now are covered"),
    ("Rigour of completion", "Rigour checks done by the advisor"): of("inputs_done", "inputs_due", "rigour checks were done", input_kind="rigour_check"),
    ("Rigour of completion", "Sprints made when a timeline was missed"): of("inputs_done", "inputs_due", "sprints were made", input_kind="sprint_made"),
    ("Rigour of completion", "Students still working through their chapters (proxy)"): of("working", "active_students", "students updated a chapter recently"),
    ("Rigour of completion", "Chapters from past months fully complete"): of("chapters_complete", "chapters_planned", "chapters from past months are fully complete"),
    ("Summer program closure", "Application support sessions held / scheduled"): of("held", "scheduled", "scheduled sessions were held", kind="summer_support"),
    ("Summer program closure", "Summer support rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="summer_support"),
    ("Summer program closure", "Students who submitted an application"): of("applied", "invited_students", "invited students have submitted an application"),
    ("Recovery", "Student-days with a recovery reading"): of("recovery_days", "student_days", "student-days had a recovery reading"),
    ("Recovery", "Whoop students still syncing (proxy)"): of("syncing", "connected_students", "Whoop students are still syncing"),
    ("Academic roadmap", "Roadmap check-in: pace of progress (average / 5)"): rating("avg_pace", 5, "responses", "check-ins"),
    ("Advisor input", "Academic session rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings", kind="academic_session"),
    ("Personal branding", "Posted clips reaching the view target (proxy)"): of("reached", "posted", "posted clips reached the view target", kind="branding_shoot"),
    ("Entrepreneurship", "Students with a startup plan"): of("students_with_roadmap", "active_students", "students have a startup plan", roadmap="entrepreneurship"),
    ("Entrepreneurship", "Entrepreneurship rating (average / 5)"): rating("avg_composite", 5, "responses", "ratings"),
    ("Career", "Check-in: confidence the roadmap leads to the goals (average / 5)"): rating("avg_confidence", 5, "responses", "check-ins"),
    ("Personal", "Check-in: how invested students feel (average / 5)"): rating("avg_invested", 5, "responses", "check-ins"),
    ("Academic", "Roadmap check-in rating (average / 5)"): rating("avg_composite", 5, "responses", "check-ins"),
}


def status(value, cfg):
    """on_track, watch, off_track, or no_data for a 0-1 share."""
    if value is None:
        return "no_data"
    sc = cfg["scorecard"]
    return "on_track" if value >= sc["on_track_min"] else "watch" if value >= sc["watch_min"] else "off_track"


def windows(cfg, end):
    """(period start, quarter start) for an as-of day: the last window_days days, and the quarter so far."""
    return end - timedelta(days=cfg["scorecard"]["window_days"] - 1), metrics.quarter_for(end, cfg)[0]


def kpi_rows(con, cfg, end):
    """One dict per KPI: where it sits in the catalogue, its 0-1 value, its status, and the query it came from."""
    period_start, quarter_start = windows(cfg, end)
    params = {"period": metrics.params(cfg, period_start, end), "quarter": metrics.params(cfg, quarter_start, end)}
    cache, out = {}, []
    for k in KPIS:
        key = (k.file, k.query, k.window)
        if key not in cache:
            cache[key] = metrics.run(con, k.file, k.query, params[k.window])
        raw = k.pick(cache[key])
        value = None if raw is None else max(0.0, min(1.0, raw / k.scale))
        detail = DETAIL.get((k.activity, k.name))
        out.append({"cadence": k.cadence, "activity": k.activity, "lens": k.lens, "kpi": k.name, "value": value,
                    "status": status(value, cfg), "source": f"{k.file}.{k.query}", "window": k.window,
                    "detail": detail(cache[key]) if detail else None})
    return out


def cells(rows, cfg):
    """{cadence: {lens: {status, value, kpis, with_data, counts}}}: the status of the average of a cell's KPIs that have data."""
    grid = {c: {l: {"status": "no_data", "value": None, "kpis": 0, "with_data": 0,
                    "counts": {"on_track": 0, "watch": 0, "off_track": 0, "no_data": 0}} for l in LENSES} for c in CADENCES}
    values = {(c, l): [] for c in CADENCES for l in LENSES}
    for r in rows:
        cell = grid[r["cadence"]][r["lens"]]
        cell["kpis"] += 1
        cell["counts"][r["status"]] += 1
        if r["value"] is not None:
            cell["with_data"] += 1
            values[(r["cadence"], r["lens"])].append(r["value"])
    for (c, l), vals in values.items():
        if vals:
            grid[c][l]["value"] = sum(vals) / len(vals)
            grid[c][l]["status"] = status(grid[c][l]["value"], cfg)
    return grid


REASONS = {
    "no_quiz": "no quiz started in the last {n} days",
    "no_focus": "no valid focus minutes in the last {n} days",
    "syllabus_behind": "behind the syllabus pace",
    "roadmap_off_track": "roadmap items missed their deadlines",
    "tasks_slipping": "less than half of to-dos done",
}


def student_signals(con, cfg, end):
    """One dict per active student with the numbers behind the off-track reasons and the reasons themselves. Everything the student list and
    the student page show comes from here, so a number has one definition."""
    period_start, quarter_start = windows(cfg, end)
    per = metrics.params(cfg, period_start, end)
    qtr = metrics.params(cfg, quarter_start, end)
    n = cfg["scorecard"]["lookback_days"]
    syl = {r["student_id"]: r for r in metrics.run(con, "weekly", "syllabus_pace_by_student", per)}
    road = {r["student_id"]: r for r in metrics.run(con, "roadmaps", "roadmap_on_track_by_student", qtr)}
    task = {r["student_id"]: r for r in metrics.run(con, "given", "task_metrics_by_student", per)}
    ready = {r["student_id"]: r for r in metrics.run(con, "given", "chapter_readiness_by_student", per)}
    out = []
    for a in metrics.run(con, "students", "student_activity", per):
        sid, why = a["student_id"], []
        if a["quizzes_due"] and not a["quizzes_started"]:
            why.append("no_quiz")
        if not a["focus_minutes"]:
            why.append("no_focus")
        if sid in syl and not syl[sid]["on_track"]:
            why.append("syllabus_behind")
        if sid in road and not road[sid]["on_track"]:
            why.append("roadmap_off_track")
        if sid in task and task[sid]["task_completion_rate"] < cfg["scorecard"]["watch_min"]:
            why.append("tasks_slipping")
        out.append({
            "student_id": sid, "name": a["name"], "advisor_id": a["advisor_id"], "reasons": why,
            "explanations": [REASONS[w].format(n=n) for w in why],
            "days_since_activity": a["days_since_activity"], "last_activity": a["last_activity"],
            "days_enrolled": a["days_enrolled"], "new_student": a["days_enrolled"] < cfg["scorecard"]["window_days"],
            "quizzes_due": a["quizzes_due"], "quizzes_started": a["quizzes_started"], "focus_minutes": a["focus_minutes"],
            "syllabus_pct": syl[sid]["completion_pct"] if sid in syl else None, "syllabus_pace_pct": syl[sid]["pace_pct"] if sid in syl else None,
            "syllabus_on_track": syl[sid]["on_track"] if sid in syl else None,
            "roadmap_pct": road[sid]["pct"] if sid in road else None, "roadmap_on_track": road[sid]["on_track"] if sid in road else None,
            "task_completion_rate": task[sid]["task_completion_rate"] if sid in task else None,
            "deadline_adherence": task[sid]["deadline_adherence"] if sid in task else None,
            "readiness_score": ready[sid]["readiness_score"] if sid in ready else None,
        })
    return out


def student_table(con, cfg, end):
    """Every active student, listed ones first (worst first), with a `listed` flag.
    A student is listed with at least scorecard.off_track_min_reasons reasons to look at. new_student marks someone enrolled for less than
    scorecard.window_days: they can be listed, but have not had a full window to build a record."""
    need = cfg["scorecard"]["off_track_min_reasons"]
    rows = [{**r, "listed": len(r["reasons"]) >= need} for r in student_signals(con, cfg, end)]
    return sorted(rows, key=lambda r: (not r["listed"], -len(r["reasons"]), -(r["days_since_activity"] if r["days_since_activity"] is not None else 10**6), r["student_id"]))


def off_track(con, cfg, end):
    """The listed students of student_table, worst first."""
    return [r for r in student_table(con, cfg, end) if r["listed"]]


def student_timeline(con, cfg, end, student_id, days=None):
    """The student's last `days` days (default scorecard.window_days), oldest first (see students.sql student_timeline)."""
    days = days or cfg["scorecard"]["window_days"]
    prm = metrics.params(cfg, end - timedelta(days=days - 1), end)
    return metrics.run(con, "students", "student_timeline", {**prm, "student_id": student_id})


def recent_runs(con, cfg, end):
    return metrics.run(con, "health", "recent_runs", metrics.params(cfg, end, end))


def freshness(con, cfg, end):
    return metrics.run(con, "health", "source_freshness", metrics.params(cfg, end, end))


def history_start(con):
    """First day the database has events for: a comparison window that begins before it would read missing data as a drop."""
    return metrics.run(con, "health", "history_start", {})[0]["first_day"]


def previous_values(con, cfg, end):
    """{(activity, kpi): value} for the same KPIs window_days earlier, or None when there is nothing fair to compare with: the earlier window starts
    before the data does, or (for a quarter-so-far KPI) the earlier day falls in the previous quarter, which would compare unlike periods."""
    days = cfg["scorecard"]["window_days"]
    prev_end = end - timedelta(days=days)
    if prev_end - timedelta(days=days - 1) < history_start(con):
        return None
    same_quarter = metrics.quarter_for(prev_end, cfg)[0] == metrics.quarter_for(end, cfg)[0]
    window = {(k.activity, k.name): k.window for k in KPIS}
    return {(r["activity"], r["kpi"]): (None if window[(r["activity"], r["kpi"])] == "quarter" and not same_quarter else r["value"])
            for r in kpi_rows(con, cfg, prev_end)}


def add_trend(rows, previous):
    """Each KPI row gets `delta`: its value minus the earlier value, in share points (0.04 = up 4 points); None when either side has no value."""
    for r in rows:
        before = None if previous is None else previous.get((r["activity"], r["kpi"]))
        r["delta"] = None if r["value"] is None or before is None else r["value"] - before
    return rows


def whoop_reconnect(con, cfg, end):
    """The students behind a 'need to reconnect Whoop' note (see sql/metrics/health.sql whoop_reconnect)."""
    return metrics.run(con, "health", "whoop_reconnect", metrics.params(cfg, end, end))


def build(con, cfg, end):
    """Everything the front page needs for the as-of day `end`."""
    rows = add_trend(kpi_rows(con, cfg, end), previous_values(con, cfg, end))
    days = cfg["scorecard"]["window_days"]
    earlier = student_table(con, cfg, end - timedelta(days=days)) if end - timedelta(days=days * 2 - 1) >= history_start(con) else None
    return {"as_of": end, "kpis": rows, "cells": cells(rows, cfg), "off_track": off_track(con, cfg, end), "freshness": freshness(con, cfg, end),
            "attention_before": None if earlier is None else sum(1 for r in earlier if r["listed"])}
