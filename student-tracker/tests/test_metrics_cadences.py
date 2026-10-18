"""Weekly, event (monthly and quarterly), quarterly and roadmap queries. Hand-made rows pin each definition; the seed pins the stories."""
from datetime import date, timedelta
from math import ceil

import pytest

import metrics
from tests.conftest import AS_OF
from tests.test_metrics import CFG, add, make, one, q, student

MONTHS_30 = 30 / 30.4375    # a 30-day period in the fractional months the queries use


def event(con, eid, kind, day, status="held", **kw):
    add(con, "events", event_id=eid, kind=kind, planned_for=f"{day} 17:00:00", status=status, source="clickup", **kw)


def invite(con, eid, sid, attended=None, outcome=None):
    add(con, "event_attendance", event_id=eid, student_id=sid, invited=True, attended=attended, outcome=outcome)


def rating(con, fid, sid, eid, kind, comp, when="2026-10-06 18:00:00", q1=None, q2=None, q3=None):
    add(con, "feedback", feedback_id=fid, student_id=sid, event_id=eid, kind=kind, q1_rating=q1, q2_rating=q2, q3_rating=q3,
        composite=comp, has_comment=False, submitted_at=when)


def todo(con, n, sid, source, due, status, created, updated):
    add(con, "todos", todo_id=f"T{n}", student_id=sid, source=source, title="t", due_date=due, status=status, created_at=created, updated_at=updated)


def item(con, n, sid, roadmap, level, due, done=None, created="2026-08-01 09:00:00"):
    add(con, "roadmap_items", item_id=f"R{n}", student_id=sid, roadmap=roadmap, level=level, title="t", created_at=created,
        due_date=due, done_at=done, source="clickup")


# ---------- weekly ----------

def test_study_plan_set_needs_both_weekday_and_weekend_hours():
    con = make()
    student(con, "both", weekday_study_hours=2, weekend_study_hours=5)
    student(con, "half", weekday_study_hours=2)
    student(con, "none")
    student(con, "gone", left_on="2026-10-01", weekday_study_hours=2, weekend_study_hours=5)
    r = one(con, "weekly", "study_plan_set", "2026-10-01", "2026-10-24")
    assert (r["active_students"], r["plan_set"]) == (3, 1) and r["plan_set_rate"] == pytest.approx(1 / 3)
    assert one(make(), "weekly", "study_plan_set", "2026-10-01", "2026-10-24")["plan_set_rate"] is None


def test_session_delivery_counts_held_cancelled_policy_and_attendance():
    con = make()
    student(con, "a")
    student(con, "b")
    for eid, kind, day, status in [("S1", "academic_session", "2026-10-05", "held"), ("S2", "academic_session", "2026-10-06", "held"),
                                   ("S3", "academic_session", "2026-10-07", "cancelled"), ("S4", "academic_session", "2026-10-30", "planned"),
                                   ("S5", "career_session", "2026-10-08", "held"), ("S6", "academic_session", "2026-09-01", "held")]:
        event(con, eid, kind, day, status)
    invite(con, "S1", "a", True)
    invite(con, "S2", "b", False)
    invite(con, "S5", "a", True)
    rows = {r["kind"]: r for r in q(con, "weekly", "session_delivery", "2026-10-01", "2026-10-30")}
    ac = rows["academic_session"]
    assert (ac["scheduled"], ac["held"], ac["cancelled"]) == (3, 2, 1) and ac["held_rate"] == pytest.approx(2 / 3)
    expected = CFG["sessions"]["policy_per_month"]["academic"] * 2 * MONTHS_30
    assert ac["policy_expected"] == pytest.approx(expected) and ac["delivered_vs_policy"] == pytest.approx(2 / expected)
    assert (ac["attended"], ac["attended_rate"]) == (1, 0.5)
    assert rows["career_session"]["held"] == 1 and rows["career_session"]["policy_expected"] == pytest.approx(4 * 2 * MONTHS_30)


def test_session_feedback_averages_session_forms_for_sessions_in_the_period_only():
    con = make()
    student(con, "a")
    student(con, "b")
    event(con, "S1", "academic_session", "2026-10-05")
    event(con, "S2", "peer_session", "2026-10-06")
    event(con, "OLD", "career_session", "2026-09-01")
    for eid, sid in [("S1", "a"), ("S1", "b"), ("S2", "a"), ("OLD", "a")]:
        invite(con, eid, sid, True)
    rating(con, "F1", "a", "S1", "session", 4.0, q1=4, q2=4, q3=4)
    rating(con, "F2", "a", "S2", "session", 2.0, q1=2, q2=2, q3=2)
    rating(con, "F3", "b", "S1", "workshop", 5.0, q1=5)          # another form kind: ignored
    rating(con, "F4", "a", "OLD", "session", 5.0, q1=5)          # session outside the period: ignored
    r = one(con, "weekly", "session_feedback", "2026-10-01", "2026-10-30")
    assert (r["attended_sessions"], r["responses"]) == (3, 2) and r["response_rate"] == pytest.approx(2 / 3)
    assert r["avg_composite"] == 3.0 and r["avg_q1"] == 3.0
    assert one(make(), "weekly", "session_feedback", "2026-10-01", "2026-10-30")["response_rate"] is None


def test_syllabus_pace_uses_the_latest_reading_on_or_before_the_end_and_the_pace_param():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    student(con, "gone", left_on="2026-10-01")
    for sid, day, done in [("a", "2026-10-20", 50), ("a", "2026-10-22", 60), ("a", "2026-10-25", 99),   # the 25th is after the end
                           ("b", "2026-10-24", 40), ("gone", "2026-10-24", 90)]:
        add(con, "syllabus_daily", student_id=sid, day=day, chapters_completed=done, total_chapters=100)
    p = metrics.params(CFG, date(2026, 10, 18), date(2026, 10, 24))
    assert p["syllabus_pace_pct"] == pytest.approx(25 * (2 + 54 / 91))              # two quarters done, 54 of 91 days into the third
    rows = {r["student_id"]: r for r in q(con, "weekly", "syllabus_pace_by_student", "2026-10-18", "2026-10-24")}
    assert set(rows) == {"a", "b"}                                                  # no history and left students are absent
    assert rows["a"]["completion_pct"] == 60 and rows["a"]["days_stale"] == 2 and rows["a"]["on_track"]
    assert rows["b"]["completion_pct"] == 40 and not rows["b"]["on_track"]          # 80% of the pace is 51.9
    c = one(con, "weekly", "syllabus_pace", "2026-10-18", "2026-10-24")
    assert (c["students"], c["on_track"], c["on_track_rate"]) == (2, 1, 0.5) and c["avg_completion_pct"] == 50


def test_advisor_todos_counts_only_assigned_ones_due_in_the_period():
    con = make()
    student(con, "a")
    todo(con, 1, "a", "admin_assigned", "2026-10-05", "done", "2026-10-01 09:00:00", "2026-10-05 10:00:00")   # on time
    todo(con, 2, "a", "admin_assigned", "2026-10-06", "done", "2026-10-01 09:00:00", "2026-10-08 10:00:00")   # late
    todo(con, 3, "a", "admin_assigned", "2026-10-07", "pending", "2026-10-01 09:00:00", "2026-10-01 09:00:00")
    todo(con, 4, "a", "manual", "2026-10-05", "done", "2026-10-01 09:00:00", "2026-10-05 10:00:00")           # not assigned by staff
    todo(con, 5, "a", "admin_assigned", "2026-09-05", "done", "2026-09-01 09:00:00", "2026-09-05 10:00:00")   # outside the period
    r = one(con, "weekly", "advisor_todos", "2026-10-01", "2026-10-31")
    assert (r["assigned"], r["done"], r["done_on_time"]) == (3, 2, 1)
    assert r["done_rate"] == pytest.approx(2 / 3) and r["on_time_rate"] == pytest.approx(1 / 3)
    assert one(make(), "weekly", "advisor_todos", "2026-10-01", "2026-10-31")["on_time_rate"] is None


def test_student_input_cadence_counts_own_todos_and_completions_in_the_last_seven_days():
    con = make()
    for sid in ("own", "done", "old", "assigned"):
        student(con, sid)
    student(con, "gone", left_on="2026-10-01")
    todo(con, 1, "own", "manual", "2026-10-30", "pending", "2026-10-20 10:00:00", "2026-10-20 10:00:00")        # created by the student, in window
    todo(con, 2, "done", "admin_assigned", "2026-10-22", "done", "2026-10-01 10:00:00", "2026-10-23 10:00:00")  # marked done in window
    todo(con, 3, "old", "manual", "2026-10-10", "done", "2026-10-10 10:00:00", "2026-10-10 11:00:00")           # before the window
    todo(con, 4, "assigned", "admin_assigned", "2026-10-30", "pending", "2026-10-22 10:00:00", "2026-10-22 10:00:00")   # staff-created: not the student's input
    r = one(con, "weekly", "student_input_cadence", "2026-10-18", "2026-10-24")
    assert (r["active_students"], r["filled_inputs"]) == (4, 2) and r["filled_rate"] == 0.5


# ---------- events: monthly and quarterly activities ----------

def test_event_delivery_held_rate_and_expected_counts_from_config():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    for eid, kind, day, status in [("W1", "workshop", "2026-10-05", "held"), ("W2", "workshop", "2026-10-19", "held"),
                                   ("W3", "workshop", "2026-10-12", "cancelled"), ("W4", "workshop", "2026-10-30", "planned"),
                                   ("M1", "mentor_call", "2026-10-03", "held"), ("M2", "mentor_call", "2026-10-04", "held"),
                                   ("P1", "pod", "2026-10-10", "held"), ("PC1", "podcast", "2026-10-11", "held")]:
        event(con, eid, kind, day, status)
    rows = {r["kind"]: r for r in q(con, "events", "event_delivery", "2026-10-01", "2026-10-30")}
    w = rows["workshop"]
    assert (w["scheduled"], w["held"], w["cancelled"], w["still_planned"]) == (3, 2, 1, 1) and w["held_rate"] == pytest.approx(2 / 3)
    assert w["expected"] == pytest.approx(2 * MONTHS_30) and w["delivered_vs_expected"] == pytest.approx(2 / (2 * MONTHS_30))
    assert rows["mentor_call"]["expected"] == pytest.approx(1 * 3 * MONTHS_30)
    assert rows["pod"]["expected"] == pytest.approx(ceil(3 / 5) * MONTHS_30)
    assert rows["podcast"]["expected"] is None and rows["podcast"]["delivered_vs_expected"] is None


def test_event_attendance_rates_use_held_events_only_and_skip_quizzes():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    event(con, "W1", "workshop", "2026-10-05")
    event(con, "W2", "workshop", "2026-10-20", status="planned")
    event(con, "QZ", "quiz", "2026-10-05")
    for sid, att in [("a", True), ("b", True), ("c", False)]:
        invite(con, "W1", sid, att)
        invite(con, "QZ", sid, True)
    invite(con, "W2", "a", None)
    rows = {r["kind"]: r for r in q(con, "events", "event_attendance_rates", "2026-10-01", "2026-10-30")}
    assert set(rows) == {"workshop"}
    w = rows["workshop"]
    assert (w["events_held"], w["invited"], w["attended"], w["not_attended"]) == (1, 3, 2, 1) and w["attended_rate"] == pytest.approx(2 / 3)


def test_event_feedback_response_rate_nps_and_a_kind_without_a_form():
    con = make()
    for sid in ("a", "b"):
        student(con, sid)
    event(con, "W1", "workshop", "2026-10-05", nps_score=8.0)
    event(con, "W2", "workshop", "2026-10-19", nps_score=6.0)
    event(con, "B1", "branding_shoot", "2026-10-07")
    for eid in ("W1", "W2", "B1"):
        for sid in ("a", "b"):
            invite(con, eid, sid, True)
    rating(con, "F1", "a", "W1", "workshop", 4.0, q1=4, q2=4, q3=4)
    rating(con, "F2", "b", "W1", "workshop", 5.0, q1=5, q2=5, q3=5)
    rating(con, "F3", "a", "W2", "workshop", 3.0, q1=3, q2=3, q3=3)
    rows = {r["kind"]: r for r in q(con, "events", "event_feedback", "2026-10-01", "2026-10-30")}
    w = rows["workshop"]
    assert (w["attended"], w["responses"]) == (4, 3) and w["response_rate"] == 0.75
    assert w["avg_composite"] == 4.0 and w["avg_q1"] == 4.0 and w["avg_nps"] == 7.0 and w["nps_events"] == 2
    b = rows["branding_shoot"]
    assert b["responses"] == 0 and b["response_rate"] == 0 and b["avg_composite"] is None and b["avg_nps"] is None


def test_posted_clips_counts_only_clips_posted_by_the_end():
    con = make()
    student(con, "a")
    event(con, "B1", "branding_shoot", "2026-10-05", posted_on="2026-10-10", views=100, shares=10)
    event(con, "B2", "branding_shoot", "2026-10-10", posted_on="2026-10-20", views=300, shares=30)
    event(con, "B3", "branding_shoot", "2026-10-12")                                                  # not posted yet
    event(con, "B4", "branding_shoot", "2026-10-15", posted_on="2026-11-05", views=999, shares=99)    # posted after the end
    event(con, "B5", "branding_shoot", "2026-10-16", status="cancelled")                              # not held
    rows = q(con, "events", "posted_clips", "2026-10-01", "2026-10-30")
    assert [r["kind"] for r in rows] == ["branding_shoot"]
    r = rows[0]
    assert (r["held"], r["posted"], r["posted_rate"]) == (4, 2, 0.5)
    assert r["avg_days_to_post"] == 7.5 and r["avg_views"] == 200 and r["avg_shares"] == 20


# ---------- quarterly ----------

def test_competition_outcomes_counts_assigned_entrants_and_stages_and_ignores_cancelled():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    event(con, "C1", "competition", "2026-09-30")
    event(con, "C2", "competition", "2026-10-10", status="cancelled")
    event(con, "C3", "competition", "2026-11-25", status="planned")
    invite(con, "C1", "a", True, "placed")
    invite(con, "C1", "b", True, "shortlisted")
    invite(con, "C1", "c", False)
    invite(con, "C2", "a", None)       # cancelled: ignored
    invite(con, "C3", "c", None)       # not held yet: assigned, outcome unknown
    r = one(con, "quarterly", "competition_outcomes", "2026-09-01", "2026-11-30")
    assert (r["active_students"], r["assigned_students"], r["entries"], r["shortlisted"], r["placed"]) == (3, 3, 2, 1, 1)
    assert r["assigned_rate"] == 1.0 and r["entered_rate"] == pytest.approx(2 / 3)    # the future competition is not counted as a miss
    assert one(make(), "quarterly", "competition_outcomes", "2026-09-01", "2026-11-30")["entered_rate"] is None


def test_social_work_groups_sizes_activities_and_attendance():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    for eid, group, day, status in [("E1", "G1", "2026-09-05", "held"), ("E2", "G1", "2026-09-20", "held"), ("E3", "G2", "2026-09-06", "held"),
                                    ("E4", "G2", "2026-09-21", "cancelled"), ("E5", "G2", "2026-11-19", "planned")]:
        event(con, eid, "social_work", day, status, group_id=group)
    for eid, sid, att in [("E1", "a", True), ("E1", "b", True), ("E2", "a", True), ("E2", "b", False), ("E3", "c", True)]:
        invite(con, eid, sid, att)
    for eid in ("E4", "E5"):
        invite(con, eid, "c", None)
    r = one(con, "quarterly", "social_work_groups", "2026-09-01", "2026-11-30")
    assert (r["groups_formed"], r["groups_expected"], r["min_group_size"], r["max_group_size"]) == (2, 1, 1, 2)
    assert (r["activities_held"], r["activities_scheduled"], r["still_planned"]) == (3, 4, 1) and r["held_rate"] == 0.75
    assert (r["invited"], r["attended"]) == (5, 4) and r["attended_rate"] == 0.8


# ---------- roadmaps ----------

def test_roadmap_status_separates_on_time_late_open_and_done_after_the_end():
    con = make()
    student(con, "a")
    student(con, "b")
    student(con, "gone", left_on="2026-10-01")
    item(con, 1, "a", "career", "quarterly", "2026-10-10", done="2026-10-08 10:00:00")     # by deadline
    item(con, 2, "b", "career", "quarterly", "2026-10-10", done="2026-10-12 10:00:00")     # late
    item(con, 3, "a", "personal", "monthly", "2026-10-15")                                 # open
    item(con, 4, "b", "personal", "monthly", "2026-10-20", done="2026-11-02 10:00:00")     # done after the end: still open at the end
    item(con, 5, "a", "personal", "monthly", "2026-11-20")                                 # not due in the period
    item(con, 6, "gone", "career", "quarterly", "2026-10-10", done="2026-10-08 10:00:00")  # left
    rows = {(r["roadmap"], r["level"]): r for r in q(con, "roadmaps", "roadmap_status", "2026-10-01", "2026-10-24")}
    c = rows[("career", "quarterly")]
    assert (c["items_due"], c["done_by_deadline"], c["done_late"], c["open_items"]) == (2, 1, 1, 0) and c["done_by_deadline_rate"] == 0.5
    p = rows[("personal", "monthly")]
    assert (p["items_due"], p["done_by_deadline"], p["done_late"], p["open_items"]) == (2, 0, 0, 2) and p["done_by_deadline_rate"] == 0


def test_roadmap_on_track_uses_the_configured_threshold_inclusively():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    for n in range(5):                                       # a: 4 of 5 by deadline = 80.0 exactly
        item(con, f"a{n}", "a", "personal", "monthly", "2026-10-10", done="2026-10-09 10:00:00" if n < 4 else None)
        item(con, f"b{n}", "b", "personal", "monthly", "2026-10-10", done="2026-10-09 10:00:00" if n < 3 else None)
    rows = {r["student_id"]: r for r in q(con, "roadmaps", "roadmap_on_track_by_student", "2026-10-01", "2026-10-24")}
    assert set(rows) == {"a", "b"}                           # c has nothing due: absent
    assert rows["a"]["pct"] == 80 and rows["a"]["on_track"] and rows["b"]["pct"] == 60 and not rows["b"]["on_track"]


def test_roadmap_coverage_counts_students_with_an_item_created_by_the_end():
    con = make()
    student(con, "a")
    student(con, "b")
    item(con, 1, "a", "career", "annual", "2026-12-31")
    item(con, 2, "a", "personal", "monthly", "2026-10-31")
    item(con, 3, "b", "personal", "monthly", "2026-11-30", created="2026-10-28 09:00:00")   # created after the end
    rows = {r["roadmap"]: r for r in q(con, "roadmaps", "roadmap_coverage", "2026-10-01", "2026-10-24")}
    assert rows["career"]["students_with_roadmap"] == 1 and rows["career"]["coverage_rate"] == 0.5
    assert rows["personal"]["students_with_roadmap"] == 1 and rows["personal"]["active_students"] == 2


def test_advisor_inputs_by_kind_counts_the_months_in_the_period():
    con = make()
    student(con, "a", advisor_id="ADV1", career_counsellor_id="CC1")
    student(con, "b", advisor_id="ADV1")                                   # no counsellor
    student(con, "c", advisor_id="ADV2", career_counsellor_id="CC1")
    for sid, kind, done in [("a", "targets_aligned", True), ("b", "targets_aligned", False), ("c", "targets_aligned", True),
                            ("a", "career_roadmap_reviewed", True), ("b", "career_roadmap_reviewed", False), ("c", "career_roadmap_reviewed", False)]:
        add(con, "advisor_inputs", student_id=sid, month="2026-10-01", input_kind=kind, done=done, source="clickup")
    add(con, "advisor_inputs", student_id="a", month="2026-09-01", input_kind="targets_aligned", done=True, source="clickup")   # before the period
    kinds = {r["input_kind"]: r for r in q(con, "roadmaps", "advisor_inputs_by_kind", "2026-10-01", "2026-10-24")}
    assert kinds["targets_aligned"]["inputs_due"] == 3 and kinds["targets_aligned"]["done_rate"] == pytest.approx(2 / 3)


def test_exam_score_vs_target_leaves_unscored_exams_null():
    con = make()
    student(con, "a")
    student(con, "b")
    for sid, et, target, actual in [("a", "formative", 80, 85), ("b", "formative", 70, 60), ("a", "unit_test", 75, None), ("b", "mid_term", 70, None)]:
        add(con, "exam_targets", student_id=sid, subject="Maths", exam_type=et, target_score=target, actual_score=actual)
    rows = {r["exam_type"]: r for r in q(con, "roadmaps", "exam_score_vs_target", "2026-10-01", "2026-10-24")}
    f = rows["formative"]
    assert (f["n_scored"], f["avg_gap"], f["met_target_rate"]) == (2, -2.5, 0.5)
    u = rows["unit_test"]
    assert u["n_scored"] == 0 and u["avg_target"] == 75 and u["avg_actual"] is None and u["met_target_rate"] is None


def test_roadmap_feedback_counts_students_not_responses_for_the_response_rate():
    con = make()
    for sid in ("a", "b", "c"):
        student(con, sid)
    rating(con, "F1", "a", None, "roadmap", 4.0, when="2026-10-10 10:00:00", q1=4, q2=3, q3=5)
    rating(con, "F2", "a", None, "roadmap", 2.0, when="2026-10-20 10:00:00", q1=2, q2=2, q3=2)
    rating(con, "F3", "b", None, "session", 5.0, when="2026-10-10 10:00:00", q1=5)               # another form
    rating(con, "F4", "c", None, "roadmap", 5.0, when="2026-09-10 10:00:00", q1=5, q2=5, q3=5)   # before the period
    r = one(con, "roadmaps", "roadmap_feedback", "2026-10-01", "2026-10-24")
    assert (r["active_students"], r["students_responded"], r["responses"]) == (3, 1, 2) and r["response_rate"] == pytest.approx(1 / 3)
    assert r["avg_composite"] == 3.0 and r["avg_pace"] == 3.0 and r["avg_invested"] == 2.5 and r["avg_confidence"] == 3.5


# ---------- the planted stories show up in the metrics ----------

START = AS_OF - timedelta(days=29)
Q3 = date(2026, 9, 1)


def seeded(db, file, name, start=START, end=AS_OF):
    return metrics.run(db, file, name, metrics.params(CFG, start, end))


def test_seed_most_students_set_a_study_plan_and_three_did_not(db):
    r = seeded(db, "weekly", "study_plan_set")[0]
    assert (r["active_students"], r["plan_set"]) == (19, 16)


def test_seed_sessions_are_delivered_close_to_policy_and_feedback_is_partial(db):
    rows = {r["kind"]: r for r in seeded(db, "weekly", "session_delivery")}
    assert 0.7 < rows["academic_session"]["delivered_vs_policy"] < 1.3
    assert rows["career_session"]["delivered_vs_policy"] < rows["academic_session"]["delivered_vs_policy"] + 0.3
    f = seeded(db, "weekly", "session_feedback")[0]
    assert 0.3 < f["response_rate"] < 0.9 and 3 < f["avg_composite"] < 5


def test_seed_syllabus_pace_splits_the_class_and_the_engaged_are_ahead(db):
    rows = {r["student_id"]: r for r in seeded(db, "weekly", "syllabus_pace_by_student")}
    assert len(rows) == 19 and rows["DEMO-S01"]["on_track"] and not rows["DEMO-S17"]["on_track"]
    assert rows["DEMO-S01"]["completion_pct"] > rows["DEMO-S17"]["completion_pct"]
    c = seeded(db, "weekly", "syllabus_pace")[0]
    assert 0.25 < c["on_track_rate"] < 0.75 and c["pace_pct"] == pytest.approx(25 * (2 + 54 / 91))


def test_seed_inputs_from_students_cover_the_active_but_not_the_dormant(db):
    r = seeded(db, "weekly", "student_input_cadence")[0]
    assert 0.3 < r["filled_rate"] < 0.9 and r["active_students"] == 19


def test_seed_workshop_in_september_was_cancelled_and_august_was_rated_poorly(db):
    sep = {r["kind"]: r for r in seeded(db, "events", "event_delivery", date(2026, 9, 1), date(2026, 9, 30))}
    assert (sep["workshop"]["held"], sep["workshop"]["cancelled"]) == (1, 1) and sep["workshop"]["held_rate"] == 0.5
    nps = {m: next(r for r in seeded(db, "events", "event_feedback", date(2026, m, 1), date(2026, m + 1, 1) - timedelta(days=1))
                   if r["kind"] == "workshop")["avg_nps"] for m in (8, 9)}
    assert nps[8] < nps[9] and nps[9] > 7       # August averages a poorly rated workshop with a good one


def test_seed_pods_are_four_groups_and_the_short_pod_is_rated_lowest(db):
    sep = {r["kind"]: r for r in seeded(db, "events", "event_delivery", date(2026, 9, 1), date(2026, 9, 30))}
    assert sep["pod"]["held"] <= 4 and sep["pod"]["expected"] == pytest.approx(ceil(19 / 5) * 30 / 30.4375)
    att = {r["kind"]: r for r in seeded(db, "events", "event_attendance_rates", date(2026, 8, 1), date(2026, 10, 24))}
    assert 0 < att["pod"]["attended_rate"] < 1 and att["workshop"]["attended_rate"] < att["mentor_call"]["attended_rate"] + 0.5


def test_seed_branding_clips_are_mostly_posted_and_views_grow_with_age(db):
    r = {x["kind"]: x for x in seeded(db, "events", "posted_clips", date(2026, 8, 1), date(2026, 10, 24))}["branding_shoot"]
    assert r["posted"] > 0 and 0 < r["posted_rate"] <= 1 and r["avg_days_to_post"] > 0 and r["avg_views"] > 100


def test_seed_competition_and_social_work_in_the_quarter(db):
    c = seeded(db, "quarterly", "competition_outcomes", Q3, AS_OF)[0]
    assert c["assigned_students"] == 4 and c["entries"] >= 1 and c["entered_rate"] > 0
    s = seeded(db, "quarterly", "social_work_groups", Q3, AS_OF)[0]
    assert (s["groups_formed"], s["groups_expected"], s["min_group_size"], s["max_group_size"]) == (4, 4, 4, 5)
    assert s["activities_held"] <= s["activities_scheduled"] and 0.3 < s["attended_rate"] < 0.9


def test_seed_roadmaps_career_is_the_weakest_covered_and_dormant_students_are_off_track(db):
    cov = {r["roadmap"]: r for r in seeded(db, "roadmaps", "roadmap_coverage", Q3, AS_OF)}
    assert cov["career"]["students_with_roadmap"] == 16 and cov["personal"]["students_with_roadmap"] == 19
    by = {r["student_id"]: r for r in seeded(db, "roadmaps", "roadmap_on_track_by_student", Q3, AS_OF)}
    assert by["DEMO-S01"]["pct"] > by["DEMO-S17"]["pct"] and not by["DEMO-S17"]["on_track"]
    status = seeded(db, "roadmaps", "roadmap_status", Q3, AS_OF)
    assert {r["roadmap"] for r in status} == {"personal", "academic", "social_work", "entrepreneurship"}   # career items fall due in December
    done = {r["roadmap"]: r for r in seeded(db, "roadmaps", "roadmap_completion", Q3, AS_OF)}
    assert done["career"]["students"] == 16 and 0 < done["career"]["completion_rate"] < 0.5


def test_seed_mid_term_is_not_scored_yet_and_the_others_run_slightly_below_target(db):
    rows = {r["exam_type"]: r for r in seeded(db, "roadmaps", "exam_score_vs_target")}
    assert rows["mid_term"]["n_scored"] == 0 and rows["mid_term"]["avg_actual"] is None
    assert rows["formative"]["avg_gap"] < 5 and rows["unit_test"]["n_scored"] > 0


def test_seed_roadmap_feedback_reaches_about_half_the_students(db):
    r = seeded(db, "roadmaps", "roadmap_feedback", date(2026, 8, 1), AS_OF)[0]
    assert 0.3 < r["response_rate"] <= 1 and 3 < r["avg_composite"] < 5


def test_roadmap_completion_ignores_due_dates_and_counts_students_with_everything_done():
    con = make()
    student(con, "a")
    student(con, "b")
    student(con, "gone", left_on="2026-10-01")
    item(con, 1, "a", "career", "annual", "2026-12-31", done="2026-10-05 10:00:00")
    item(con, 2, "a", "career", "quarterly", "2026-12-01", done="2026-10-20 10:00:00")
    item(con, 3, "b", "career", "annual", "2026-12-31", done="2026-11-05 10:00:00")        # done after the end: not done at the end
    item(con, 4, "b", "career", "quarterly", "2026-12-01")
    item(con, 5, "gone", "career", "annual", "2026-12-31", done="2026-09-20 10:00:00")
    item(con, 6, "a", "personal", "monthly", "2026-10-31", created="2026-10-28 09:00:00")    # created after the end
    rows = {r["roadmap"]: r for r in q(con, "roadmaps", "roadmap_completion", "2026-10-01", "2026-10-24")}
    assert set(rows) == {"career"}
    c = rows["career"]
    assert (c["items"], c["items_done"], c["students"], c["students_all_done"]) == (4, 2, 2, 1) and c["completion_rate"] == 0.5


def test_the_input_window_comes_from_config_not_from_the_sql():
    con = make()
    student(con, "a")
    todo(con, 1, "a", "manual", "2026-10-30", "pending", "2026-10-18 10:00:00", "2026-10-18 10:00:00")   # created 6 days before the end
    base = metrics.params(CFG, date(2026, 10, 18), date(2026, 10, 24))
    rates = {days: metrics.run(con, "weekly", "student_input_cadence", {**base, "weekly_input_window_days": days})[0]["filled_rate"] for days in (3, 7)}
    assert rates == {3: 0.0, 7: 1.0}
