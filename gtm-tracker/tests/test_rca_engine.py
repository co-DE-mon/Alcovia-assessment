"""RCA rules (README.md), one behaviour per test, on hand-built inputs. Thresholds come from config.yaml; nothing here is tuned to a dataset."""
import pytest

import rca

CFG = {"campaign": {"frequency_change_at": 3}, "rca": {
    "lookback_days": 90, "mature_after_days": 28, "min_days_running": 14, "min_qualified_leads": 30, "pause_cost_per_paid_program": 50000, "worsening_ratio": 1.30,
    "ctr_decline": 0.15, "weak_ad_below_median": 0.50, "landing_drop_off": 0.50, "landing_load_seconds": 4, "overspend_program": 50000, "overspend_workshop": 3999,
    "workshop_min_revenue_ratio": 1.0, "followup_days": 60}}


def prog(campaign_id="P", **over):
    """An eligible program campaign that is unremarkable: above the floor, cheap, no flags."""
    row = dict(campaign_id=campaign_id, name=campaign_id, days_running=90, spend_to_date=200_000, qualified=50, mature_qualified=40, mature_paid_program=8, mature_paid_trial=2,
               mature_spend=180_000, cpql_mature=4500.0, cpql_recent=4500.0, cpql_ratio=1.0, cost_per_paid_program=22_500.0, conv_rate=0.25, paid_any=10,
               landing_drop_off=0.3, landing_load=2.0)
    row.update(over)
    return row


def adset(campaign_id="P", ad_set_id="AS", frequency=1.5, ctr_change=0.0, **over):
    row = dict(campaign_id=campaign_id, ad_set_id=ad_set_id, frequency=frequency, ctr_change=ctr_change, clicks_recent=200, impressions_recent=10_000, clicks_prior=200, impressions_prior=10_000)
    row.update(over)
    return row


def ad(campaign_id="P", ad_id="AD", vs_median=0.0, **over):
    row = dict(campaign_id=campaign_id, ad_id=ad_id, asset_name=ad_id, ctr=0.02, median_ctr=0.02, vs_median=vs_median)
    row.update(over)
    return row


def one(rows, adsets=(), ads=(), campaign_id="P"):
    """Decide a set of program campaigns, return the one asked for."""
    return {r["campaign_id"]: r for r in rca.program_verdicts(rows, rca.peer_medians(rows, CFG), list(adsets), list(ads), CFG)}[campaign_id]


def peers():
    """Two comparable campaigns. The medians are taken over every eligible campaign including the one being judged, so a third campaign decides them:
    with conversion 0.15, 0.35 and a third value x the median is the middle one; with cost per qualified lead 6000, 3000 and y likewise."""
    return [prog("LOW", conv_rate=0.15, cpql_mature=6000.0), prog("HIGH", conv_rate=0.35, cpql_mature=3000.0)]


STAR = dict(conv_rate=0.40, cpql_mature=2500.0, cost_per_paid_program=15_000.0)       # conversion 0.40 beats the 0.35 median; cost 2500 beats the 3000 median


# ---- Pause ---------------------------------------------------------------------------------------------------------------------------------------------------

def test_pause_when_mature_cost_per_full_program_customer_is_above_the_ceiling():
    r = one([prog(cost_per_paid_program=50_001.0)])
    assert r["verdict"] == "Pause" and any("50,001" in x and "50,000" in x for x in r["reasons"])


def test_exactly_the_ceiling_is_not_a_pause():
    assert one([prog(cost_per_paid_program=50_000.0)])["verdict"] != "Pause"


def test_pause_needs_enough_mature_qualified_leads_to_judge_sign_ups():
    r = one([prog(cost_per_paid_program=90_000.0, mature_qualified=29)])
    assert r["verdict"] == "Too early" and "mature qualified" in r["confidence"]


def test_pause_outranks_refresh_and_keeps_the_refresh_trigger_as_a_reason_and_repair():
    r = one([prog(cost_per_paid_program=108_625.0)], [adset(frequency=3.55, ctr_change=-0.19)])
    assert r["verdict"] == "Pause"
    assert any("Creative refresh needed" in x and "3.55" in x and "19%" in x for x in r["reasons"])


def test_no_paid_full_program_customer_is_a_budget_review_flag_never_a_zero_cost_and_never_an_automatic_pause():
    r = one([prog(mature_paid_program=0, cost_per_paid_program=None, conv_rate=0.1)])
    assert r["verdict"] != "Pause" and any("No paid full-program conversions" in f and "budget review" in f for f in r["flags"])


# ---- Refresh ---------------------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("frequency,triggers", [(3.0, True), (2.99, False), (None, False)])
def test_frequency_of_three_or_more_triggers_refresh_on_its_own(frequency, triggers):
    r = one([prog()], [adset(frequency=frequency)])
    assert (r["verdict"] == "Refresh") is triggers


@pytest.mark.parametrize("change,triggers", [(-0.15, True), (-0.1499, False), (0.2, False), (None, False)])
def test_a_ctr_fall_of_at_least_fifteen_percent_triggers_refresh_and_a_missing_comparison_does_not(change, triggers):
    r = one([prog()], [adset(ctr_change=change)])
    assert (r["verdict"] == "Refresh") is triggers


def test_the_refresh_reason_shows_the_clicks_and_impressions_behind_the_ctr_fall():
    r = one([prog()], [adset(ctr_change=-0.2, clicks_recent=160, impressions_recent=10_000, clicks_prior=200, impressions_prior=10_000)])
    assert any("160" in x and "200" in x and "10,000" in x for x in r["reasons"])


def test_a_creative_or_frequency_trigger_gives_refresh_even_below_the_data_floor():
    r = one([prog(days_running=5, qualified=3, mature_qualified=0)], [adset(frequency=4.0)])
    assert r["verdict"] == "Refresh" and r["confidence"].startswith("Too early")


# ---- Scale and Hold -----------------------------------------------------------------------------------------------------------------------------------------------

def test_scale_needs_conversion_above_and_cost_per_qualified_lead_below_the_peer_medians():
    star = prog("STAR", **STAR)
    assert one(peers() + [star], campaign_id="STAR")["verdict"] == "Scale"


@pytest.mark.parametrize("conv,cpql,failed", [(0.20, 2500.0, "conversion"), (0.40, 5500.0, "Cost per qualified lead")])
def test_missing_either_median_test_is_a_hold_naming_only_the_failed_condition(conv, cpql, failed):
    r = one(peers() + [prog("X", conv_rate=conv, cpql_mature=cpql)], campaign_id="X")
    assert r["verdict"] == "Hold" and len(r["reasons"]) == 1 and failed in r["reasons"][0] and "not" in r["reasons"][0]


def test_equal_to_the_median_is_not_above_or_below_it():
    r = one(peers() + [prog("TIE", conv_rate=0.25, cpql_mature=4500.0)], campaign_id="TIE")
    assert r["verdict"] == "Hold"


def test_scale_must_also_pass_the_acquisition_cost_guardrail():
    star = prog("STAR", **{**STAR, "cost_per_paid_program": 50_001.0})
    assert one(peers() + [star], campaign_id="STAR")["verdict"] == "Pause"                 # over the ceiling, so Pause wins before Scale is even asked


def test_recent_cost_more_than_thirty_percent_worse_blocks_scale_and_reads_hold_getting_worse():
    star = prog("STAR", **STAR, cpql_ratio=1.35)
    r = one(peers() + [star], campaign_id="STAR")
    assert r["verdict"] == "Hold" and r["label"] == "Hold: recent acquisition cost worsening" and any("worsening" in f for f in r["flags"])


def test_exactly_thirty_percent_worse_is_not_worsening():
    star = prog("STAR", **STAR, cpql_ratio=1.30)
    assert one(peers() + [star], campaign_id="STAR")["verdict"] == "Scale"


def test_medians_use_only_campaigns_with_enough_mature_evidence():
    thin = [prog(f"THIN{i}", mature_qualified=10, conv_rate=0.9, cpql_mature=100.0) for i in (1, 2)]      # two tiny, lucky campaigns must not drag the medians
    star = prog("STAR", conv_rate=0.36, cpql_mature=2500.0, cost_per_paid_program=15_000.0)
    assert one(peers() + thin + [star], campaign_id="STAR")["verdict"] == "Scale"
    counted = [dict(t, mature_qualified=40) for t in thin]                                 # the same two with enough evidence would move both medians past STAR
    assert one(peers() + counted + [star], campaign_id="STAR")["verdict"] == "Hold"


def test_scale_needs_at_least_two_comparable_campaigns():
    r = one([prog("ALONE", conv_rate=0.9, cpql_mature=100.0)], campaign_id="ALONE")
    assert r["verdict"] == "Hold" and any("comparable" in x for x in r["reasons"])


# ---- Too early and evidence ---------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("over,needle", [(dict(days_running=13), "days"), (dict(qualified=29), "qualified leads"), (dict(mature_qualified=29), "mature qualified")])
def test_each_evidence_threshold_blocks_a_verdict_and_names_what_is_missing(over, needle):
    r = one([prog(**over)])
    assert r["verdict"] == "Too early" and needle in r["confidence"]


def test_enough_evidence_is_reported_with_the_count():
    assert "40 mature qualified" in one([prog()])["confidence"] and one([prog()])["confidence"].startswith("Enough")


def test_below_the_floor_the_page_and_cost_flags_still_show():
    r = one([prog(mature_qualified=27, landing_drop_off=0.67, landing_load=4.8, cpql_ratio=1.5)])
    assert r["verdict"] == "Too early" and any("Fix landing page" in f for f in r["flags"]) and any("worsening" in f for f in r["flags"])


# ---- Flags ----------------------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("drop,load,flagged", [(0.51, 2.0, True), (0.5, 2.0, False), (0.2, 4.1, True), (0.2, 4.0, False), (None, None, False)])
def test_landing_page_flag_needs_more_than_half_dropping_off_or_more_than_four_seconds(drop, load, flagged):
    r = one([prog(landing_drop_off=drop, landing_load=load)])
    assert any("Fix landing page" in f for f in r["flags"]) is flagged
    assert r["verdict"] != "Refresh" or not flagged                                      # a page problem never turns into a replace-the-ad instruction


@pytest.mark.parametrize("vs,flagged", [(-0.5, True), (-0.4999, False), (None, False), (0.3, False)])
def test_weak_ad_flag_is_fifty_percent_below_the_campaign_median_and_skipped_when_unavailable(vs, flagged):
    r = one([prog()], ads=[ad(ad_id="AD-3", vs_median=vs)])
    assert any("Creative review" in f and "AD-3" in f for f in r["flags"]) is flagged
    assert r["verdict"] != "Refresh"                                                      # a weak ad is a flag beside the verdict, not a verdict


@pytest.mark.parametrize("spend,paid,flagged", [(50_001, 0, True), (50_000, 0, False), (90_000, 1, False)])
def test_program_overspend_alert_is_spend_above_the_limit_with_no_paid_customer_of_any_age(spend, paid, flagged):
    r = one([prog(spend_to_date=spend, paid_any=paid)])
    assert any("Overspend alert" in f for f in r["flags"]) is flagged


def test_overspend_alert_shows_even_while_too_early_and_never_pauses_by_itself():
    r = one([prog(days_running=20, qualified=22, mature_qualified=0, spend_to_date=60_000, paid_any=0)])
    assert r["verdict"] == "Too early" and any("Overspend alert" in f for f in r["flags"])


# ---- Workshops ------------------------------------------------------------------------------------------------------------------------------------------------

def ws(campaign_id="W", **over):
    row = dict(campaign_id=campaign_id, name=campaign_id, days_running=30, spend=100_000.0, qualified=40, paid_seats=30, revenue=119_970.0, cost_per_seat=3333.0,
               revenue_ratio=1.2, followup_buyers=10, followup_converted=2, followup_rate=0.2, landing_drop_off=0.3, landing_load=2.0)
    row.update(over)
    return row


def wone(row, adsets=(), ads=()):
    return rca.workshop_verdicts([row], list(adsets), list(ads), CFG)[0]


@pytest.mark.parametrize("ratio,verdict", [(0.999, "Pause"), (1.0, "Hold"), (0.0, "Pause"), (1.7, "Hold")])
def test_a_workshop_is_paused_below_one_rupee_collected_per_rupee_of_ad_spend(ratio, verdict):
    assert wone(ws(revenue_ratio=ratio))["verdict"] == verdict


def test_workshop_pause_reason_states_what_the_figure_covers():
    r = wone(ws(revenue_ratio=0.53, spend=197_046.0, revenue=103_974.0))
    assert any("0.53" in x and "advertising only" in x and "delivery costs" in x for x in r["reasons"])


@pytest.mark.parametrize("over", [dict(days_running=13), dict(qualified=29)])
def test_workshop_needs_fourteen_days_and_thirty_qualified_leads_before_a_financial_verdict(over):
    r = wone(ws(revenue_ratio=0.1, **over))
    assert r["verdict"] == "Too early" and r["confidence"].startswith("Too early")


def test_workshop_refresh_trigger_applies_but_pause_comes_first():
    assert wone(ws(revenue_ratio=1.5), [adset("W", frequency=3.2)])["verdict"] == "Refresh"
    assert wone(ws(revenue_ratio=0.4), [adset("W", frequency=3.2)])["verdict"] == "Pause"


@pytest.mark.parametrize("spend,seats,flagged", [(4_000.0, 0, True), (3_999.0, 0, False), (50_000.0, 2, False)])
def test_workshop_overspend_alert_is_spend_above_3999_with_no_paid_seat(spend, seats, flagged):
    r = wone(ws(spend=spend, paid_seats=seats, revenue=seats * 3999.0, revenue_ratio=seats * 3999.0 / spend))
    assert any("Overspend alert" in f for f in r["flags"]) is flagged


def test_downstream_program_purchases_never_change_the_workshop_verdict():
    low = wone(ws(revenue_ratio=0.5, followup_converted=0, followup_rate=0.0))
    high = wone(ws(revenue_ratio=0.5, followup_converted=9, followup_rate=0.9))
    assert low["verdict"] == high["verdict"] == "Pause"
