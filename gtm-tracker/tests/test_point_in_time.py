"""A snapshot as of a past end date must not change when something happens later: a lead reaching a later stage, a payment arriving, a workshop seat bought.
Each case runs a query for a period ending 10 Oct, then adds rows dated after 10 Oct, and expects the answer to be identical."""
from datetime import date

import pytest

import metrics

START, END = date(2026, 10, 1), date(2026, 10, 10)
QUERIES = [("funnel", n) for n in ("stage_counts", "show_up_and_drop", "exits", "headline", "by_campaign", "by_dimension", "lead_list")] + \
          [("revenue", n) for n in ("target_vs_actual", "signup_split", "workshop_revenue", "program_vs_workshop", "unpaid_invoices", "cash_breakdown", "onboarded_monthly")]


@pytest.fixture
def world(empty):
    con = empty
    con.execute("INSERT INTO campaigns VALUES ('DEMO-C-1', 'c1', 'program'), ('DEMO-C-2', 'c2', 'workshop')")
    con.execute("INSERT INTO ad_sets VALUES ('DEMO-AS-1', 'DEMO-C-1', 's1'), ('DEMO-AS-2', 'DEMO-C-2', 's2')")
    con.execute("INSERT INTO ads VALUES ('DEMO-AD-1', 'DEMO-AS-1', 'a1'), ('DEMO-AD-2', 'DEMO-AS-2', 'a2')")
    con.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-1', '2026-10-05', 600, 1000, 20), ('DEMO-AD-2', '2026-10-05', 400, 1000, 20)")
    day = lambda d, h=8: f"2026-10-{d:02d} {h:02d}:00:00"
    for lead_id, camp, created, stages in [
        ("DEMO-L-1", "DEMO-C-1", day(1), ["lead", "review", "qualified", "conveyed", "discovery_set", "discovery_attended", "ambition_interview"]),
        ("DEMO-L-2", "DEMO-C-1", day(2), ["lead", "review", "qualified"]),
        ("DEMO-L-3", "DEMO-C-1", day(3), ["lead", "review"]),
        ("DEMO-L-4", "DEMO-C-2", day(3), ["lead", "review", "qualified"]),
        ("DEMO-L-5", "DEMO-C-1", day(4), ["lead", "review", "qualified", "conveyed", "discovery_set", "discovery_attended"]),
    ]:
        con.execute("INSERT INTO leads (lead_id, source_lead, campaign_id, created_at, city, grade) VALUES (?, 'paid_ads', ?, ?, 'Delhi', 10)", [lead_id, camp, created])
        for i, st in enumerate(stages):
            base = int(created[8:10])
            con.execute("INSERT INTO lead_stages VALUES (?, ?, ?)", [lead_id, st, f"2026-10-{base + (0 if i == 0 else 1):02d} {8 + i:02d}:00:00"])
    con.execute("INSERT INTO enrollments VALUES ('DEMO-EN-1', 'DEMO-ST-1', 'DEMO-L-1', 'program', '2026-10-08', NULL, 500000)")
    con.execute("INSERT INTO invoices VALUES ('DEMO-INV-1', 'DEMO-EN-1', '2026-10-08', '2026-10-15', 500000, '2026-10-09')")
    con.execute("INSERT INTO invoices VALUES ('DEMO-INV-3', 'DEMO-EN-1', '2026-10-09', '2026-10-16', 100000, NULL)")        # issued before the end, still unpaid on it
    con.execute("INSERT INTO workshops VALUES ('DEMO-WS-1', 'DEMO-C-2', 'w', '2026-10-05')")
    con.execute("INSERT INTO workshop_payments VALUES ('DEMO-PAY-1', 'DEMO-WS-1', 'DEMO-L-4', '2026-10-04 10:00:00', 1, 3999)")
    con.execute("INSERT INTO revenue_targets VALUES ('2026-10-01', 900000)")
    return con


def future(con):
    """Everything that happens after 10 Oct and must not leak into a snapshot taken on 10 Oct."""
    con.execute("INSERT INTO lead_stages VALUES ('DEMO-L-3', 'qualified', '2026-10-20 09:00:00'), ('DEMO-L-3', 'conveyed', '2026-10-21 09:00:00')")      # a later stage change
    con.execute("INSERT INTO lead_stages VALUES ('DEMO-L-2', 'nurture', '2026-10-15 10:00:00')")                                                          # a later exit
    con.execute("INSERT INTO lead_stages VALUES ('DEMO-L-5', 'ambition_interview', '2026-10-16 10:00:00'), ('DEMO-L-5', 'architect_session', '2026-10-18 10:00:00'), ('DEMO-L-5', 'signed', '2026-10-25 10:00:00')")
    con.execute("INSERT INTO enrollments VALUES ('DEMO-EN-2', 'DEMO-ST-2', 'DEMO-L-5', 'trial_3m', '2026-10-25', '2027-01-23', 175000)")
    con.execute("INSERT INTO invoices VALUES ('DEMO-INV-2', 'DEMO-EN-2', '2026-10-25', '2026-11-01', 175000, '2026-10-26')")                            # a later enrollment and payment
    con.execute("UPDATE invoices SET paid_on = '2026-10-17' WHERE invoice_id = 'DEMO-INV-3'")                                                            # a payment that arrives after the end date
    con.execute("INSERT INTO workshop_payments VALUES ('DEMO-PAY-2', 'DEMO-WS-1', 'DEMO-L-4', '2026-10-15 10:00:00', 2, 7998)")                         # a seat bought after the workshop's window
    con.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-1', '2026-10-20', 900, 1000, 30)")


@pytest.mark.parametrize("file,name", QUERIES)
def test_a_snapshot_never_uses_what_happens_after_its_end_date(world, cfg, file, name):
    prm = metrics.params(cfg, START, END)
    before = metrics.run(world, file, name, prm)
    future(world)
    assert metrics.run(world, file, name, prm) == before, f"{file}.{name} used information dated after {END}"


def test_the_same_future_rows_do_change_a_snapshot_taken_later(world, cfg):
    """Guards the test above: the future rows are real, so a later snapshot sees them."""
    prm_later = metrics.params(cfg, START, date(2026, 10, 31))
    before = metrics.run(world, "funnel", "headline", prm_later)[0]
    future(world)
    after = metrics.run(world, "funnel", "headline", prm_later)[0]
    assert after["program_conversion_rate"] != before["program_conversion_rate"]
    assert metrics.run(world, "revenue", "cash_breakdown", prm_later)[2]["amount"] == 11997           # both workshop seats are now in


@pytest.mark.parametrize("name,lead", [("lead_detail", "DEMO-L-5"), ("lead_timeline", "DEMO-L-5"), ("lead_money", "DEMO-L-1"), ("lead_detail", "DEMO-L-2"), ("lead_timeline", "DEMO-L-3")])
def test_a_single_lead_view_is_as_known_on_the_end_date(world, cfg, name, lead):
    prm = {**metrics.params(cfg, START, END), "lead_id": lead}
    before = metrics.run(world, "funnel", name, prm)
    future(world)
    assert metrics.run(world, "funnel", name, prm) == before
