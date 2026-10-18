"""Expected verdicts (README.md) on the dummy data, last 90 days. If one fails, the message prints the calculated inputs and the rule that failed.
The expected labels are never reached by changing a threshold or the fixtures: a failure is a finding to report."""
from datetime import timedelta

import pytest

import rca
from seed.generate import DEFAULT_AS_OF as END, STORIES

START = END - timedelta(days=89)

EXPECTED = {   # campaign: (verdict, a text a flag or reason must contain, or None)
    "scale": ("Scale", None),
    "decline": ("Hold", "worsening"),
    "asset": ("Hold", "AD-ASSET-3"),
    "fatigue": ("Pause", "Creative refresh needed"),
    "landing": ("Too early", "Fix landing page"),
    "new": ("Too early", None),
    "volume": ("Pause", "advertising only"),
    "workshop_ok": ("Pause", "advertising only"),
}


@pytest.fixture(scope="module")
def result(db_module, cfg_module):
    return rca.assess(db_module, cfg_module, START, END)


def explain(result, campaign_id):
    inputs = next(r for r in result["program_inputs"] + result["workshop_inputs"] if r["campaign_id"] == campaign_id)
    shown = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in inputs.items()}
    v = next(r for r in result["verdicts"] if r["campaign_id"] == campaign_id)
    return f"\\n  verdict={v['label']!r} confidence={v['confidence']!r}\\n  reasons={v['reasons']}\\n  flags={v['flags']}\\n  inputs={shown}\\n  medians={result['medians']}"


@pytest.mark.parametrize("key", list(EXPECTED))
def test_expected_verdict(result, key):
    campaign_id = STORIES[key]
    verdict, needle = EXPECTED[key]
    got = next(r for r in result["verdicts"] if r["campaign_id"] == campaign_id)
    text = " | ".join(got["reasons"] + got["flags"])
    assert got["verdict"] == verdict, f"{campaign_id} expected {verdict}, got {got['verdict']}" + explain(result, campaign_id)
    if needle:
        assert needle in text, f"{campaign_id}: expected '{needle}' among the reasons or flags" + explain(result, campaign_id)


def test_every_campaign_gets_exactly_one_verdict(result):
    ids = [v["campaign_id"] for v in result["verdicts"]]
    assert sorted(ids) == sorted(STORIES[k] for k in EXPECTED) and len(set(ids)) == len(ids)


def test_a_seven_day_view_does_not_shorten_the_program_lookback(db_module, cfg_module):
    seven = rca.assess(db_module, cfg_module, END - timedelta(days=6), END)
    ninety = rca.assess(db_module, cfg_module, START, END)
    pick = lambda res: {v["campaign_id"]: v["verdict"] for v in res["verdicts"] if v["kind"] == "program"}
    assert pick(seven) == pick(ninety)                                                       # program verdicts ignore the selector's start day
    assert {v["campaign_id"]: v["verdict"] for v in seven["verdicts"] if v["kind"] == "workshop"} != {v["campaign_id"]: v["verdict"] for v in ninety["verdicts"] if v["kind"] == "workshop"}


def test_a_past_end_date_uses_only_what_was_known_then(db_module, cfg_module):
    past = rca.assess(db_module, cfg_module, END - timedelta(days=119), END - timedelta(days=30))
    inputs = {r["campaign_id"]: r for r in past["program_inputs"]}
    assert STORIES["new"] not in inputs                                                      # it had not launched yet
    assert all(r["days_running"] >= 1 for r in inputs.values())
