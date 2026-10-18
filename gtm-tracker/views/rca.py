import pandas as pd
import streamlit as st

import data
import fmt
import ui
from views import campaigns
from views.common import header, pick, section, tiles

ORDER = ["Scale", "Hold", "Refresh", "Pause", "Too early"]


def _campaign(table, key):
    """A table of campaigns where clicking a row opens that campaign's ads (the page opens it on the rerun)."""
    camp = pick(table, table["Campaign"], key)
    if camp:
        st.session_state["cp_campaign"] = camp
        st.rerun()


def page():
    start, end = header("Root cause analysis", "Which campaigns to scale, hold, refresh or pause, with the reasons, the flags and how much evidence stands behind each.")
    campaigns.open_pending(start, end)
    cfg = data.config()
    r = cfg["rca"]
    result = data.assess(start, end)
    verdicts = result["verdicts"]
    counts = {v: sum(1 for x in verdicts if x["verdict"] == v) for v in ORDER}
    tiles([(v, str(counts[v]), "campaigns", None) for v in ORDER])

    section("Program campaigns", f"Program verdict: {r['lookback_days']}-day lookback ending {end:%d %b %Y}. Only payments and outcomes known by that date are counted, "
                                 f"so the start of the timeline does not change it. Leads at least {r['mature_after_days']} days old are mature.")
    program = [v for v in verdicts if v["kind"] == "program"]
    st.markdown(ui.verdict_table(program), unsafe_allow_html=True)
    m = result["medians"]
    st.caption("Peer medians (program campaigns with enough mature evidence): " + (f"qualified-to-paid conversion {m['conv'] * 100:.1f}%, cost per qualified lead {fmt.inr(m['cpql'])}, "
               f"across {m['n']} campaigns. Scale needs a campaign to beat both." if m else "fewer than two campaigns qualify, so Scale is unavailable."))
    inputs = result["program_inputs"]
    st.markdown("**Numbers behind the program verdicts**")
    table = pd.DataFrame({"Campaign": [x["campaign_id"] for x in inputs], "Days running": [fmt.num(x["days_running"]) for x in inputs],
                          "Qualified leads": [fmt.num(x["qualified"]) for x in inputs], "Mature qualified": [fmt.num(x["mature_qualified"]) for x in inputs],
                          "Awaiting conversion": [fmt.num(x["leads"] - x["mature_leads"]) for x in inputs], "Paid full program": [fmt.num(x["mature_paid_program"]) for x in inputs],
                          "Paid trial": [fmt.num(x["mature_paid_trial"]) for x in inputs], "Qualified to paid": [fmt.pct(x["conv_rate"]) for x in inputs],
                          "Cost per qualified lead": [fmt.inr(x["cpql_mature"]) for x in inputs], "Recent cost per qualified lead": [fmt.inr(x["cpql_recent"]) for x in inputs],
                          "Cost per full-program sign-up": [fmt.inr(x["cost_per_paid_program"]) for x in inputs]})
    st.caption("Click a campaign to see its ads.")
    _campaign(table, "rca_program")
    st.caption(f"Awaiting conversion: leads from the last {r['mature_after_days']} days, too young to have converted yet. They count toward recent cost, not toward conversion. "
               f"The {fmt.inr(r['pause_cost_per_paid_program'])} ceiling is a provisional share of the full-program fee, to validate against real margins.")

    section("Workshop campaigns", "Workshop verdict: the selected period. Judged on collected revenue against ad spend, advertising only.")
    workshop = [v for v in verdicts if v["kind"] == "workshop"]
    st.markdown(ui.verdict_table(workshop), unsafe_allow_html=True)
    w_inputs = result["workshop_inputs"]
    st.markdown("**Numbers behind the workshop verdicts**")
    table = pd.DataFrame({"Campaign": [x["campaign_id"] for x in w_inputs], "Days running": [fmt.num(x["days_running"]) for x in w_inputs],
                          "Qualified leads": [fmt.num(x["qualified"]) for x in w_inputs], "Ad spend": [fmt.inr(x["spend"]) for x in w_inputs],
                          "Paid seats": [fmt.num(x["paid_seats"]) for x in w_inputs], "Cost per seat": [fmt.inr(x["cost_per_seat"]) for x in w_inputs],
                          "Collected revenue": [fmt.inr(x["revenue"]) for x in w_inputs], "Revenue per rupee of ads": [fmt.dec(x["revenue_ratio"]) for x in w_inputs]})
    _campaign(table, "rca_workshop")
    st.caption("Refunds are assumed to be ₹0 in this demo. Net revenue therefore equals recorded collected revenue.")
    st.markdown("**Later program purchases (separate from the verdict)**")
    table = pd.DataFrame({"Campaign": [x["campaign_id"] for x in w_inputs], f"Buyers with a complete {r['followup_days']}-day follow-up": [fmt.num(x["followup_buyers"]) for x in w_inputs],
                          "Bought the program in time": [fmt.num(x["followup_converted"]) for x in w_inputs], "Rate": [fmt.pct(x["followup_rate"]) for x in w_inputs]})
    _campaign(table, "rca_followup")
    st.caption("These program purchases are synthetic, added to the dummy data to show the metric. They are counted once in company revenue and do not change the workshop verdict.")

    with st.expander("Creative signals behind Refresh and the weak-ad flag"):
        adsets = pd.DataFrame(result["adset_signals"])
        if not adsets.empty:
            st.markdown("**Ad sets: frequency and click-through, latest 14 days against the 14 before**")
            adsets = adsets.reset_index(drop=True)
            table = pd.DataFrame({"Ad set": adsets["ad_set_id"], "Frequency": adsets["frequency"].map(fmt.dec),
                                  "Clicks, latest 14 days": adsets["clicks_recent"].map(fmt.num), "Impressions, latest 14 days": adsets["impressions_recent"].map(fmt.num),
                                  "Clicks, 14 days before": adsets["clicks_prior"].map(fmt.num), "Impressions, 14 days before": adsets["impressions_prior"].map(fmt.num),
                                  "CTR change": adsets["ctr_change"].map(fmt.change)})
            adset = pick(table, adsets["ad_set_id"], "rca_adsets")
            if adset:
                st.session_state["cp_adset"] = adset
                st.rerun()
        ads = pd.DataFrame(result["ad_signals"])
        if not ads.empty:
            weak = ads[ads["vs_median"].notna()].sort_values("vs_median").head(8)
            st.markdown("**Ads furthest below their campaign's median**")
            weak = weak.reset_index(drop=True)
            table = pd.DataFrame({"Ad": weak["ad_id"], "Campaign": weak["campaign_id"], "CTR": weak["ctr"].map(lambda v: fmt.pct(v, 2)),
                                  "Campaign median CTR": weak["median_ctr"].map(lambda v: fmt.pct(v, 2)), "Against median": weak["vs_median"].map(lambda v: fmt.change(v, 0))})
            ad = pick(table, weak["ad_id"], "rca_weak_ads")
            if ad:
                st.session_state["cp_ad"] = ad
                st.rerun()
