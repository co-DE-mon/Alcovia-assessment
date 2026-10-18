"""RCA inputs, computed from hand-built data. Everything is as known on the end date (31 Oct): a 90-day lookback from 3 Aug, mature leads created 3 Aug to 3 Oct,
recent leads created 4 Oct to 31 Oct."""
from datetime import date, timedelta

import pytest

import metrics

END = date(2026, 10, 31)


def run(con, cfg, name, start=date(2026, 8, 1), end=END):
    return metrics.run(con, "rca", name, metrics.params(cfg, start, end))


def days(first, last):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


@pytest.fixture
def program(empty):
    con = empty
    con.execute("INSERT INTO campaigns VALUES ('DEMO-C-1', 'prog', 'program')")
    con.execute("INSERT INTO ad_sets VALUES ('DEMO-AS-1', 'DEMO-C-1', 's1')")
    con.execute("INSERT INTO ads VALUES ('DEMO-AD-1', 'DEMO-AS-1', 'strong'), ('DEMO-AD-2', 'DEMO-AS-1', 'weak')")
    for day in days(date(2026, 8, 3), END):
        spend = 1000 if day <= date(2026, 10, 3) else 2000                          # mature window 62 days x 1,000; recent window 28 days x 2,000
        clicks1 = 200 if day <= date(2026, 10, 17) else 161                          # the strong ad slips in the last 14 days
        con.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-1', ?, ?, 10000, ?), ('DEMO-AD-2', ?, 0, 10000, 60)", [day, spend, clicks1, day])
        con.execute("INSERT INTO landing_page_daily VALUES ('DEMO-C-1', ?, 100, 40, 3.0)", [day])
    con.execute("INSERT INTO ad_set_daily VALUES ('DEMO-AS-1', '2026-10-31', 5000, 3.4), ('DEMO-AS-1', '2026-10-30', 5000, 3.0), ('DEMO-AS-1', '2026-11-03', 5000, 1.0)")      # 3 Nov is after the end date

    def lead(n, created, qualified=True, qualified_on=None):
        con.execute("INSERT INTO leads (lead_id, source_lead, campaign_id, created_at) VALUES (?, 'paid_ads', 'DEMO-C-1', ?)", [f"DEMO-L-{n}", created])
        con.execute("INSERT INTO lead_stages VALUES (?, 'lead', ?)", [f"DEMO-L-{n}", created])
        if qualified:
            con.execute("INSERT INTO lead_stages VALUES (?, 'qualified', ?)", [f"DEMO-L-{n}", qualified_on or created])

    for n in range(1, 11):                                   # 10 mature leads (created Aug to Sep), 6 qualified
        lead(n, f"2026-09-{n:02d} 10:00:00", qualified=n <= 6)
    lead(11, "2026-07-01 10:00:00")                          # before the lookback: ignored
    for n, d in zip(range(12, 16), (10, 12, 14, 16)):        # 4 recent leads, 2 qualified by the end, 1 qualified only after it
        lead(n, f"2026-10-{d:02d} 10:00:00", qualified=n in (12, 13, 14), qualified_on="2026-11-02 10:00:00" if n == 14 else None)

    def paid(n, kind, eid, started, invoice_paid):
        amount = 500000 if kind == "program" else 175000
        con.execute("INSERT INTO enrollments VALUES (?, ?, ?, ?, ?, NULL, ?)", [eid, f"DEMO-ST-{eid}", f"DEMO-L-{n}", kind, started, amount])
        con.execute("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", [f"DEMO-INV-{eid}", eid, started, started, amount, invoice_paid])
    paid(1, "program", "A", "2026-09-20", "2026-09-21")
    paid(2, "program", "B", "2026-09-22", "2026-09-23")
    paid(3, "program", "C", "2026-10-01", "2026-10-02")
    paid(4, "trial_3m", "D", "2026-09-25", "2026-09-26")
    paid(5, "program", "E", "2026-10-25", "2026-11-04")      # enrolled, but the payment arrives after the end date: not a paid customer on 31 Oct
    paid(12, "program", "F", "2026-10-20", "2026-10-21")      # a recent lead that paid: counts toward 'any paid', not toward the mature figures
    return con


def test_program_inputs_by_hand(program, cfg):
    row = run(program, cfg, "program_inputs")[0]
    assert (row["leads"], row["qualified"]) == (14, 8)                                    # 14 leads created in the lookback; 6 mature + 2 recent qualified by the end (lead 14 qualifies only on 2 Nov)
    assert (row["mature_leads"], row["mature_qualified"], row["mature_paid_program"], row["mature_paid_trial"]) == (10, 6, 3, 1)
    assert row["mature_spend"] == 62_000 and row["recent_spend"] == 56_000 and row["spend_to_date"] == 118_000
    assert row["recent_qualified"] == 2                                                   # leads 12 and 13; lead 14 qualified on 2 Nov, after the end date
    assert row["cpql_mature"] == pytest.approx(62_000 / 6) and row["cpql_recent"] == pytest.approx(28_000)
    assert row["cpql_ratio"] == pytest.approx(28_000 / (62_000 / 6))
    assert row["cost_per_paid_program"] == pytest.approx(62_000 / 3)
    assert row["conv_rate"] == pytest.approx(4 / 6)
    assert row["paid_any"] == 5                                                           # leads 1, 2, 3, 4 and 12; lead 5's payment came after the end date
    assert row["days_running"] == 90 and row["first_day"] == date(2026, 8, 3)
    assert row["landing_drop_off"] == pytest.approx(0.4) and row["landing_load"] == pytest.approx(3.0)


def test_program_inputs_ignore_everything_after_the_end_date(program, cfg):
    before = run(program, cfg, "program_inputs")
    program.execute("INSERT INTO lead_stages VALUES ('DEMO-L-9', 'qualified', '2026-11-10 10:00:00'), ('DEMO-L-9', 'signed', '2026-11-20 10:00:00')")
    program.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-1', '2026-11-05', 99999, 10000, 100)")
    program.execute("UPDATE invoices SET paid_on = '2026-11-30' WHERE invoice_id = 'DEMO-INV-A'")
    after = run(program, cfg, "program_inputs")
    assert after[0]["mature_paid_program"] == 2 and before[0]["mature_paid_program"] == 3        # the changed invoice WAS paid on 21 Sep: rewriting it to 30 Nov means it was unpaid on 31 Oct
    assert after[0]["spend_to_date"] == before[0]["spend_to_date"] and after[0]["mature_qualified"] == before[0]["mature_qualified"]


def test_program_with_no_paid_program_customer_has_no_cost_per_paid_program_not_zero(program, cfg):
    program.execute("DELETE FROM invoices WHERE invoice_id IN ('DEMO-INV-A', 'DEMO-INV-B', 'DEMO-INV-C')")
    row = run(program, cfg, "program_inputs")[0]
    assert row["mature_paid_program"] == 0 and row["cost_per_paid_program"] is None


def test_program_with_no_qualified_leads_has_null_costs(program, cfg):
    program.execute("DELETE FROM lead_stages WHERE stage = 'qualified'")
    row = run(program, cfg, "program_inputs")[0]
    assert row["cpql_mature"] is None and row["cpql_recent"] is None and row["cpql_ratio"] is None and row["conv_rate"] is None


def test_adset_signals_by_hand(program, cfg):
    row = run(program, cfg, "adset_signals")[0]
    assert row["frequency"] == 3.4                                                         # the last day on or before the end date; the 3 Nov row is ignored
    assert row["impressions_recent"] == 14 * 20_000 and row["impressions_prior"] == 14 * 20_000
    assert row["clicks_prior"] == 14 * 260 and row["clicks_recent"] == 14 * 221
    assert row["ctr_change"] == pytest.approx(221 / 260 - 1)                               # -15%


def test_adset_with_no_prior_impressions_has_no_ctr_change_instead_of_dividing_by_zero(program, cfg):
    program.execute("DELETE FROM ad_daily WHERE day BETWEEN '2026-10-04' AND '2026-10-17'")
    row = run(program, cfg, "adset_signals")[0]
    assert row["ctr_change"] is None and row["ctr_prior"] is None


def test_ad_signals_flag_the_weak_ad_against_its_campaign_median(program, cfg):
    rows = {r["ad_id"]: r for r in run(program, cfg, "ad_signals")}
    strong = (76 * 200 + 14 * 161) / (90 * 10_000)
    assert rows["DEMO-AD-1"]["ctr"] == pytest.approx(strong) and rows["DEMO-AD-2"]["ctr"] == pytest.approx(0.006)
    median = (strong + 0.006) / 2
    assert rows["DEMO-AD-2"]["vs_median"] == pytest.approx(0.006 / median - 1) and rows["DEMO-AD-2"]["vs_median"] <= -0.5
    assert rows["DEMO-AD-1"]["vs_median"] > 0


def test_ad_signals_give_no_comparison_when_the_median_is_zero(program, cfg):
    program.execute("UPDATE ad_daily SET clicks = 0")
    assert all(r["vs_median"] is None for r in run(program, cfg, "ad_signals"))


@pytest.fixture
def workshop(empty):
    con = empty
    con.execute("INSERT INTO campaigns VALUES ('DEMO-C-2', 'ws', 'workshop')")
    con.execute("INSERT INTO ad_sets VALUES ('DEMO-AS-2', 'DEMO-C-2', 's')")
    con.execute("INSERT INTO ads VALUES ('DEMO-AD-3', 'DEMO-AS-2', 'a')")
    for day in days(date(2026, 8, 1), END):
        con.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-3', ?, 500, 10000, 150)", [day])
        con.execute("INSERT INTO landing_page_daily VALUES ('DEMO-C-2', ?, 100, 30, 2.0)", [day])
    con.execute("INSERT INTO workshops VALUES ('DEMO-WS-1', 'DEMO-C-2', 'w', '2026-10-10')")
    for n, (lead, when, seats) in enumerate([("DEMO-L-C", "2026-08-20 10:00:00", 1), ("DEMO-L-D", "2026-08-25 10:00:00", 1), ("DEMO-L-E", "2026-08-28 10:00:00", 1),
                                              ("DEMO-L-A", "2026-10-09 10:00:00", 2), ("DEMO-L-B", "2026-10-20 10:00:00", 1), ("DEMO-L-Z", "2026-11-05 10:00:00", 4)], 1):
        con.execute("INSERT INTO workshop_payments VALUES (?, 'DEMO-WS-1', ?, ?, ?, ?)", [f"DEMO-PAY-{n}", lead, when, seats, seats * 3999])
    for n, (created, qualified_on) in enumerate([("2026-08-05", "2026-08-06"), ("2026-09-05", "2026-09-06"), ("2026-10-05", "2026-10-06"), ("2026-10-25", "2026-11-03"), ("2026-10-26", None)], 1):
        con.execute("INSERT INTO leads (lead_id, source_lead, campaign_id, created_at) VALUES (?, 'paid_ads', 'DEMO-C-2', ?)", [f"DEMO-W-{n}", f"{created} 10:00:00"])
        con.execute("INSERT INTO lead_stages VALUES (?, 'lead', ?)", [f"DEMO-W-{n}", f"{created} 10:00:00"])
        if qualified_on:
            con.execute("INSERT INTO lead_stages VALUES (?, 'qualified', ?)", [f"DEMO-W-{n}", f"{qualified_on} 10:00:00"])
    con.execute("INSERT INTO enrollments VALUES ('DEMO-EN-C', 'DEMO-ST-C', 'DEMO-L-C', 'program', '2026-09-10', NULL, 500000)")     # 21 days after the seat: converted
    con.execute("INSERT INTO enrollments VALUES ('DEMO-EN-E', 'DEMO-ST-E', 'DEMO-L-E', 'program', '2026-10-30', NULL, 500000)")     # 63 days after the seat: too late
    return con


def test_workshop_inputs_by_hand(workshop, cfg):
    row = run(workshop, cfg, "workshop_inputs")[0]
    assert row["days_running"] == 92 and row["spend"] == 46_000
    assert row["paid_seats"] == 6 and row["revenue"] == 6 * 3999                          # the 5 Nov payment is after the end date and is not counted
    assert row["cost_per_seat"] == pytest.approx(46_000 / 6) and row["revenue_ratio"] == pytest.approx(6 * 3999 / 46_000)
    assert row["qualified"] == 3                                                           # W-4 qualified only on 3 Nov, W-5 never
    assert row["landing_drop_off"] == pytest.approx(0.3) and row["landing_load"] == pytest.approx(2.0)


def test_workshop_follow_up_uses_only_buyers_with_a_complete_60_day_window(workshop, cfg):
    row = run(workshop, cfg, "workshop_inputs")[0]
    assert row["followup_buyers"] == 3                                                     # C, D and E paid on or before 2 Sep (60 days before the end); A and B have not had 60 days
    assert row["followup_converted"] == 1                                                  # only C enrolled within 60 days of their seat
    assert row["followup_rate"] == pytest.approx(1 / 3)


def test_workshop_with_no_seats_has_no_cost_per_seat_and_a_zero_ratio(workshop, cfg):
    workshop.execute("DELETE FROM workshop_payments")
    row = run(workshop, cfg, "workshop_inputs")[0]
    assert row["paid_seats"] == 0 and row["cost_per_seat"] is None and row["revenue_ratio"] == 0 and row["followup_rate"] is None


def test_workshop_inputs_follow_the_selected_window(workshop, cfg):
    row = run(workshop, cfg, "workshop_inputs", date(2026, 10, 1), END)[0]
    assert row["days_running"] == 31 and row["spend"] == 15_500 and row["paid_seats"] == 3 and row["revenue"] == 3 * 3999
