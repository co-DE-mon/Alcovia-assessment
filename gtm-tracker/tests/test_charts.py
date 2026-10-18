import pytest

from views import charts

PARTS = [
    dict(stream="Full program", students=14, contract=7_000_000, paid_new=4_000_000, not_collected=3_000_000, earlier=3_500_000, amount=7_500_000, payments=15),
    dict(stream="3-month trial", students=4, contract=700_000, paid_new=350_000, not_collected=350_000, earlier=875_000, amount=1_225_000, payments=7),
    dict(stream="Workshop seats", students=None, contract=None, paid_new=None, not_collected=None, earlier=None, amount=55_992, payments=2),
]


def test_bridge_steps_walk_from_the_contract_value_to_the_achieved_number():
    steps = charts.bridge_steps(PARTS)
    assert [s["label"] for s in steps] == ["Contract value of new sign-ups", "Not collected yet", "Paid by earlier students", "Workshop seats", "Achieved"]
    assert [s["kind"] for s in steps] == ["total", "down", "up", "up", "total"]
    assert [(s["start"], s["end"]) for s in steps] == [(0, 7_700_000), (7_700_000, 4_350_000), (4_350_000, 8_725_000), (8_725_000, 8_780_992), (0, 8_780_992)]
    assert steps[-1]["end"] == sum(p["amount"] for p in PARTS)                 # it ends exactly on the achieved number
    assert [s["value"] for s in steps] == [7_700_000, -3_350_000, 4_375_000, 55_992, 8_780_992]


def test_bridge_steps_never_drop_below_zero_and_cope_with_no_students():
    empty = [dict(PARTS[0], students=0, contract=0, paid_new=0, not_collected=0, earlier=0, amount=0, payments=0), dict(PARTS[1], students=0, contract=0, paid_new=0, not_collected=0, earlier=0, amount=0, payments=0),
             dict(PARTS[2], amount=0, payments=0)]
    steps = charts.bridge_steps(empty)
    assert all(s["start"] >= 0 and s["end"] >= 0 for s in steps) and steps[-1]["end"] == 0
    only_cash = [dict(PARTS[0], students=0, contract=0, paid_new=0, not_collected=0, earlier=1_000_000, amount=1_000_000), PARTS[1], PARTS[2]]
    assert all(s["start"] >= 0 for s in charts.bridge_steps(only_cash))


def test_bridge_on_the_seed_ends_on_the_achieved_number_for_every_period(db, cfg):
    from datetime import timedelta
    import metrics
    from seed.generate import DEFAULT_AS_OF as E
    for days in (7, 30, 90, 180):
        prm = metrics.params(cfg, E - timedelta(days=days - 1), E)
        steps = charts.bridge_steps(metrics.run(db, "revenue", "cash_breakdown", prm))
        assert steps[-1]["end"] == pytest.approx(metrics.run(db, "revenue", "target_vs_actual", prm)[0]["actual"])


def test_bridge_bars_are_plain_amounts_that_each_start_at_zero_not_a_running_total():
    rows = charts.bridge_bar_rows(charts.bridge_steps(PARTS))
    assert [r["label"] for r in rows] == ["Contract value of new sign-ups", "Not collected yet", "Paid by earlier students", "Workshop seats", "Achieved"]
    assert [r["amount"] for r in rows] == [7_700_000, 3_350_000, 4_375_000, 55_992, 8_780_992]      # each bar is its own amount; none builds on the one before
    assert all(r["amount"] >= 0 for r in rows) and "start" not in rows[0]
    assert [r["role"] for r in rows] == ["total", "part", "part", "part", "total"]
    assert [r["text"] for r in rows] == ["₹77.0L", "₹33.5L", "₹43.8L", "₹0.6L", "₹87.8L"]


def test_the_value_axis_is_written_in_lakhs():
    assert "100000" in charts.LAKH_AXIS and charts.LAKH_AXIS.endswith("'L'")
