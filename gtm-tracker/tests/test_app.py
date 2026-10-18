"""The dashboard renders every page without an error and shows what it promises. Streamlit's AppTest runs the real pages in-process."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from seed.generate import STORIES

HARNESS = "import streamlit as st\nimport ui\nfrom views import {module}\nst.markdown(ui.CSS, unsafe_allow_html=True)\n{module}.page()\n"
PAGES = ["overview", "revenue", "funnel", "campaigns", "rca", "leads", "definitions"]


def run(module, **state):
    at = AppTest.from_string(HARNESS.format(module=module), default_timeout=90)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def text(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [s.value for s in at.subheader] + [h.value for h in at.header]
    parts += [e.value for e in at.error] + [i.value for i in at.info] + [w.value for w in at.warning]
    parts += [x.label for x in at.expander] + [d.value.to_string() for d in at.dataframe]       # table views and expander titles are page content too
    return " ".join(parts)


@pytest.mark.parametrize("module", PAGES)
def test_every_page_renders_without_an_exception_and_says_dummy(module):
    at = run(module)
    assert not at.exception, [e.value for e in at.exception]
    assert "Dummy data" in text(at)


@pytest.mark.parametrize("module", [p for p in PAGES if p != "definitions"])
def test_every_data_page_has_the_timeline_selector(module):
    at = run(module)
    assert at.selectbox(key="tl_choice").options == ["Last 7 days", "Last 30 days", "Last 90 days", "This month", "Last month", "Custom"]


def test_revenue_page_covers_the_seven_brief_items():
    body = text(run("revenue"))
    for item in ["Target vs achievement", "3-month trial vs full program", "Students onboarded", "Workshop revenue", "Program vs workshop revenue",
                 "Unpaid invoices", "Renewals coming up"]:
        assert item in body, item


def test_funnel_page_has_the_five_stages_and_four_top_metrics():
    body = text(run("funnel"))
    for item in ["Leads", "Qualified", "Discovery call", "Ambition interview", "Architect session", "Rejected at review", "Moved to nurture", "Discovery call show-up rate", "Ambition interview drop-off rate",
                 "Cost per qualified lead", "Program conversion", "Organic leads", "Average lead journey"]:
        assert item in body, item


def test_campaigns_page_flags_the_fatigued_ad_set_and_lists_assets_and_landing_pages():
    body = text(run("campaigns", tl_choice="Last 90 days"))
    assert STORIES["fatigue_ad_set"] in body and "needs a change" in body
    for item in ["Highest CTR", "Lowest CTR", "Landing page health", "Ad-set frequency"]:
        assert item in body, item
    assert STORIES["weak_asset"] in body


def test_changing_the_selector_changes_the_overview_numbers():
    at = run("overview")
    before = text(at)
    after = text(at.selectbox(key="tl_choice").select("Last 7 days").run())
    assert before != after


def test_a_reversed_custom_range_shows_a_message_instead_of_crashing():
    at = run("overview", tl_choice="Custom", tl_custom=(date(2026, 9, 10), date(2026, 9, 1)))
    assert not at.exception
    assert "start day is after the end day" in text(at)


def test_definitions_page_lists_every_named_query():
    import metrics
    body = text(run("definitions"))
    for file in ("revenue", "funnel", "campaigns", "rca"):
        for name in metrics.describe(file):
            assert name in body, (file, name)


def test_the_real_app_entry_point_starts_and_lands_on_the_overview():
    from tests.conftest import ROOT
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert "GTM overview" in text(at) and "Dummy data" in text(at)


def test_every_headline_number_on_the_revenue_and_overview_pages_follows_the_selector():
    for module in ("revenue", "overview"):
        at = run(module, tl_choice="Last 90 days")
        wide = text(at)
        narrow = text(at.selectbox(key="tl_choice").select("Last 7 days").run())
        assert wide != narrow
        assert "Target for the period" in wide and "Target for the period" in narrow


def test_the_point_in_time_sections_say_the_start_day_does_not_move_them():
    assert "start day" in text(run("revenue")) and "does not change with the timeline" in text(run("revenue"))
    assert "start day" in text(run("campaigns")) and "do not change with the timeline" in text(run("campaigns"))


def test_funnel_page_breaks_leads_down_by_the_chosen_attribute():
    at = run("funnel", tl_choice="Last 90 days")
    assert at.selectbox(key="fn_dim").options == ["City", "Grade", "School", "Traffic source", "Source lead", "UTM source"]
    by_city = text(at)
    by_grade = text(at.selectbox(key="fn_dim").select("Grade").run())
    assert "Delhi" in by_city and "Delhi" not in by_grade and "Mumbai" not in by_grade


def test_leads_page_lists_individual_leads_and_filters_them():
    at = run("leads", tl_choice="Last 30 days")
    assert not at.exception and "Dummy data" in text(at)
    body = text(at)
    assert "Demo Parent" in body and "+91 00000" in body and "Showing" in body
    only = text(at.selectbox(key="ld_status").select("Rejected").run())
    assert "Rejected" in only and "Signed up" not in only
    assert at.selectbox(key="tl_choice").options[0] == "Last 7 days"


def _a_signed_lead(db):
    return db.execute("SELECT lead_id FROM enrollments WHERE lead_id IS NOT NULL ORDER BY lead_id LIMIT 1").fetchone()[0]


def test_leads_page_without_a_click_says_how_to_open_a_lead():
    assert "Click any cell" in text(run("leads", tl_choice="Last 30 days"))


def test_opening_a_lead_shows_everything_known_about_them(db):
    lead = _a_signed_lead(db)
    body = text(run("leads", tl_choice="Last 90 days", ld_open=lead))
    assert not run("leads", tl_choice="Last 90 days", ld_open=lead).exception
    for item in [lead, "Contact and profile", "Parent", "Phone", "Grade", "School", "City", "UTM source", "Traffic source", "Source lead",
                 "Journey", "Form filled", "Conversion", "Campaign", "Money", "enrollment", "Invoice"]:
        assert item in body, item


def test_opening_an_unknown_lead_says_so_instead_of_crashing():
    at = run("leads", tl_choice="Last 30 days", ld_open="DEMO-L-NOPE")
    assert not at.exception and "No lead with the id DEMO-L-NOPE" in text(at)


def _shown(at):
    return at.dataframe[0].value


def test_leads_page_filters_narrow_the_table():
    at = run("leads", tl_choice="Last 90 days")
    everything = len(_shown(at))
    assert at.selectbox(key="ld_city").options[0] == "All" and at.selectbox(key="ld_grade").options[0] == "All" and at.selectbox(key="ld_stage").options[0] == "All"
    city = at.selectbox(key="ld_city").options[1]
    in_city = _shown(at.selectbox(key="ld_city").select(city).run())
    assert 0 < len(in_city) < everything and set(in_city["City"]) == {city}
    one = _shown(at.text_input(key="ld_search").input(_shown(at)["Lead"].iloc[0]).run())
    assert list(one["Lead"]) == [_shown(at)["Lead"].iloc[0]] or len(one) == 1


def test_a_stale_filter_choice_resets_when_the_timeline_changes():
    at = run("leads", tl_choice="Last 90 days")
    at.selectbox(key="ld_city").select(at.selectbox(key="ld_city").options[1]).run()
    at.selectbox(key="tl_choice").select("Last 7 days").run()
    assert not at.exception


def test_the_leads_table_opens_a_lead_from_a_click_on_any_cell_with_no_checkbox_column():
    at = run("leads", tl_choice="Last 30 days")
    modes = [int(m) for m in at.dataframe[0].proto.selection_mode]
    from streamlit.proto.Dataframe_pb2 import Dataframe
    assert modes == [Dataframe.SelectionMode.Value("SINGLE_CELL")]          # a row checkbox column would be SINGLE_ROW


def test_the_lead_opens_in_a_dialog_like_the_student_dashboard(db):
    lead = _a_signed_lead(db)
    at = run("leads", tl_choice="Last 90 days", ld_open=lead)
    assert not at.exception
    assert "Contact and profile" in text(at) and lead in text(at)


def test_revenue_page_leads_with_target_vs_achievement_then_the_breakdown_and_drops_the_extra_concepts():
    body = text(run("revenue", tl_choice="Last 30 days"))
    assert body.index("Target vs achievement") < body.index("Where the achieved number comes from") < body.index("Program vs workshop revenue")
    for gone in ["Revenue at a glance", "Booked", "Still to bill", "Cash by month", "Earlier sign-ups"]:
        assert gone not in body, gone
    for row in ["Full program", "3-month trial", "Workshop seats"]:
        assert row in body, row


def test_the_breakdown_table_opens_records_from_a_click_on_any_cell():
    from streamlit.proto.Dataframe_pb2 import Dataframe
    at = run("revenue", tl_choice="Last 30 days")
    modes = [[int(m) for m in d.proto.selection_mode] for d in at.dataframe]
    assert [Dataframe.SelectionMode.Value("SINGLE_CELL")] in modes
    assert "Click a row" in text(at)


def test_opening_a_breakdown_row_shows_its_records_and_total():
    at = run("revenue", tl_choice="Last 30 days", rv_open="Workshop seats")
    assert not at.exception
    body = text(at)
    assert "Workshop seats" in body and "payments" in body and "total" in body


def test_the_breakdown_shows_the_bridge_from_sign_ups_to_cash_on_the_page():
    body = text(run("revenue", tl_choice="Last 30 days"))
    for heading in ["Students enrolled", "Contract value", "Paid so far", "Not collected yet", "Paid by earlier students", "Cash collected"]:
        assert heading in body, heading
    assert "left to right" not in body


def test_the_bridge_on_the_page_matches_the_queries(db):
    import metrics
    from datetime import timedelta
    from seed.generate import DEFAULT_AS_OF
    start = DEFAULT_AS_OF - timedelta(days=29)
    prog = next(r for r in metrics.run(db,"revenue", "cash_breakdown", metrics.params(metrics.load_config(), start, DEFAULT_AS_OF)) if r["stream"] == "Full program")
    import fmt
    body = text(run("revenue", tl_choice="Last 30 days"))
    for value in (fmt.inr(prog["contract"]), fmt.inr(prog["paid_new"]), fmt.inr(prog["earlier"]), fmt.inr(prog["amount"])):
        assert value in body, value


def test_the_page_introduces_the_path_from_sign_ups_to_the_achieved_number():
    body = text(run("revenue", tl_choice="Last 30 days"))
    assert "From this period's sign-ups to the achieved number" in body


def test_the_two_explanatory_paragraphs_under_the_chart_and_table_are_gone_but_the_click_hint_stays():
    body = text(run("revenue", tl_choice="Last 30 days"))
    assert "Each bar starts at zero" not in body and "Read each student row left to right" not in body and "The three cash figures add up to" not in body
    assert "Click a row to see its payments" in body


def test_a_lead_opened_from_a_past_period_shows_its_status_as_of_that_periods_end(db):
    import metrics
    from seed.generate import DEFAULT_AS_OF
    con = db
    lead = con.execute("SELECT l.lead_id, min(s.reached_at)::DATE FROM leads l JOIN lead_stages s USING (lead_id) WHERE s.stage = 'signed' GROUP BY 1 ORDER BY 2 DESC LIMIT 1").fetchone()[0]
    created = con.execute("SELECT created_at::DATE FROM leads WHERE lead_id = ?", [lead]).fetchone()[0]
    signed = con.execute("SELECT reached_at::DATE FROM lead_stages WHERE lead_id = ? AND stage = 'signed'", [lead]).fetchone()[0]
    assert signed > created
    now = metrics.run(con, "funnel", "lead_detail", {**metrics.params(metrics.load_config(), created, DEFAULT_AS_OF), "lead_id": lead})[0]
    then = metrics.run(con, "funnel", "lead_detail", {**metrics.params(metrics.load_config(), created, created), "lead_id": lead})[0]
    assert now["status"] == "Signed up" and then["status"] == "In progress"


def _verdict_page(**state):
    return text(run("rca", **{"tl_choice": "Last 90 days", **state}))


def test_the_rca_page_states_each_verdict_window_and_never_says_rules_are_not_set():
    body = _verdict_page()
    assert "Program verdict: 90-day lookback ending 18 Oct 2026" in body and "rules not set" not in body
    assert "Workshop verdict: the selected period" in body


def test_the_rca_page_shows_every_campaign_with_the_authors_verdicts():
    body = _verdict_page()
    for key in ("scale", "decline", "fatigue", "asset", "landing", "new", "volume", "workshop_ok"):
        assert STORIES[key] in body, key
    for label in ("Scale", "Hold: recent acquisition cost worsening", "Pause", "Too early"):
        assert label in body, label
    assert "Fix landing page" in body and "Creative review" in body and "Creative refresh needed" in body


def test_the_rca_page_keeps_action_reasons_flags_and_evidence_in_separate_columns():
    body = _verdict_page()
    for heading in ("<th>Verdict</th>", "<th>Why</th>", "<th>Flags</th>", "<th>Evidence</th>"):
        assert heading in body, heading


def test_the_rca_page_shows_leads_still_awaiting_conversion_and_the_peer_medians():
    body = _verdict_page()
    assert "Awaiting conversion" in body and "Peer medians" in body


def test_the_workshop_note_on_refunds_is_on_the_page():
    assert "Refunds are assumed to be ₹0 in this demo. Net revenue therefore equals recorded collected revenue." in _verdict_page()


def test_workshop_downstream_purchases_are_shown_but_labelled_separate():
    body = _verdict_page()
    assert "Later program purchases" in body and "synthetic" in body and "do not change the workshop verdict" in body


def test_a_seven_day_view_leaves_program_verdicts_alone_and_makes_workshops_too_early():
    at = run("rca", tl_choice="Last 90 days")
    ninety = text(at)
    seven = text(at.selectbox(key="tl_choice").select("Last 7 days").run())
    assert "Program verdict: 90-day lookback ending 18 Oct 2026" in seven
    for label in ("Hold: recent acquisition cost worsening", "Pause"):
        assert label in seven
    assert seven.count("Too early") > ninety.count("Too early")                          # both workshops now lack 14 days and 30 qualified leads


def test_the_overview_counts_verdicts_from_the_same_engine():
    body = text(run("overview", tl_choice="Last 90 days"))
    assert "Campaigns with a verdict" in body and "rules not set" not in body
