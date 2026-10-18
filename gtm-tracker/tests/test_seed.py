"""The dummy data plants six known stories so the metrics and the RCA can be checked against truth."""
from datetime import timedelta

import duckdb

from seed.generate import DEFAULT_AS_OF, STORIES, WINDOW_DAYS, build

PATH = ["lead", "review", "qualified", "conveyed", "discovery_set", "discovery_attended", "ambition_interview", "architect_session", "signed"]   # ClickUp order
EXIT_AFTER = {"rejected": "review", "nurture": "discovery_attended"}      # an exit stage can only follow this stage, and nothing follows it


def test_deterministic_and_seed_sensitive(tmp_path):
    def rows(seed):
        path = str(tmp_path / f"s{seed}.duckdb")
        build(path, seed=seed)
        con = duckdb.connect(path, read_only=True)
        out = (con.execute("SELECT * FROM leads ORDER BY lead_id").fetchall(), con.execute("SELECT * FROM ad_daily ORDER BY ad_id, day").fetchall())
        con.close()
        return out
    assert rows(7) == rows(7)
    assert rows(7) != rows(8)


def test_all_ids_are_demo_prefixed(db):
    for table, col in [("enrollments", "enrollment_id"), ("enrollments", "student_id"), ("invoices", "invoice_id"), ("workshops", "workshop_id"),
                       ("workshop_payments", "payment_id"), ("campaigns", "campaign_id"), ("ad_sets", "ad_set_id"), ("ads", "ad_id"), ("leads", "lead_id")]:
        assert db.execute(f"SELECT count(*) FROM {table} WHERE {col} NOT LIKE 'DEMO-%'").fetchone()[0] == 0, (table, col)
    assert db.execute("SELECT demo, as_of FROM snapshot_meta").fetchone() == (True, DEFAULT_AS_OF)


def test_stage_order_is_a_monotonic_prefix_of_the_clickup_path_plus_at_most_one_exit(db):
    rank = {s: i for i, s in enumerate(PATH)}
    by_lead = {}
    for lead, stage, at in db.execute("SELECT lead_id, stage, reached_at FROM lead_stages ORDER BY lead_id, reached_at, stage").fetchall():
        by_lead.setdefault(lead, []).append((stage, at))
    assert len(by_lead) == db.execute("SELECT count(*) FROM leads").fetchone()[0]   # every lead has at least the 'lead' stage
    for lead, items in by_lead.items():
        names = [s for s, _ in items]
        exit_stage = names[-1] if names[-1] in EXIT_AFTER else None
        path = names[:-1] if exit_stage else names
        assert [rank[s] for s in path] == list(range(len(path))), lead                # a prefix of the path
        if exit_stage:
            assert path[-1] == EXIT_AFTER[exit_stage], (lead, names)                  # rejected only after review, nurture only after the discovery call
        assert sum(n in EXIT_AFTER for n in names) <= 1
        times = [t for _, t in items]
        assert times == sorted(times), lead


def test_story_fatigue(db):
    ad_set = STORIES["fatigue_ad_set"]
    assert db.execute("SELECT frequency FROM ad_set_daily WHERE ad_set_id = ? AND day = ?", [ad_set, DEFAULT_AS_OF]).fetchone()[0] >= 3

    def ctr(first, last):
        return db.execute("SELECT sum(clicks) * 1.0 / sum(impressions) FROM ad_daily d JOIN ads a USING (ad_id) WHERE a.ad_set_id = ? AND day BETWEEN ? AND ?",
                          [ad_set, first, last]).fetchone()[0]
    start = DEFAULT_AS_OF - timedelta(days=WINDOW_DAYS - 1)
    assert ctr(DEFAULT_AS_OF - timedelta(days=13), DEFAULT_AS_OF) < 0.7 * ctr(start, start + timedelta(days=13))


def test_story_weak_asset(db):
    rows = dict(db.execute("""SELECT ad_id, sum(clicks) * 1.0 / sum(impressions) FROM ad_daily JOIN ads USING (ad_id) JOIN ad_sets USING (ad_set_id)
                              WHERE campaign_id = ? GROUP BY ad_id""", [STORIES["asset"]]).fetchall())
    weak = rows.pop(STORIES["weak_asset"])
    others = sorted(rows.values())
    assert weak < 0.5 * others[len(others) // 2]


def _since_90(con, as_of=DEFAULT_AS_OF):
    return as_of - timedelta(days=89)


def test_story_scale_candidate(db):
    start = _since_90(db)
    rows = db.execute("""
        SELECT c.campaign_id,
               (SELECT sum(spend) FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id) WHERE s.campaign_id = c.campaign_id AND d.day >= ?) AS spend,
               count(*) FILTER (WHERE st.stage = 'qualified') AS qualified,
               count(*) FILTER (WHERE st.stage = 'signed') * 1.0 / count(DISTINCT l.lead_id) AS signed_rate
        FROM campaigns c JOIN leads l USING (campaign_id) JOIN lead_stages st USING (lead_id)
        WHERE c.kind = 'program' AND l.created_at >= ? GROUP BY c.campaign_id""", [start, start]).fetchall()
    cpql = {r[0]: r[1] / r[2] for r in rows}
    rate = {r[0]: r[3] for r in rows}
    assert min(cpql, key=cpql.get) == STORIES["scale"]
    assert max(rate, key=rate.get) == STORIES["scale"]


def test_story_volume_without_outcome(db):
    rows = db.execute("""SELECT l.campaign_id, count(DISTINCT l.lead_id), count(*) FILTER (WHERE st.stage = 'signed') * 1.0 / count(DISTINCT l.lead_id)
                         FROM leads l JOIN lead_stages st USING (lead_id) WHERE l.campaign_id IS NOT NULL GROUP BY l.campaign_id""").fetchall()
    leads = {r[0]: r[1] for r in rows}
    rate = {r[0]: r[2] for r in rows}
    assert max(leads, key=leads.get) == STORIES["volume"]
    assert rate[STORIES["volume"]] < 0.02


def test_story_landing_page(db):
    rows = {r[0]: r[1:] for r in db.execute("SELECT campaign_id, sum(bounces) * 1.0 / sum(sessions), avg(avg_load_seconds) FROM landing_page_daily GROUP BY 1").fetchall()}
    bounce, load = rows[STORIES["landing"]]
    assert bounce > 0.6 and load > 4
    for campaign, (b, l) in rows.items():
        if campaign != STORIES["landing"]:
            assert b < 0.4 and l < 3, campaign


def test_story_money(db):
    unpaid = db.execute("SELECT count(*), count(*) FILTER (WHERE due_on < ?) FROM invoices WHERE paid_on IS NULL", [DEFAULT_AS_OF]).fetchone()
    assert unpaid[0] >= 5 and unpaid[1] >= 2
    renewals = db.execute("SELECT count(*) FROM enrollments WHERE kind = 'trial_3m' AND renewal_on BETWEEN ? AND ?",
                          [DEFAULT_AS_OF, DEFAULT_AS_OF + timedelta(days=30)]).fetchone()[0]
    assert renewals >= 3
    assert db.execute("SELECT count(*) FROM workshop_payments WHERE amount <> seats * 3999").fetchone()[0] == 0
    days = [r[0] for r in db.execute("SELECT held_on FROM workshops ORDER BY held_on").fetchall()]
    assert len(days) >= 10 and all((b - a).days == 14 for a, b in zip(days, days[1:]))


def test_history_covers_at_least_nine_months_with_data_in_every_month(db):
    assert WINDOW_DAYS >= 270
    months = db.execute("SELECT count(DISTINCT date_trunc('month', day)) FROM ad_daily").fetchone()[0]
    assert months >= 9
    enrolled = db.execute("SELECT count(DISTINCT date_trunc('month', started_on)) FROM enrollments").fetchone()[0]
    assert enrolled >= 9


def _cpql(db, campaign, first, last):
    spend = db.execute("""SELECT sum(spend) FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
                          WHERE s.campaign_id = ? AND day BETWEEN ? AND ?""", [campaign, first, last]).fetchone()[0]
    qualified = db.execute("""SELECT count(*) FROM leads l JOIN lead_stages st USING (lead_id) WHERE l.campaign_id = ? AND st.stage = 'qualified'
                              AND l.created_at::DATE BETWEEN ? AND ?""", [campaign, first, last]).fetchone()[0]
    return spend / qualified


def test_story_decline_cost_per_qualified_lead_more_than_doubles_over_the_year(db):
    first = DEFAULT_AS_OF - timedelta(days=WINDOW_DAYS - 1)
    early = _cpql(db, STORIES["decline"], first, first + timedelta(days=89))
    late = _cpql(db, STORIES["decline"], DEFAULT_AS_OF - timedelta(days=89), DEFAULT_AS_OF)
    assert late > 2 * early


def test_story_new_campaign_launched_inside_the_last_30_days_with_a_strong_ctr(db):
    first_day = db.execute("""SELECT min(day) FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id) WHERE s.campaign_id = ?""", [STORIES["new"]]).fetchone()[0]
    assert first_day == DEFAULT_AS_OF - timedelta(days=24)
    assert db.execute("SELECT count(*) FROM landing_page_daily WHERE campaign_id = ? AND day < ?", [STORIES["new"], first_day]).fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM leads WHERE campaign_id = ? AND created_at::DATE < ?", [STORIES["new"], first_day]).fetchone()[0] == 0
    def ctr(campaign):
        return db.execute("""SELECT sum(clicks) * 1.0 / sum(impressions) FROM ad_daily d JOIN ads a USING (ad_id) JOIN ad_sets s USING (ad_set_id)
                             WHERE s.campaign_id = ? AND day >= ?""", [campaign, DEFAULT_AS_OF - timedelta(days=24)]).fetchone()[0]
    assert ctr(STORIES["new"]) > ctr(STORIES["scale"])


def test_leads_grow_over_the_year(db):
    first = DEFAULT_AS_OF - timedelta(days=WINDOW_DAYS - 1)
    n = lambda a, b: db.execute("SELECT count(*) FROM leads WHERE created_at::DATE BETWEEN ? AND ?", [a, b]).fetchone()[0]
    assert n(DEFAULT_AS_OF - timedelta(days=89), DEFAULT_AS_OF) > 1.2 * n(first, first + timedelta(days=89))


def test_both_exits_exist_and_rejected_leads_never_reach_qualified(db):
    assert db.execute("SELECT count(*) FROM lead_stages WHERE stage = 'rejected'").fetchone()[0] > 50
    assert db.execute("SELECT count(*) FROM lead_stages WHERE stage = 'nurture'").fetchone()[0] > 20
    assert db.execute("SELECT count(*) FROM lead_stages a JOIN lead_stages b USING (lead_id) WHERE a.stage = 'rejected' AND b.stage = 'qualified'").fetchone()[0] == 0


def test_lead_attributes_follow_the_clickup_fields_and_are_clearly_fake(db):
    assert db.execute("SELECT count(*) FROM leads WHERE parent_name NOT LIKE 'Demo Parent %' OR student_name NOT LIKE 'Demo Student %' OR phone NOT LIKE '+91 00000 %' OR school NOT LIKE 'Demo School %'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM leads WHERE grade NOT BETWEEN 8 AND 12 OR city IS NULL OR traffic_source NOT IN ('instagram', 'facebook', 'google', 'direct')").fetchone()[0] == 0
    assert {r[0] for r in db.execute("SELECT DISTINCT source_lead FROM leads").fetchall()} == {"paid_ads", "brochure", "organic"}


def test_source_lead_rules(db):
    assert db.execute("SELECT count(*) FROM leads WHERE source_lead = 'paid_ads' AND (campaign_id IS NULL OR utm_source NOT IN ('instagram', 'meta'))").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM leads WHERE source_lead <> 'paid_ads' AND (campaign_id IS NOT NULL OR utm_source IS NOT NULL)").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM leads WHERE source_lead = 'brochure' AND traffic_source <> 'direct'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM leads WHERE source_lead = 'brochure'").fetchone()[0] > 30


def test_contract_values_follow_the_founders_office_email(db):
    assert {r[0]: r[1] for r in db.execute("SELECT kind, any_value(amount) FROM enrollments GROUP BY kind").fetchall()} == {"program": 500000, "trial_3m": 175000}
    assert db.execute("SELECT count(DISTINCT amount) FROM enrollments").fetchone()[0] == 2


def test_monthly_targets_are_realistic_so_the_dashboard_shows_ahead_and_behind_months(db):
    rows = db.execute("""
        SELECT t.month, t.target, coalesce((SELECT sum(amount) FROM invoices WHERE date_trunc('month', paid_on) = t.month), 0)
                                + coalesce((SELECT sum(amount) FROM workshop_payments WHERE date_trunc('month', paid_at) = t.month), 0) AS actual
        FROM revenue_targets t WHERE t.month < date_trunc('month', ?::DATE) AND t.month >= date_trunc('month', ?::DATE) ORDER BY t.month""",
        [DEFAULT_AS_OF, DEFAULT_AS_OF - timedelta(days=200)]).fetchall()
    ratios = [actual / target for _, target, actual in rows]
    assert len(ratios) >= 6 and all(0.6 <= r <= 1.5 for r in ratios), ratios
    assert any(r < 1 for r in ratios) and any(r > 1 for r in ratios)


def test_every_enrollment_is_invoiced_once_for_its_full_contract_value(db):
    bad = db.execute("""SELECT count(*) FROM (SELECT e.enrollment_id FROM enrollments e JOIN invoices i USING (enrollment_id)
                        GROUP BY e.enrollment_id, e.amount HAVING count(*) <> 1 OR sum(i.amount) <> e.amount)""").fetchone()[0]
    assert bad == 0
    assert db.execute("SELECT count(*) FROM enrollments e WHERE NOT EXISTS (SELECT 1 FROM invoices i WHERE i.enrollment_id = e.enrollment_id)").fetchone()[0] == 0


def test_students_pay_within_three_days_of_their_invoice_and_few_never_pay(db):
    assert db.execute("SELECT count(*) FROM invoices WHERE paid_on IS NOT NULL AND paid_on - issued_on > 3").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM invoices WHERE paid_on IS NOT NULL AND paid_on < issued_on").fetchone()[0] == 0
    unpaid, total = db.execute("SELECT count(*) FILTER (WHERE paid_on IS NULL), count(*) FROM invoices WHERE issued_on <= ?", [DEFAULT_AS_OF - timedelta(days=10)]).fetchone()
    assert 0 < unpaid / total <= 0.12


def test_synthetic_workshop_buyers_who_later_bought_the_program(db):
    rows = db.execute("""SELECT w.campaign_id, e.enrollment_id, p.lead_id, p.paid_at::DATE, e.started_on, e.kind, e.amount, e.lead_id
                         FROM enrollments e JOIN workshop_payments p ON p.lead_id = e.lead_id JOIN workshops w ON w.workshop_id = p.workshop_id
                         WHERE e.enrollment_id LIKE 'DEMO-EN-WS-%' ORDER BY e.enrollment_id""").fetchall()
    per = {}
    for campaign, eid, lead, paid, started, kind, amount, _ in rows:
        per[campaign] = per.get(campaign, 0) + 1
        assert 0 < (started - paid).days <= 60, eid                  # after the workshop purchase and within 60 days
        assert kind == "program" and amount == 500000
    assert per == {STORIES["workshop_ok"]: 3, STORIES["volume"]: 1}
    assert db.execute("SELECT count(*) FROM enrollments WHERE enrollment_id LIKE 'DEMO-EN-WS-%'").fetchone()[0] == 4          # none is linked to a lead that is not a workshop buyer
    assert db.execute("""SELECT count(*) FROM (SELECT lead_id FROM enrollments WHERE lead_id IS NOT NULL GROUP BY lead_id HAVING count(*) > 1)""").fetchone()[0] == 0    # a buyer is never enrolled twice


def test_synthetic_purchases_follow_the_one_invoice_rule_and_have_complete_follow_up(db):
    ids = [r[0] for r in db.execute("SELECT enrollment_id FROM enrollments WHERE enrollment_id LIKE 'DEMO-EN-WS-%'").fetchall()]
    for eid in ids:
        assert db.execute("SELECT count(*), sum(amount) FROM invoices WHERE enrollment_id = ?", [eid]).fetchone() == (1, 500000)          # each payment counted once
    latest_started = db.execute("SELECT max(started_on) FROM enrollments WHERE enrollment_id LIKE 'DEMO-EN-WS-%'").fetchone()[0]
    assert latest_started <= DEFAULT_AS_OF - timedelta(days=1)


def test_the_planted_stories_survive_the_synthetic_purchases(db):
    """The new rows use their own random stream, so the earlier dummy data is unchanged: a few spot checks of numbers other tests rely on."""
    assert db.execute("SELECT count(*) FROM leads").fetchone()[0] == 4234
    assert db.execute("SELECT count(*) FROM enrollments WHERE enrollment_id NOT LIKE 'DEMO-EN-WS-%'").fetchone()[0] == 263


def test_the_synthetic_buyers_sit_inside_the_default_90_day_view_with_a_complete_60_day_follow_up(db):
    rows = db.execute("""SELECT w.campaign_id, p.paid_at::DATE FROM enrollments e JOIN workshop_payments p ON p.lead_id = e.lead_id JOIN workshops w ON w.workshop_id = p.workshop_id
                         WHERE e.enrollment_id LIKE 'DEMO-EN-WS-%'""").fetchall()
    assert len(rows) == 4
    for campaign, paid_on in rows:
        assert DEFAULT_AS_OF - timedelta(days=89) <= paid_on <= DEFAULT_AS_OF - timedelta(days=60), (campaign, paid_on)
