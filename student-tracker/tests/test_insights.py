"""The product-owner read-outs: verdict sentences, gaps, movement and the engagement panel."""
import insights
import ui
from tests.test_metrics import CFG


def kpi(name, value, status, delta=None, activity="A", detail=None, lens="conducted"):
    return {"kpi": name, "value": value, "status": status, "delta": delta, "activity": activity, "detail": detail, "lens": lens, "cadence": "daily"}


ROWS = [kpi("a", 0.95, "on_track", 0.04), kpi("b", 0.60, "watch", -0.05), kpi("c", 0.10, "off_track", 0.0, detail="1 of 10 things"), kpi("d", None, "no_data")]


def test_gaps_and_bright_spots_leave_out_the_other_group_and_the_unmeasured():
    assert [r["kpi"] for r in insights.gaps(ROWS)] == ["c", "b"]
    assert [r["kpi"] for r in insights.bright_spots(ROWS)] == ["a"]


def test_summary_names_the_biggest_gap_with_its_count_and_the_movement():
    out = insights.summary(ROWS, CFG)
    assert out[0] == "1 of 3 measurable KPIs are on track."
    assert out[1] == "Biggest gap: c (A) at 10%, 1 of 10 things."
    assert out[2] == "Against the previous 30 days: up on 1 KPI, down on 1."


def test_summary_has_no_movement_line_without_an_earlier_window():
    assert all("Against" not in x for x in insights.summary([{**r, "delta": None} for r in ROWS], CFG))
    assert insights.summary([kpi("d", None, "no_data")], CFG) == ["No KPI here has data yet."]


def test_activity_verdict_is_set_by_its_weakest_kpi():
    status, text = insights.activity_verdict(ROWS, CFG)
    assert status == "off_track" and text.startswith("Weakest: c at 10%") and "Strongest: a at 95%" in text
    assert insights.activity_verdict([ROWS[0]], CFG) == ("on_track", "On track.")
    assert insights.activity_verdict([ROWS[3]], CFG)[0] == "no_data"


def test_delta_text_says_the_direction_in_words_and_symbols():
    assert ui.delta_parts(0.043) == ("up", "▲ 4 pts") and ui.delta_parts(-0.2) == ("down", "▼ 20 pts")
    assert ui.delta_parts(0.004) == ("flat", "no change") and ui.delta_parts(None) == (None, "")


def student(sid, adv, started, focus, rate, syl, road):
    return {"student_id": sid, "name": f"Student {sid}", "advisor_id": adv, "quizzes_started": started, "quizzes_due": 7, "focus_minutes": focus,
            "task_completion_rate": rate, "syllabus_on_track": syl, "syllabus_pct": None if syl is None else 40, "syllabus_pace_pct": 60,
            "roadmap_on_track": road, "roadmap_pct": None if road is None else 50}


def test_engagement_counts_students_per_behaviour_with_the_right_base():
    people = [student("1", "X", 3, 60, 0.9, True, True), student("2", "X", 0, 0, 0.2, False, None), student("3", "Y", 1, 0, None, None, False)]
    got = {x["label"]: (x["count"], x["base"]) for x in insights.engagement(people, CFG)}
    assert got == {"Took a quiz recently": (2, 3), "Did focus time recently": (1, 3), "Finishing their to-dos": (1, 2),
                   "On the syllabus pace": (1, 2), "Roadmap items on time": (1, 2)}


def test_by_advisor_puts_the_busiest_caseload_first():
    groups = insights.by_advisor([{"advisor_id": "B"}, {"advisor_id": "A"}, {"advisor_id": "B"}])
    assert [(a, len(g)) for a, g in groups] == [("B", 2), ("A", 1)]


def test_a_kpi_over_an_unfinished_period_is_never_the_biggest_gap():
    rigour = kpi("Monthly rigour adherence", 0.0, "off_track", activity="Academic roadmap")
    rows = [rigour, kpi("c", 0.10, "off_track")]
    assert [r["kpi"] for r in insights.gaps(rows)] == ["c"] and insights.weakest(rows)["kpi"] == "c"
    assert insights.activity_verdict([rigour], CFG)[0] == "no_data"


def test_engagement_says_per_student_who_shows_the_behaviour_and_who_it_does_not_apply_to():
    people = [student("1", "X", 3, 60, 0.9, True, True), student("2", "X", 0, 0, None, None, False)]
    quiz, _, todos, syllabus, _ = insights.engagement(people, CFG)
    assert [(w[0]["student_id"], w[1], w[2]) for w in quiz["who"]] == [("1", True, "3 of 7 quizzes"), ("2", False, "0 of 7 quizzes")]
    assert [w[1] for w in todos["who"]] == [True, None] and [w[1] for w in syllabus["who"]] == [True, None]   # not applicable is None, not a failure
