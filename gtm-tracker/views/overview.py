import streamlit as st

import data
import nav
import fmt
import ui
from views.common import header, num, section, tiles


def page():
    start, end = header("GTM overview", "Revenue, funnel and campaign health for the selected period.")
    tv = data.query("revenue", "target_vs_actual", start, end).iloc[0]
    section("Revenue", "Target for the period is prorated from the monthly targets.")
    tiles([("Achieved in the period", fmt.inr(num(tv["actual"])), f"against {fmt.inr(num(tv['target']))} target for the period", None)])
    st.markdown(ui.meter(num(tv["actual"]), num(tv["target"])), unsafe_allow_html=True)
    split = data.query("revenue", "signup_split", start, end)
    h = data.query("funnel", "headline", start, end).iloc[0]
    freq = data.query("campaigns", "adset_frequency", start, end)
    verdicts = data.assess(start, end)["verdicts"]
    decided = sum(1 for v in verdicts if v["verdict"] != "Too early")
    pauses = sum(1 for v in verdicts if v["verdict"] == "Pause")

    section("Funnel and campaigns")
    tiles([("Students onboarded", fmt.num(int(split["students"].sum()) if len(split) else 0), "in the period", None),
           ("Cost per qualified lead", fmt.inr(num(h["cost_per_qualified_lead"])), None, None),
           ("Program conversion", fmt.pct(num(h["program_conversion_rate"])), None, None),
           ("Ad sets needing a change", fmt.num(int(freq["needs_change"].sum()) if len(freq) else 0), "frequency 3 or more", None),
           ("Campaigns with a verdict", f"{decided} of {len(verdicts)}", f"{pauses} to pause" if pauses else "none to pause", None)])
    for key, label in [("revenue", "Revenue details"), ("funnel", "Funnel details"), ("campaigns", "Campaign details"), ("rca", "Root cause analysis")]:
        nav.link(key, label)
