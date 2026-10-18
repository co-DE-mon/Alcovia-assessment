"""The HTML helpers: thresholds in the numbers, escaping, and that status is never colour alone."""
from datetime import date

import pytest

import scorecard as sc
import ui
from tests.test_metrics import CFG


@pytest.mark.parametrize("value,expected", [(None, "—"), (0.0, "0%"), (0.5, "50%"), (0.83, "83%"), (1.0, "100%"),
                                            (0.7997, "79.9%"), (0.4999, "49.9%"), (0.795, "79.5%"), (0.7949, "79%")])
def test_pct_never_rounds_a_value_up_across_a_threshold(value, expected):
    assert ui.pct(value, CFG) == expected


def test_pct_without_config_just_rounds():
    assert ui.pct(0.7997) == "80%"


def test_every_status_chip_has_an_icon_and_a_label():
    for status, (label, glyph, fill, ink) in ui.STATUS.items():
        html = ui.chip(status)
        assert label in html and glyph in html and fill in html and 'aria-hidden="true"' in html


def test_the_status_palette_is_the_fixed_one():
    assert [ui.STATUS[s][2] for s in ("on_track", "watch", "off_track")] == ["#3aa675", "#e9b44c", "#dc6b6b"]


def test_meter_is_accessible_clamped_and_marks_both_lines():
    html = ui.meter(1.4, "on_track", CFG, "Daily conducted: 140%")
    assert 'role="meter"' in html and 'aria-valuenow="100"' in html and "width:100.0%" in html
    assert html.count("sv-tick") == 2 and 'left:50%' in html and 'left:80%' in html
    assert "aria-valuenow" not in ui.meter(None, "no_data", CFG, "x")          # no value, no reading


def test_user_visible_text_is_escaped():
    row = {"name": "<script>alert(1)</script>", "student_id": 'a"b', "advisor_id": "<b>x</b>", "days_since_activity": 3,
           "new_student": False, "reasons": ["no_quiz"], "explanations": ['"><img src=x>']}
    html = ui.attention_row(row)
    assert "<script>" not in html and "<img" not in html and "&lt;script&gt;" in html and "&quot;&gt;&lt;img" in html
    assert "<b>x</b>" not in html
    kpi = ui.kpi_row({"kpi": "<i>x</i>", "value": 0.5, "status": "watch", "source": "a.b<c"}, CFG)
    assert "<i>x</i>" not in kpi and "&lt;i&gt;" in kpi and "a.b&lt;c" in kpi
    assert "<u>" not in ui.tile("<u>", "<u>", "<u>") and "<u>" not in ui.page_header("<u>", "<u>")


def grid_cells():
    cells = {c: {l: {"status": "watch", "value": 0.6, "kpis": 2, "with_data": 2, "counts": {"on_track": 0, "watch": 2, "off_track": 0, "no_data": 0}}
                 for l in ui.LENS_LABEL} for c in sc.CADENCES}
    cells["daily"]["liked"] = {"status": "no_data", "value": None, "kpis": 1, "with_data": 0, "counts": {"on_track": 0, "watch": 0, "off_track": 0, "no_data": 1}}
    return cells


def test_scorecard_grid_has_a_cell_per_cadence_and_lens_and_says_when_there_is_no_data():
    html = ui.scorecard_grid(grid_cells(), sc.CADENCES, CFG, {c: "last 30 days" for c in sc.CADENCES})
    assert html.count('class="sv-cell ') == 15 and html.count("sv-rowlabel") == 5
    assert "No KPI had data in this window" in html and "0 on track · 2 watch · 0 off track" in html
    assert "\n" not in html                                                     # Markdown would read indented HTML lines as code


def test_quiz_strip_uses_three_distinct_shapes_not_just_colours():
    day = lambda held, started: {"day": date(2026, 10, 1), "quiz_held": held, "quiz_started": started}
    html = ui.quiz_strip([day(True, True), day(True, False), day(False, False)])
    assert "sv-day-yes" in html and "sv-day-no" in html and "sv-day-none" in html
    assert 'title="1 Oct: started the quiz"' in html and "held, not started" in html and "no quiz that day" in html


def test_source_card_shows_stale_fresh_and_the_error_only_when_the_latest_run_was_not_ok():
    import datetime as dt
    base = {"source": "whoop", "last_ok_at": dt.datetime(2026, 10, 21, 2, 3), "hours_since_ok": 93, "last_run_at": None, "last_status": "partial",
            "last_error": "2 students need to reconnect", "failed_7d": 0, "partial_7d": 3, "stale": True}
    stale = ui.source_card(base)
    assert "Stale" in stale and "93 h ago" in stale and "2 students need to reconnect" in stale
    ok = ui.source_card({**base, "stale": False, "last_status": "ok", "last_error": "old error"})
    assert "Fresh" in ok and "old error" not in ok
    assert "No successful run yet" in ui.source_card({**base, "last_ok_at": None, "hours_since_ok": None, "last_status": None, "last_error": None})


def test_legend_names_every_status_with_the_configured_thresholds():
    html = ui.legend(CFG)
    assert "On track ≥ 80%" in html and "Watch 50–80%" in html and "Off track &lt; 50%" in html and "No data" in html


def test_plain_text_and_windows_follow_config_not_fixed_numbers():
    cfg = {**CFG, "scorecard": {**CFG["scorecard"], "window_days": 14}, "syllabus": {**CFG["syllabus"], "quarter_target_pct": 30},
           "quiz": {**CFG["quiz"], "entry_window_minutes": 10, "regular_taker_days": [3, 5]}, "wellness": {**CFG["wellness"], "connected_after_days": 45}}
    assert "30%-a-quarter" in ui.plain_text("Students on the syllabus pace", cfg)
    assert "within 10 minutes" in ui.plain_text("Started inside the entry window", cfg)
    assert "at least 3 of the last 5 quizzes" in ui.plain_text("Regular quiz takers (proxy)", cfg)
    assert "after 45 days" in ui.plain_text("Calendar still connected (proxy)", cfg)
    assert 'title="Against the previous 14 days"' in ui.delta_chip(0.05, 14)
    for kpi in ui.KPI_PLAIN:
        assert "{" not in ui.plain_text(kpi, cfg)            # every placeholder is filled
