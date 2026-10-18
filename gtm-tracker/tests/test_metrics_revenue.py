from datetime import date, timedelta

import pytest

import metrics
from seed.generate import DEFAULT_AS_OF

END = DEFAULT_AS_OF
MONTH_START = END.replace(day=1)


def run(con, cfg, name, start, end):
    return metrics.run(con, "revenue", name, metrics.params(cfg, start, end))


def test_target_vs_actual_is_the_periods_cash_against_a_prorated_target(db, cfg):
    start = END - timedelta(days=89)
    row = run(db, cfg, "target_vs_actual", start, END)[0]
    invoices = db.execute("SELECT coalesce(sum(amount), 0) FROM invoices WHERE paid_on BETWEEN ? AND ?", [start, END]).fetchone()[0]
    workshops = db.execute("SELECT coalesce(sum(amount), 0) FROM workshop_payments WHERE paid_at::DATE BETWEEN ? AND ?", [start, END]).fetchone()[0]
    assert row["actual"] == invoices + workshops
    expected = 0.0
    day = start
    while day <= END:
        month_start = day.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        target = db.execute("SELECT target FROM revenue_targets WHERE month = ?", [month_start]).fetchone()[0]
        expected += target / (next_month - month_start).days
        day += timedelta(days=1)
    assert row["target"] == pytest.approx(expected)


def test_target_vs_actual_changes_with_the_period(db, cfg):
    seven = run(db, cfg, "target_vs_actual", END - timedelta(days=6), END)[0]
    ninety = run(db, cfg, "target_vs_actual", END - timedelta(days=89), END)[0]
    assert seven["actual"] < ninety["actual"] and seven["target"] < ninety["target"]


def test_a_whole_calendar_month_gets_exactly_that_months_target(db, cfg):
    row = run(db, cfg, "target_vs_actual", date(2026, 9, 1), date(2026, 9, 30))[0]
    assert row["target"] == pytest.approx(db.execute("SELECT target FROM revenue_targets WHERE month = '2026-09-01'").fetchone()[0])


def test_signup_split_matches_enrollments_in_period(db, cfg):
    start = END - timedelta(days=89)
    rows = run(db, cfg, "signup_split", start, END)
    expected = db.execute("SELECT count(*) FROM enrollments WHERE started_on BETWEEN ? AND ?", [start, END]).fetchone()[0]
    assert sum(r["students"] for r in rows) == expected
    assert {r["kind"] for r in rows} == {"program", "trial_3m"}


def test_onboarded_monthly_sums_to_period_total(db, cfg):
    start = END - timedelta(days=89)
    rows = run(db, cfg, "onboarded_monthly", start, END)
    assert sum(r["students"] for r in rows) == db.execute("SELECT count(*) FROM enrollments WHERE started_on BETWEEN ? AND ?", [start, END]).fetchone()[0]
    assert [r["month"] for r in rows] == sorted(r["month"] for r in rows)


def test_workshop_revenue_is_seats_times_price(db, cfg):
    rows = run(db, cfg, "workshop_revenue", END - timedelta(days=89), END)
    assert rows and all(r["amount"] == r["seats"] * 3999 for r in rows)


def test_program_vs_workshop_splits_cash(db, cfg):
    start = END - timedelta(days=29)
    rows = {r["stream"]: r["amount"] for r in run(db, cfg, "program_vs_workshop", start, END)}
    assert rows["program"] == db.execute("SELECT coalesce(sum(amount), 0) FROM invoices WHERE paid_on BETWEEN ? AND ?", [start, END]).fetchone()[0]
    assert rows["workshop"] == db.execute("SELECT coalesce(sum(amount), 0) FROM workshop_payments WHERE paid_at::DATE BETWEEN ? AND ?", [start, END]).fetchone()[0]


def test_unpaid_invoices_are_those_issued_in_the_period_and_unpaid_at_its_end(empty, cfg):
    empty.execute("INSERT INTO enrollments VALUES ('DEMO-EN-1', 'DEMO-ST-1', NULL, 'program', '2026-08-01', NULL, 1000)")
    empty.execute("INSERT INTO invoices VALUES ('DEMO-INV-1', 'DEMO-EN-1', '2026-09-01', '2026-09-08', 500, '2026-10-05')")    # issued in Sep, paid after Sep ends
    empty.execute("INSERT INTO invoices VALUES ('DEMO-INV-2', 'DEMO-EN-1', '2026-09-01', '2026-09-08', 500, '2026-09-09')")    # paid before Sep ends
    empty.execute("INSERT INTO invoices VALUES ('DEMO-INV-3', 'DEMO-EN-1', '2026-10-01', '2026-10-20', 500, NULL)")           # issued in Oct, unpaid
    empty.execute("INSERT INTO invoices VALUES ('DEMO-INV-4', 'DEMO-EN-1', '2026-08-01', '2026-08-08', 500, NULL)")           # issued in Aug, unpaid
    sep = run(empty, cfg, "unpaid_invoices", date(2026, 9, 1), date(2026, 9, 30))
    assert [r["invoice_id"] for r in sep] == ["DEMO-INV-1"] and sep[0]["days_overdue"] == 22
    early_oct = run(empty, cfg, "unpaid_invoices", date(2026, 10, 1), date(2026, 10, 4))
    assert [(r["invoice_id"], r["days_overdue"]) for r in early_oct] == [("DEMO-INV-3", 0)]
    wide = run(empty, cfg, "unpaid_invoices", date(2026, 8, 1), date(2026, 10, 4))
    assert [r["invoice_id"] for r in wide] == ["DEMO-INV-4", "DEMO-INV-1", "DEMO-INV-3"]      # most overdue first


def test_unpaid_invoices_change_with_the_period(db, cfg):
    seven = run(db, cfg, "unpaid_invoices", END - timedelta(days=6), END)
    ninety = run(db, cfg, "unpaid_invoices", END - timedelta(days=89), END)
    assert len(seven) < len(ninety)


def test_upcoming_renewals_window(db, cfg):
    rows = run(db, cfg, "upcoming_renewals", END - timedelta(days=29), END)
    assert len(rows) >= 3
    assert all(0 <= r["days_left"] <= 30 for r in rows)
    assert [r["renewal_on"] for r in rows] == sorted(r["renewal_on"] for r in rows)


def test_period_with_no_data_returns_empty_not_errors(db, cfg):
    start, end = date(2020, 1, 1), date(2020, 1, 7)
    assert run(db, cfg, "signup_split", start, end) == []
    assert run(db, cfg, "workshop_revenue", start, end) == []
    assert run(db, cfg, "onboarded_monthly", start, end) == []
    row = run(db, cfg, "target_vs_actual", start, end)[0]
    assert row["actual"] == 0 and row["target"] is None


@pytest.fixture
def october(empty):
    """October by hand. EN-0: an earlier program student, second installment Rs 2,50,000 paid 9 Oct. EN-1: a new program student, Rs 2,50,000 paid 8 Oct.
    EN-2: a new trial student, Rs 1,75,000 paid 12 Oct. Plus workshop seats Rs 7,998 paid 9 Oct, and one invoice paid in September (outside the period)."""
    empty.execute("INSERT INTO enrollments VALUES ('DEMO-EN-0', 'DEMO-ST-0', NULL, 'program', '2026-08-01', NULL, 500000), "
                  "('DEMO-EN-1', 'DEMO-ST-1', NULL, 'program', '2026-10-05', NULL, 500000), ('DEMO-EN-2', 'DEMO-ST-2', NULL, 'trial_3m', '2026-10-06', '2027-01-04', 175000)")
    empty.execute("INSERT INTO invoices VALUES ('DEMO-INV-0', 'DEMO-EN-0', '2026-10-02', '2026-10-09', 250000, '2026-10-09'), ('DEMO-INV-1', 'DEMO-EN-1', '2026-10-05', '2026-10-12', 250000, '2026-10-08'), "
                  "('DEMO-INV-2', 'DEMO-EN-2', '2026-10-06', '2026-10-13', 175000, '2026-10-12'), ('DEMO-INV-3', 'DEMO-EN-0', '2026-09-02', '2026-09-09', 250000, '2026-09-08')")
    empty.execute("INSERT INTO workshops VALUES ('DEMO-WS-1', NULL, 'w', '2026-10-09')")
    empty.execute("INSERT INTO workshop_payments VALUES ('DEMO-PAY-1', 'DEMO-WS-1', 'DEMO-L-7', '2026-10-09 10:00:00', 2, 7998)")
    return empty


def records(con, cfg, stream, start=date(2026, 10, 1), end=date(2026, 10, 31)):
    return metrics.run(con, "revenue", "cash_records", {**metrics.params(cfg, start, end), "stream": stream})


def test_cash_breakdown_by_hand(october, cfg):
    rows = run(october, cfg, "cash_breakdown", date(2026, 10, 1), date(2026, 10, 31))
    assert [(r["stream"], r["amount"], r["payments"]) for r in rows] == [("Full program", 500000, 2), ("3-month trial", 175000, 1), ("Workshop seats", 7998, 1)]


@pytest.mark.parametrize("days", [7, 30, 90, 180])
def test_cash_breakdown_always_adds_up_to_the_achieved_number(db, cfg, days):
    start = END - timedelta(days=days - 1)
    assert sum(r["amount"] for r in run(db, cfg, "cash_breakdown", start, END)) == run(db, cfg, "target_vs_actual", start, END)[0]["actual"]


@pytest.mark.parametrize("stream", ["Full program", "3-month trial", "Workshop seats"])
def test_the_records_behind_a_row_add_up_to_that_row(db, cfg, stream):
    start = END - timedelta(days=89)
    row = next(r for r in run(db, cfg, "cash_breakdown", start, END) if r["stream"] == stream)
    rows = records(db, cfg, stream, start, END)
    assert len(rows) == row["payments"] and sum(r["amount"] for r in rows) == pytest.approx(row["amount"])


def test_cash_records_by_hand_newest_first_with_the_enrollment_date(october, cfg):
    program = records(october, cfg, "Full program")
    assert [(r["reference"], r["who"], r["paid_on"], r["enrolled_on"], r["amount"]) for r in program] == [
        ("DEMO-INV-0", "DEMO-ST-0", date(2026, 10, 9), date(2026, 8, 1), 250000), ("DEMO-INV-1", "DEMO-ST-1", date(2026, 10, 8), date(2026, 10, 5), 250000)]
    workshop = records(october, cfg, "Workshop seats")
    assert [(r["reference"], r["who"], r["enrolled_on"], r["amount"]) for r in workshop] == [("DEMO-PAY-1", "DEMO-L-7", None, 7998)]


def test_cash_records_for_an_unknown_stream_or_an_empty_period_are_empty(october, cfg):
    assert records(october, cfg, "Nonsense") == []
    assert records(october, cfg, "Full program", date(2020, 1, 1), date(2020, 1, 7)) == []


def test_cash_breakdown_for_an_empty_period_has_all_three_rows_at_zero(db, cfg):
    rows = run(db, cfg, "cash_breakdown", date(2020, 1, 1), date(2020, 1, 7))
    assert [(r["stream"], r["amount"], r["payments"]) for r in rows] == [("Full program", 0, 0), ("3-month trial", 0, 0), ("Workshop seats", 0, 0)]


@pytest.mark.parametrize("days", [30, 90])
def test_program_cash_is_close_to_the_new_program_students_times_the_fee(db, cfg, days):
    """One invoice per student, paid within days of enrolling, so cash for a period tracks the sign-ups in it (a student enrolling late in the period may pay after it)."""
    start = END - timedelta(days=days - 1)
    booked = next(r["amount"] for r in run(db, cfg, "signup_split", start, END) if r["kind"] == "program")
    cash = next(r["amount"] for r in run(db, cfg, "cash_breakdown", start, END) if r["stream"] == "Full program")
    assert booked > 0 and 0.85 <= cash / booked <= 1.15, (cash, booked)


def test_the_bridge_from_sign_ups_to_cash_by_hand(october, cfg):
    rows = {r["stream"]: r for r in run(october, cfg, "cash_breakdown", date(2026, 10, 1), date(2026, 10, 31))}
    program, trial, workshop = rows["Full program"], rows["3-month trial"], rows["Workshop seats"]
    assert (program["students"], program["contract"], program["paid_new"], program["not_collected"], program["earlier"], program["amount"], program["payments"]) == (1, 500000, 250000, 250000, 250000, 500000, 2)
    assert (trial["students"], trial["contract"], trial["paid_new"], trial["not_collected"], trial["earlier"], trial["amount"]) == (1, 175000, 175000, 0, 0, 175000)
    assert workshop["amount"] == 7998 and workshop["students"] is None and workshop["contract"] is None and workshop["earlier"] is None      # a workshop seat has no sign-up behind it


@pytest.mark.parametrize("days", [7, 30, 90, 180])
def test_the_bridge_adds_up_on_the_seed_for_every_period(db, cfg, days):
    start = END - timedelta(days=days - 1)
    signups = {r["kind"]: r for r in run(db, cfg, "signup_split", start, END)}
    for row in run(db, cfg, "cash_breakdown", start, END):
        if row["stream"] == "Workshop seats":
            continue
        kind = {"Full program": "program", "3-month trial": "trial_3m"}[row["stream"]]
        assert row["contract"] == pytest.approx(row["paid_new"] + row["not_collected"])         # what the new students owe = paid so far + not collected yet
        assert row["amount"] == pytest.approx(row["paid_new"] + row["earlier"])                 # cash = new students' payments + earlier students' payments
        assert row["students"] == signups.get(kind, {"students": 0})["students"]
        assert row["contract"] == pytest.approx(signups.get(kind, {"amount": 0})["amount"])


def test_the_bridge_for_an_empty_period_is_all_zero_for_sign_up_rows(db, cfg):
    rows = {r["stream"]: r for r in run(db, cfg, "cash_breakdown", date(2020, 1, 1), date(2020, 1, 7))}
    for stream in ("Full program", "3-month trial"):
        assert all(rows[stream][k] == 0 for k in ("students", "contract", "paid_new", "not_collected", "earlier", "amount", "payments"))
