"""Campaign decision rules (README.md) applied to the inputs in sql/metrics/rca.sql. Pure functions, no database, no Streamlit.

A verdict is one of Scale, Hold, Refresh, Pause or Too early. Above the evidence floor the order is Pause, then Refresh, then Scale, then Hold.
Flags (landing page, weak ad, overspend, worsening cost, no paid conversions) sit beside the verdict and never replace it. Every threshold comes from config.yaml (rca).
"""
from collections import defaultdict
from statistics import median

import fmt
import metrics

EPS = 1e-9          # a fall of exactly 15% is stored as -0.15000000000000002; the author's boundary is inclusive


def _group(rows):
    out = defaultdict(list)
    for row in rows:
        out[row["campaign_id"]].append(row)
    return out


def _pct(x):
    return f"{abs(x) * 100:.0f}%"


def refresh_reasons(adsets, cfg):
    """Why creative needs a refresh: an ad set at frequency 3 or more, or whose CTR fell by at least the configured share (latest 14 days against the 14 before)."""
    limit, fall = cfg["campaign"]["frequency_change_at"], cfg["rca"]["ctr_decline"]
    reasons = []
    for a in adsets:
        parts = []
        if not fmt.missing(a.get("frequency")) and a["frequency"] >= limit:
            parts.append(f"is at frequency {a['frequency']:.2f} ({limit:g} or more means change it)")
        if not fmt.missing(a.get("ctr_change")) and a["ctr_change"] <= -fall + EPS:
            parts.append(f"has CTR down {_pct(a['ctr_change'])} over the latest 14 days against the 14 before "
                         f"({a['clicks_recent']:,} clicks on {a['impressions_recent']:,} impressions, against {a['clicks_prior']:,} on {a['impressions_prior']:,})")
        if parts:
            reasons.append(f"Creative refresh needed: ad set {a['ad_set_id']} {' and '.join(parts)}")
    return reasons


def common_flags(row, ads, cfg, overspend_limit, spent, has_customer, unit):
    """Flags that never change the verdict: a landing page to fix, weak ads to review, and money spent with nothing to show."""
    r, flags = cfg["rca"], []
    drop, load = row.get("landing_drop_off"), row.get("landing_load")
    if (not fmt.missing(drop) and drop > r["landing_drop_off"]) or (not fmt.missing(load) and load > r["landing_load_seconds"]):
        parts = ([f"{drop * 100:.0f}% drop-off"] if not fmt.missing(drop) else []) + ([f"{load:.1f} s load"] if not fmt.missing(load) else [])
        flags.append(f"Fix landing page: {', '.join(parts)}")
    for a in ads:
        if not fmt.missing(a.get("vs_median")) and a["vs_median"] <= -r["weak_ad_below_median"] + EPS:
            flags.append(f"Creative review: ad {a['ad_id']} ({a['asset_name']}) CTR is {_pct(a['vs_median'])} below its campaign's median ad")
    if not fmt.missing(spent) and spent > overspend_limit and not has_customer:
        flags.append(f"Overspend alert: {fmt.inr(spent)} spent with no {unit}")
    return flags


def decide_program(row, medians, adsets, ads, cfg):
    """One program campaign's verdict, reasons, flags and evidence confidence."""
    r = cfg["rca"]
    days_ok = row["days_running"] >= r["min_days_running"]
    qualified_ok = row["qualified"] >= r["min_qualified_leads"]
    initial = days_ok and qualified_ok
    mature_ok = row["mature_qualified"] >= r["min_qualified_leads"]
    signup = initial and mature_ok
    if signup:
        confidence = f"Enough evidence: {row['mature_qualified']} mature qualified leads"
    elif initial:
        confidence = f"Limited: {row['mature_qualified']} of {r['min_qualified_leads']} mature qualified leads"
    else:
        missing = ([f"{row['days_running']} of {r['min_days_running']} days running"] if not days_ok else []) + \
                  ([f"{row['qualified']} of {r['min_qualified_leads']} qualified leads"] if not qualified_ok else [])
        confidence = f"Too early: {'; '.join(missing)}"

    refresh = refresh_reasons(adsets, cfg)
    worse = not fmt.missing(row.get("cpql_ratio")) and row["cpql_ratio"] > r["worsening_ratio"] + EPS
    cost = row.get("cost_per_paid_program")
    flags = common_flags(row, ads, cfg, r["overspend_program"], row.get("spend_to_date"), row["paid_any"] > 0, "paid customer from any lead")
    if worse:
        flags.append(f"Recent acquisition cost worsening: cost per qualified lead is {(row['cpql_ratio'] - 1) * 100:.0f}% higher on leads from the last {r['mature_after_days']} days")
    if signup and row["mature_paid_program"] == 0:
        flags.append("No paid full-program conversions in the mature cohort: budget review")

    reasons = []
    if signup and not fmt.missing(cost) and cost > r["pause_cost_per_paid_program"]:
        verdict = "Pause"
        reasons.append(f"Mature cost per full-program sign-up {fmt.inr(cost)} is above the {fmt.inr(r['pause_cost_per_paid_program'])} ceiling (provisional)")
        reasons += refresh
    elif refresh:
        verdict, reasons = "Refresh", refresh
    elif not signup:
        verdict = "Too early"
        reasons.append("Not enough evidence for a sign-up-based verdict yet" if initial else "Not enough data for a verdict yet")
    else:
        verdict, reasons = _scale_or_hold(row, medians, worse, cfg)
    label = "Hold: recent acquisition cost worsening" if verdict == "Hold" and worse else verdict
    return dict(campaign_id=row["campaign_id"], name=row["name"], kind="program", verdict=verdict, label=label, reasons=reasons, flags=flags, confidence=confidence)


def _scale_or_hold(row, medians, worse, cfg):
    """Scale when conversion is above and cost per qualified lead below the peer medians, the cost ceiling holds and recent cost is not worsening; otherwise Hold."""
    r = cfg["rca"]
    if medians is None:
        return "Hold", ["Scale needs at least two comparable campaigns with enough evidence to set the medians"]
    fails = []
    if fmt.missing(row.get("conv_rate")) or row["conv_rate"] <= medians["conv"]:
        fails.append(f"Qualified-to-paid conversion {fmt.pct(row.get('conv_rate'))} is not above the peer median {medians['conv'] * 100:.1f}%")
    if fmt.missing(row.get("cpql_mature")) or row["cpql_mature"] >= medians["cpql"]:
        fails.append(f"Cost per qualified lead {fmt.inr(row.get('cpql_mature'))} is not below the peer median {fmt.inr(medians['cpql'])}")
    cost = row.get("cost_per_paid_program")
    if fmt.missing(cost):
        fails.append("No paid full-program customer yet to check the cost ceiling against")
    if worse:
        fails.append("Recent acquisition cost is worsening, which blocks Scale")
    if fails:
        return "Hold", fails
    return "Scale", [f"Qualified-to-paid conversion {row['conv_rate'] * 100:.1f}% is above the peer median {medians['conv'] * 100:.1f}%",
                     f"Cost per qualified lead {fmt.inr(row['cpql_mature'])} is below the peer median {fmt.inr(medians['cpql'])}",
                     f"Mature cost per full-program sign-up {fmt.inr(cost)} is within the {fmt.inr(r['pause_cost_per_paid_program'])} ceiling",
                     f"Recent cost per qualified lead is not more than {(r['worsening_ratio'] - 1) * 100:.0f}% worse than the mature cost"]


def peer_medians(program_rows, cfg):
    """Medians of mature qualified-to-paid conversion and cost per qualified lead over the program campaigns with enough evidence (the campaign being judged is one of them).
    None when fewer than two campaigns qualify: Scale then has no peers to beat."""
    r = cfg["rca"]
    eligible = [p for p in program_rows if p["days_running"] >= r["min_days_running"] and p["qualified"] >= r["min_qualified_leads"]
                and p["mature_qualified"] >= r["min_qualified_leads"] and not fmt.missing(p.get("conv_rate")) and not fmt.missing(p.get("cpql_mature"))]
    if len(eligible) < 2:
        return None
    return dict(conv=median(p["conv_rate"] for p in eligible), cpql=median(p["cpql_mature"] for p in eligible), n=len(eligible))


def program_verdicts(program_rows, medians, adset_rows, ad_rows, cfg):
    """Verdicts for every program campaign. `medians` (from peer_medians) come from the campaigns with enough mature evidence (initial floor and mature floor met)."""
    sets, ads = _group(adset_rows), _group(ad_rows)
    return [decide_program(p, medians, sets[p["campaign_id"]], ads[p["campaign_id"]], cfg) for p in program_rows]


def decide_workshop(row, adsets, ads, cfg):
    """One workshop campaign over the selected period: Pause below the configured revenue-to-ad-spend ratio once there is enough data. Later program purchases are not used."""
    r = cfg["rca"]
    days_ok, qualified_ok = row["days_running"] >= r["min_days_running"], row["qualified"] >= r["min_qualified_leads"]
    eligible = days_ok and qualified_ok
    if eligible:
        confidence = f"Enough evidence: {row['days_running']} days, {row['qualified']} qualified leads"
    else:
        missing = ([f"{row['days_running']} of {r['min_days_running']} days"] if not days_ok else []) + ([f"{row['qualified']} of {r['min_qualified_leads']} qualified leads"] if not qualified_ok else [])
        confidence = f"Too early: {'; '.join(missing)}"
    refresh = refresh_reasons(adsets, cfg)
    ratio = row.get("revenue_ratio")
    flags = common_flags(row, ads, cfg, r["overspend_workshop"], row.get("spend"), row["paid_seats"] > 0, "paid seat")
    if eligible and not fmt.missing(ratio) and ratio < r["workshop_min_revenue_ratio"]:
        verdict = "Pause"
        reasons = [f"Collected {fmt.inr(row['revenue'])} on {fmt.inr(row['spend'])} of ads, {ratio:.2f} per rupee, below {r['workshop_min_revenue_ratio']:.1f}. "
                   "This covers advertising only; delivery costs are not deducted"] + refresh
    elif refresh:
        verdict, reasons = "Refresh", refresh
    elif not eligible:
        verdict, reasons = "Too early", ["Not enough data for a financial verdict yet"]
    else:
        verdict = "Hold"
        reasons = [f"Collected {fmt.inr(row['revenue'])} on {fmt.inr(row['spend'])} of ads, {ratio:.2f} per rupee, at or above {r['workshop_min_revenue_ratio']:.1f}"]
    return dict(campaign_id=row["campaign_id"], name=row["name"], kind="workshop", verdict=verdict, label=verdict, reasons=reasons, flags=flags, confidence=confidence)


def workshop_verdicts(workshop_rows, adset_rows, ad_rows, cfg):
    sets, ads = _group(adset_rows), _group(ad_rows)
    return [decide_workshop(w, sets[w["campaign_id"]], ads[w["campaign_id"]], cfg) for w in workshop_rows]


def assess(con, cfg, start, end):
    """Run the RCA queries and the rules for the period start..end (program verdicts look back rca.lookback_days from end). Returns the verdicts and the inputs behind them."""
    prm = metrics.params(cfg, start, end)
    program = metrics.run(con, "rca", "program_inputs", prm)
    workshop = metrics.run(con, "rca", "workshop_inputs", prm)
    adsets = metrics.run(con, "rca", "adset_signals", prm)
    ads = metrics.run(con, "rca", "ad_signals", prm)
    medians = peer_medians(program, cfg)
    verdicts = program_verdicts(program, medians, adsets, ads, cfg) + workshop_verdicts(workshop, adsets, ads, cfg)
    return dict(verdicts=verdicts, program_inputs=program, workshop_inputs=workshop, adset_signals=adsets, ad_signals=ads, medians=medians)
