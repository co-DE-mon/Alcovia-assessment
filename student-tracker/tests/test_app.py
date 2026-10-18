"""The dashboard renders every page without an error and shows what it promises. Streamlit's AppTest runs the real pages in-process."""
from datetime import timedelta

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import AS_OF, ROOT

HARNESS = "import streamlit as st\nimport ui\nfrom views import {module}\nst.markdown(ui.CSS, unsafe_allow_html=True)\n{call}\n"
PAGES = [("overview", "overview.page()"), ("cadence", 'cadence.page("daily")'), ("cadence", 'cadence.page("weekly")'),
         ("cadence", 'cadence.page("monthly")'), ("cadence", 'cadence.page("quarterly")'), ("cadence", 'cadence.page("roadmaps")'),
         ("students", "students.page()"), ("health", "health.page()"), ("definitions", "definitions.page()")]


def run(module, call, as_of=AS_OF):
    at = AppTest.from_string(HARNESS.format(module=module, call=call), default_timeout=90)
    at.session_state["as_of"] = as_of
    return at.run()


def text(at):
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [s.value for s in at.success] + [i.value for i in at.info])


@pytest.mark.parametrize("module,call", PAGES)
def test_every_page_renders_without_an_exception(module, call):
    at = run(module, call)
    assert not at.exception, [e.value for e in at.exception]


def test_overview_shows_the_scorecard_the_attention_list_and_the_health_cards():
    at = run("overview", "overview.page()")
    body = text(at)
    assert "Student progress" in body and "Dummy data" in body                       # header carries the badge
    assert "sv-grid" in body and body.count("sv-cell ") == 15 and "Conducted" in body   # 5 cadences x 3 lenses
    assert "Needs attention" in body and "DEMO-S17" in body and "Demo Student 17" in body
    assert "whoop" in body and "Stale" in body and "Fresh" in body
    assert "On track" in body and "Off track" in body and "No data" in body            # the legend names every status
    assert len(at.expander) == 2 and len(at.dataframe) == 1                            # the full scorecard, and the table view of every KPI
    assert "need attention, and" in body and "Biggest gap:" in body and "How engaged are students?" in body and "Bright spots" in body
    assert "Against the previous 30 days" in body                                      # the trend line, at the default date which has an earlier window


def test_status_is_never_colour_only_on_the_overview():
    body = text(run("overview", "overview.page()"))
    assert body.count('class="sv-ico"') >= 15 and body.count("sv-chip ") >= 15        # every chip carries an icon


def test_each_cadence_page_shows_its_activities_and_a_table_view():
    daily = text(run("cadence", 'cadence.page("daily")'))
    for activity in ("8pm quiz", "Focus time", "Timetable", "Active minutes", "Recovery"):
        assert activity in daily
    assert "Last 30 days" in daily
    roadmaps = text(run("cadence", 'cadence.page("roadmaps")'))
    assert "Quarter so far (2026-27 Q3)" in roadmaps and "Career" in roadmaps
    assert len(run("cadence", 'cadence.page("daily")').get("vega_lite_chart")) == 2                # the two trends, one per scale


def test_students_page_filters_by_advisor_and_by_attention():
    at = run("students", "students.page()")
    assert not at.exception and len(at.selectbox) == 1 and len(at.toggle) == 1
    assert "19 of 19 students" in text(at)
    at.selectbox[0].select("DEMO-ADV-3").run()
    assert not at.exception and "7 of 19" not in text(at) and " of 19 students" in text(at)
    at.toggle[0].set_value(True).run()
    assert not at.exception


def test_a_student_dialog_shows_the_summary_and_every_record_section():
    """A dataframe row cannot be clicked in AppTest, so the dialog's body is run directly for one student."""
    call = ('import data\nrows = data.students(data.as_of())\ns = next(r for r in rows if r["student_id"].endswith("S17"))\n'
            'students.open_student(s, data.as_of(), data.config())')
    at = run("students", call)
    body = text(at)
    tabs = [t.label for t in at.tabs]
    assert not at.exception, [e.value for e in at.exception]
    assert "Demo Student 17" in body and "sv-strip" in body and "All records" in body
    assert tabs == ["Quizzes", "Focus", "To-dos", "Events and sessions", "Roadmaps", "Academics", "Wearable"]


def test_data_health_names_the_students_behind_the_whoop_problem():
    body = text(run("health", "health.page()"))
    assert "Students who need to reconnect Whoop" in body and "Runs that did not load completely" in body
    at = run("health", "health.page()")
    reconnect = next(df.value for df in at.dataframe if "Why" in df.value.columns)
    assert list(reconnect["ID"]) == ["DEMO-S02"] and reconnect["Why"].iloc[0] == "Disconnected the Whoop"
    assert reconnect["Days without data"].iloc[0] == 21


def test_data_health_page_lists_runs_and_can_filter_by_source():
    at = run("health", "health.page()")
    assert not at.exception and "stale" in text(at) and "whoop" in text(at)
    at.selectbox[0].select("clickup").run()
    assert not at.exception


@pytest.mark.parametrize("back", [0, 15, 30, 45, 60])
def test_pages_render_for_dates_across_the_whole_history(back):
    day = AS_OF - timedelta(days=back)
    for module, call in (("overview", "overview.page()"), ("cadence", 'cadence.page("quarterly")'), ("students", "students.page()")):
        at = run(module, call, day)
        assert not at.exception, (back, module, [e.value for e in at.exception])


def test_the_full_app_starts_on_the_overview_with_navigation_and_the_dummy_banner():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    body = text(at)
    assert "Dummy data." in body and "Student progress" in body and len(at.sidebar.date_input) == 1
    assert at.sidebar.date_input[0].value == AS_OF


@pytest.mark.parametrize("cadence", ["daily", "weekly", "monthly", "quarterly", "roadmaps"])
def test_every_kpi_opens_its_records(cadence):
    """Click each 'See the records' button: the dialog opens without an error and shows a table, or says there is nothing behind the KPI."""
    keys = [b.key for b in run("cadence", f'cadence.page("{cadence}")').button if b.key and b.key.startswith("drill-")]
    assert keys
    for key in keys:
        at = run("cadence", f'cadence.page("{cadence}")')
        next(b for b in at.button if b.key == key).click()
        at.run()
        assert not at.exception, (key, [e.value for e in at.exception])
        assert any(c.value.endswith(" rows") for c in at.caption) or any("No records" in i.value for i in at.info), key


def test_overview_has_no_trend_when_there_is_no_earlier_window():
    from datetime import timedelta
    body = text(run("overview", "overview.page()", as_of=AS_OF - timedelta(days=60)))
    assert "Against the previous 30 days" not in body and "Biggest gap:" in body       # no earlier data to compare with, so no made-up change


def test_cadence_pages_lead_with_a_verdict_and_a_verdict_per_activity():
    body = text(run("cadence", 'cadence.page("daily")'))
    assert "measurable KPIs are on track" in body and "Weakest:" in body and "sv-act-head" in body
    assert "Each tile is the average" not in body                                      # the lens-average tiles are gone


def test_every_overview_number_opens_the_records_behind_it():
    """Click each 'See ...' button on the overview: the dialog opens without an error and holds a table, and a student's Open button opens their profile."""
    keys = [b.key for b in run("overview", "overview.page()").button if b.key and b.key.startswith("see-overview-")]
    assert len(keys) >= 4 + 5 + 5                                   # four tiles, five engagement rows, and the students who need attention
    for key in keys:
        at = run("overview", "overview.page()")
        next(b for b in at.button if b.key == key).click()
        at.run()
        assert not at.exception, (key, [e.value for e in at.exception])
        if key.startswith("see-overview-student-"):
            assert "All records" in text(at), key
        else:
            assert len(at.dataframe) >= 2, key                          # the page's own table view, and the dialog's


def test_definitions_covers_every_displayed_kpi_and_current_assumptions():
    import scorecard

    at = run("definitions", "definitions.page()")
    assert not at.exception, [e.value for e in at.exception]
    assert [tab.label for tab in at.tabs] == ["How to read this", "KPI catalogue", "Assumptions"]
    body = text(at)
    for kpi in scorecard.KPIS:
        assert kpi.name in body, (kpi.activity, kpi.name)
    assert "`SignificantlyDone` is incomplete" in body
    assert "without requiring a current-quarter plan" in body
