from datetime import date, timedelta

import pytest

import metrics
from seed.generate import DEFAULT_AS_OF, STORIES

ORDER = ["lead", "qualified", "discovery_set", "discovery_attended", "ambition_interview", "architect_session", "signed"]
START, END = date(2026, 10, 1), date(2026, 10, 10)


def run(con, cfg, name, start=START, end=END):
    return metrics.run(con, "funnel", name, metrics.params(cfg, start, end))


@pytest.fixture
def tiny(empty):
    """Five leads with hand-set timestamps (see the expected numbers in the tests) and Rs 1000 of spend in the period."""
    con = empty
    con.execute("INSERT INTO campaigns VALUES ('DEMO-C-1', 'c1', 'program'), ('DEMO-C-2', 'c2', 'program')")
    con.execute("INSERT INTO ad_sets VALUES ('DEMO-AS-1', 'DEMO-C-1', 's1'), ('DEMO-AS-2', 'DEMO-C-2', 's2')")
    con.execute("INSERT INTO ads VALUES ('DEMO-AD-1', 'DEMO-AS-1', 'a1'), ('DEMO-AD-2', 'DEMO-AS-2', 'a2')")
    con.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-1', '2026-10-05', 600, 1000, 20), ('DEMO-AD-2', '2026-10-05', 400, 1000, 20)")

    def lead(lead_id, source, camp, created, stages):
        ad = {"DEMO-C-1": ("DEMO-AS-1", "DEMO-AD-1"), "DEMO-C-2": ("DEMO-AS-2", "DEMO-AD-2")}.get(camp, (None, None))
        con.execute("INSERT INTO leads (lead_id, source_lead, campaign_id, ad_set_id, ad_id, created_at) VALUES (?, ?, ?, ?, ?, ?)", [lead_id, source, camp, ad[0], ad[1], created])
        for stage, at in zip(ORDER, stages):
            con.execute("INSERT INTO lead_stages VALUES (?, ?, ?)", [lead_id, stage, at])
    day = lambda d, h=8: f"2026-10-{d:02d} {h:02d}:00:00"
    lead("DEMO-L-1", "paid_ads", "DEMO-C-1", day(1), [day(1), day(1, 9), day(2), day(3), day(5), day(7), day(10)])      # signed on the last day, 9 days
    lead("DEMO-L-2", "paid_ads", "DEMO-C-1", day(2), [day(2), day(2, 9), day(4)])                                       # set a call, 2 days
    lead("DEMO-L-3", "paid_ads", "DEMO-C-2", day(3), [day(3)])                                                          # never qualified, 0 days
    lead("DEMO-L-4", "organic", None, day(3), [day(3), day(3, 20)])                                                 # organic, 0.5 days
    lead("DEMO-L-5", "paid_ads", "DEMO-C-1", day(2), [day(2), day(2, 10), day(3), day(4), day(9)])                      # reached the interview, 7 days
    return con


def test_stage_counts_are_non_increasing_and_complete(db, cfg):
    rows = run(db, cfg, "stage_counts", DEFAULT_AS_OF - timedelta(days=89), DEFAULT_AS_OF)
    assert [r["stage"] for r in rows] == ORDER
    counts = [r["leads"] for r in rows]
    assert counts == sorted(counts, reverse=True) and counts[0] > counts[-1] > 0


def test_show_up_and_drop_off_rates_by_hand(tiny, cfg):
    row = run(tiny, cfg, "show_up_and_drop")[0]
    assert (row["discovery_set"], row["discovery_attended"], row["ambition_interview"], row["architect_session"]) == (3, 2, 2, 1)
    assert row["discovery_show_up_rate"] == pytest.approx(2 / 3)
    assert row["ambition_drop_off_rate"] == pytest.approx(0.5)


def test_headline_by_hand(tiny, cfg):
    row = run(tiny, cfg, "headline")[0]
    assert row["cost_per_qualified_lead"] == pytest.approx(1000 / 3)        # Rs 1000 over L1, L2, L5 (paid, qualified); the organic one is excluded
    assert row["program_conversion_rate"] == pytest.approx(1 / 5)           # 1 sign-up in the period over 5 leads created in it
    assert row["organic_leads"] == 1
    assert row["avg_journey_days"] == pytest.approx((9 + 2 + 0 + 0.5 + 7) / 5)


def test_by_campaign_null_cost_when_nobody_qualified(tiny, cfg):
    rows = {r["campaign_id"]: r for r in run(tiny, cfg, "by_campaign")}
    assert rows["DEMO-C-1"]["qualified"] == 3 and rows["DEMO-C-1"]["spend"] == 600 and rows["DEMO-C-1"]["cost_per_qualified_lead"] == pytest.approx(200)
    assert rows["DEMO-C-2"]["leads"] == 1 and rows["DEMO-C-2"]["qualified"] == 0 and rows["DEMO-C-2"]["cost_per_qualified_lead"] is None


def test_period_boundary_is_inclusive_on_the_last_day(tiny, cfg):
    tiny.execute("INSERT INTO leads (lead_id, source_lead, created_at) VALUES ('DEMO-L-6', 'organic', '2026-10-10 23:59:00')")
    tiny.execute("INSERT INTO lead_stages VALUES ('DEMO-L-6', 'lead', '2026-10-10 23:59:00')")
    tiny.execute("INSERT INTO leads (lead_id, source_lead, created_at) VALUES ('DEMO-L-7', 'organic', '2026-10-11 00:00:00')")
    tiny.execute("INSERT INTO lead_stages VALUES ('DEMO-L-7', 'lead', '2026-10-11 00:00:00')")
    assert run(tiny, cfg, "headline")[0]["organic_leads"] == 2       # L4 and L6, not L7


def test_empty_period_gives_nulls_not_errors(db, cfg):
    start, end = date(2020, 1, 1), date(2020, 1, 7)
    row = run(db, cfg, "headline", start, end)[0]
    assert row["cost_per_qualified_lead"] is None and row["program_conversion_rate"] is None and row["organic_leads"] == 0
    assert all(r["leads"] == 0 for r in run(db, cfg, "stage_counts", start, end))
    assert run(db, cfg, "show_up_and_drop", start, end)[0]["discovery_show_up_rate"] is None


def test_story_campaigns_all_present_in_by_campaign(db, cfg):
    ids = {r["campaign_id"] for r in run(db, cfg, "by_campaign", DEFAULT_AS_OF - timedelta(days=89), DEFAULT_AS_OF)}
    assert {STORIES[k] for k in ("scale", "fatigue", "asset", "landing", "volume", "workshop_ok")} <= ids


def test_a_brochure_lead_is_not_organic_and_not_paid(tiny, cfg):
    before = run(tiny, cfg, "headline")[0]
    tiny.execute("INSERT INTO leads (lead_id, source_lead, created_at) VALUES ('DEMO-L-8', 'brochure', '2026-10-04 09:00:00')")
    tiny.execute("INSERT INTO lead_stages VALUES ('DEMO-L-8', 'lead', '2026-10-04 09:00:00'), ('DEMO-L-8', 'qualified', '2026-10-04 10:00:00')")
    after = run(tiny, cfg, "headline")[0]
    assert after["organic_leads"] == before["organic_leads"] == 1                 # a brochure lead does not count as organic
    assert after["cost_per_qualified_lead"] == before["cost_per_qualified_lead"]   # nor as a paid qualified lead: spend is divided by paid leads only
    assert sum(r["leads"] for r in run(tiny, cfg, "stage_counts") if r["stage"] == "lead") == 6    # but it is a lead


def test_exits_count_rejected_and_nurture_for_the_cohort(tiny, cfg):
    tiny.execute("INSERT INTO lead_stages VALUES ('DEMO-L-3', 'review', '2026-10-03 09:00:00'), ('DEMO-L-3', 'rejected', '2026-10-03 10:00:00')")
    tiny.execute("INSERT INTO lead_stages VALUES ('DEMO-L-2', 'nurture', '2026-10-05 10:00:00')")
    row = run(tiny, cfg, "exits")[0]
    assert row["rejected"] == 1 and row["nurture"] == 1
    empty_period = run(tiny, cfg, "exits", date(2020, 1, 1), date(2020, 1, 7))[0]
    assert empty_period["rejected"] == 0 and empty_period["nurture"] == 0


def test_stage_counts_still_list_the_briefs_seven_stages_only(db, cfg):
    assert [r["stage"] for r in run(db, cfg, "stage_counts", DEFAULT_AS_OF - timedelta(days=89), DEFAULT_AS_OF)] == ORDER


@pytest.fixture
def attributed(tiny):
    """The five-lead fixture with ClickUp attributes: L1 Delhi/10, L2 Delhi/11, L3 Mumbai/10, L4 (organic) no city or grade, L5 Delhi/10."""
    for lead_id, city, grade, traffic in [("DEMO-L-1", "Delhi", 10, "instagram"), ("DEMO-L-2", "Delhi", 11, "facebook"), ("DEMO-L-3", "Mumbai", 10, "facebook"),
                                          ("DEMO-L-4", None, None, "google"), ("DEMO-L-5", "Delhi", 10, "instagram")]:
        tiny.execute("UPDATE leads SET city = ?, grade = ?, traffic_source = ?, school = ?, parent_name = ?, student_name = ?, phone = ? WHERE lead_id = ?",
                     [city, grade, traffic, f"Demo School {lead_id[-1]}", f"Demo Parent {lead_id[-1]}", f"Demo Student {lead_id[-1]}", f"+91 00000 0000{lead_id[-1]}", lead_id])
    return tiny


def breakdown(con, cfg, dimension, **period):
    return {r["value"]: r for r in run(con, cfg, "by_dimension", **period) if r["dimension"] == dimension}


def test_by_dimension_by_hand(attributed, cfg):
    city = breakdown(attributed, cfg, "city")
    assert (city["Delhi"]["leads"], city["Delhi"]["qualified"], city["Delhi"]["signed"]) == (3, 3, 1)
    assert city["Delhi"]["signed_rate"] == pytest.approx(1 / 3) and city["Delhi"]["qualified_rate"] == pytest.approx(1.0)
    assert (city["Mumbai"]["leads"], city["Mumbai"]["qualified"]) == (1, 0) and city["Mumbai"]["qualified_rate"] == 0
    assert (city["Unknown"]["leads"], city["Unknown"]["qualified"]) == (1, 1)               # a missing value is its own group, never dropped
    grade = breakdown(attributed, cfg, "grade")
    assert {k: v["leads"] for k, v in grade.items()} == {"10": 3, "11": 1, "Unknown": 1}
    assert breakdown(attributed, cfg, "source_lead")["paid_ads"]["leads"] == 4 and breakdown(attributed, cfg, "source_lead")["organic"]["leads"] == 1


def test_every_dimension_accounts_for_every_lead_in_the_period(db, cfg):
    start, end = DEFAULT_AS_OF - timedelta(days=89), DEFAULT_AS_OF
    total = run(db, cfg, "headline", start, end) and sum(r["leads"] for r in run(db, cfg, "stage_counts", start, end) if r["stage"] == "lead")
    rows = run(db, cfg, "by_dimension", start, end)
    assert {r["dimension"] for r in rows} == {"city", "grade", "school", "traffic_source", "source_lead", "utm_source"}
    for dimension in {r["dimension"] for r in rows}:
        assert sum(r["leads"] for r in rows if r["dimension"] == dimension) == total, dimension


def test_by_dimension_empty_period_is_empty(db, cfg):
    assert run(db, cfg, "by_dimension", date(2020, 1, 1), date(2020, 1, 7)) == []


def test_lead_list_by_hand(attributed, cfg):
    attributed.execute("INSERT INTO lead_stages VALUES ('DEMO-L-3', 'review', '2026-10-03 09:00:00'), ('DEMO-L-3', 'rejected', '2026-10-03 10:00:00')")
    attributed.execute("INSERT INTO lead_stages VALUES ('DEMO-L-2', 'nurture', '2026-10-05 10:00:00')")
    rows = {r["lead_id"]: r for r in run(attributed, cfg, "lead_list")}
    assert len(rows) == 5
    assert (rows["DEMO-L-1"]["furthest_stage"], rows["DEMO-L-1"]["status"]) == ("signed", "Signed up")
    assert (rows["DEMO-L-5"]["furthest_stage"], rows["DEMO-L-5"]["status"]) == ("ambition_interview", "In progress")
    assert (rows["DEMO-L-3"]["furthest_stage"], rows["DEMO-L-3"]["status"]) == ("review", "Rejected")
    assert (rows["DEMO-L-2"]["furthest_stage"], rows["DEMO-L-2"]["status"]) == ("discovery_set", "Nurture")      # the exit does not move the furthest stage
    assert rows["DEMO-L-1"]["parent_name"] == "Demo Parent 1" and rows["DEMO-L-1"]["phone"] == "+91 00000 00001" and rows["DEMO-L-1"]["city"] == "Delhi"
    assert [r["lead_id"] for r in run(attributed, cfg, "lead_list")][:2] == ["DEMO-L-4", "DEMO-L-3"]             # newest first, ties by id descending


def test_lead_list_only_has_leads_created_in_the_period(attributed, cfg):
    assert [r["lead_id"] for r in run(attributed, cfg, "lead_list", date(2026, 10, 3), date(2026, 10, 3))] == ["DEMO-L-4", "DEMO-L-3"]
    assert run(attributed, cfg, "lead_list", date(2020, 1, 1), date(2020, 1, 7)) == []


def one_lead(con, cfg, name, lead_id):
    prm = {**metrics.params(cfg, date(2026, 10, 1), date(2026, 10, 10)), "lead_id": lead_id}
    return metrics.run(con, "funnel", name, prm)


def test_lead_detail_by_hand(attributed, cfg):
    row = one_lead(attributed, cfg, "lead_detail", "DEMO-L-1")[0]
    assert (row["student_name"], row["parent_name"], row["city"], row["grade"], row["traffic_source"]) == ("Demo Student 1", "Demo Parent 1", "Delhi", 10, "instagram")
    assert (row["campaign_name"], row["ad_set_name"], row["asset_name"]) == ("c1", "s1", "a1")
    assert (row["furthest_stage"], row["status"]) == ("signed", "Signed up")
    organic = one_lead(attributed, cfg, "lead_detail", "DEMO-L-4")[0]
    assert organic["campaign_name"] is None and organic["asset_name"] is None and organic["status"] == "In progress"
    assert one_lead(attributed, cfg, "lead_detail", "DEMO-L-NOPE") == []


def test_lead_timeline_is_in_order_with_the_gap_since_the_previous_stage(attributed, cfg):
    rows = one_lead(attributed, cfg, "lead_timeline", "DEMO-L-1")
    assert [r["stage"] for r in rows] == ["lead", "qualified", "discovery_set", "discovery_attended", "ambition_interview", "architect_session", "signed"]
    assert rows[0]["days_since_previous"] is None
    assert rows[1]["days_since_previous"] == pytest.approx(1 / 24)                 # 08:00 to 09:00 on the same day
    assert rows[2]["days_since_previous"] == pytest.approx(23 / 24)                # 09:00 on the 1st to 08:00 on the 2nd
    assert one_lead(attributed, cfg, "lead_timeline", "DEMO-L-NOPE") == []


def test_lead_money_lists_enrollment_invoices_and_workshop_seats(attributed, cfg):
    attributed.execute("INSERT INTO enrollments VALUES ('DEMO-EN-1', 'DEMO-ST-1', 'DEMO-L-1', 'program', '2026-10-10', NULL, 500000)")
    attributed.execute("INSERT INTO invoices VALUES ('DEMO-INV-1', 'DEMO-EN-1', '2026-10-10', '2026-10-17', 250000, '2026-10-12'), ('DEMO-INV-2', 'DEMO-EN-1', '2026-12-09', '2026-12-16', 250000, NULL)")
    attributed.execute("INSERT INTO workshops VALUES ('DEMO-WS-1', 'DEMO-C-1', 'w', '2026-10-05')")
    attributed.execute("INSERT INTO workshop_payments VALUES ('DEMO-PAY-1', 'DEMO-WS-1', 'DEMO-L-1', '2026-10-04 10:00:00', 2, 7998)")
    rows = one_lead(attributed, cfg, "lead_money", "DEMO-L-1")      # as known on 10 Oct: the 12 Oct payment and the December invoice do not exist yet
    assert [(r["item"], r["amount"], r["state"]) for r in rows] == [
        ("Workshop seats (2)", 7998, "Paid"), ("Program enrollment", 500000, "Started"), ("Invoice", 250000, "Unpaid, due 17 Oct 2026")]
    later = metrics.run(attributed, "funnel", "lead_money", {**metrics.params(cfg, date(2026, 10, 1), date(2026, 12, 31)), "lead_id": "DEMO-L-1"})
    assert [(r["item"], r["state"]) for r in later] == [("Workshop seats (2)", "Paid"), ("Program enrollment", "Started"), ("Invoice", "Paid on 12 Oct 2026"), ("Invoice", "Unpaid, due 16 Dec 2026")]
    assert one_lead(attributed, cfg, "lead_money", "DEMO-L-2") == []


def test_a_signed_lead_in_the_seed_has_an_enrollment_and_invoices(db, cfg):
    lead = db.execute("SELECT lead_id FROM enrollments WHERE lead_id IS NOT NULL ORDER BY lead_id LIMIT 1").fetchone()[0]
    prm = {**metrics.params(cfg, DEFAULT_AS_OF, DEFAULT_AS_OF), "lead_id": lead}
    items = [r["item"] for r in metrics.run(db, "funnel", "lead_money", prm)]
    assert any(i.endswith("enrollment") for i in items) and "Invoice" in items
