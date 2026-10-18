from datetime import date, timedelta

import pytest

import metrics
from seed.generate import DEFAULT_AS_OF, STORIES

END = DEFAULT_AS_OF
START = END - timedelta(days=89)


def run(con, cfg, name, start=START, end=END):
    return metrics.run(con, "campaigns", name, metrics.params(cfg, start, end))


def test_campaign_summary_matches_raw_totals(db, cfg):
    rows = {r["campaign_id"]: r for r in run(db, cfg, "campaign_summary")}
    assert set(rows) >= {STORIES[k] for k in ("scale", "fatigue", "asset", "landing", "volume", "workshop_ok")}
    spend, impr, clicks = db.execute("SELECT sum(spend), sum(impressions), sum(clicks) FROM ad_daily WHERE day BETWEEN ? AND ?", [START, END]).fetchone()
    assert sum(r["spend"] for r in rows.values()) == pytest.approx(spend)
    assert sum(r["clicks"] for r in rows.values()) == clicks
    assert all(r["ctr"] == pytest.approx(r["clicks"] / r["impressions"]) for r in rows.values())


def test_weak_asset_is_worst_in_its_campaign(db, cfg):
    rows = [r for r in run(db, cfg, "asset_ctr") if r["campaign_id"] == STORIES["asset"]]
    worst = min(rows, key=lambda r: r["ctr"])
    assert worst["ad_id"] == STORIES["weak_asset"]
    assert max(r["ctr"] for r in rows) > worst["ctr"]


def test_asset_ctr_is_null_without_impressions(empty, cfg):
    empty.execute("INSERT INTO campaigns VALUES ('DEMO-C-1', 'c', 'program')")
    empty.execute("INSERT INTO ad_sets VALUES ('DEMO-AS-1', 'DEMO-C-1', 's')")
    empty.execute("INSERT INTO ads VALUES ('DEMO-AD-1', 'DEMO-AS-1', 'a1'), ('DEMO-AD-2', 'DEMO-AS-1', 'a2')")
    empty.execute("INSERT INTO ad_daily VALUES ('DEMO-AD-1', '2026-10-05', 100, 0, 0), ('DEMO-AD-2', '2026-10-05', 100, 1000, 20)")
    rows = {r["ad_id"]: r for r in run(empty, cfg, "asset_ctr", date(2026, 10, 1), date(2026, 10, 10))}
    assert rows["DEMO-AD-1"]["ctr"] is None and rows["DEMO-AD-2"]["ctr"] == pytest.approx(0.02)


def test_fatigued_ad_set_flagged_now_and_not_before_it_decayed(db, cfg):
    now = {r["ad_set_id"]: r for r in run(db, cfg, "adset_frequency")}
    assert now[STORIES["fatigue_ad_set"]]["needs_change"] is True
    assert now[STORIES["fatigue_ad_set"]]["frequency"] >= 3
    assert [k for k, r in now.items() if r["needs_change"]] == [STORIES["fatigue_ad_set"]]       # nothing else is over the line
    earlier = {r["ad_set_id"]: r for r in run(db, cfg, "adset_frequency", END - timedelta(days=149), END - timedelta(days=120))}
    assert earlier[STORIES["fatigue_ad_set"]]["needs_change"] is False


def test_frequency_threshold_comes_from_config(db, cfg):
    low = {**cfg, "campaign": {**cfg["campaign"], "frequency_change_at": 1.0}}
    rows = metrics.run(db, "campaigns", "adset_frequency", metrics.params(low, START, END))
    assert all(r["needs_change"] for r in rows)


def test_landing_page_story_is_worst_on_both_measures(db, cfg):
    rows = run(db, cfg, "landing_health")
    assert max(rows, key=lambda r: r["drop_off_rate"])["campaign_id"] == STORIES["landing"]
    assert max(rows, key=lambda r: r["avg_load_seconds"])["campaign_id"] == STORIES["landing"]


def test_ctr_daily_has_one_row_per_campaign_per_day(db, cfg):
    rows = run(db, cfg, "ctr_daily", END - timedelta(days=6), END)
    assert len(rows) == 8 * 7 and {r["day"] for r in rows} == {END - timedelta(days=i) for i in range(7)}


def test_empty_period_returns_empty(db, cfg):
    start, end = date(2020, 1, 1), date(2020, 1, 7)
    for name in ("campaign_summary", "asset_ctr", "adset_frequency", "landing_health", "ctr_daily"):
        assert run(db, cfg, name, start, end) == [], name
