import pandas as pd
import streamlit as st

import data
import fmt
from views import charts, leads
from views.common import header, num, pick, section, tiles

DIMENSIONS = {"City": "city", "Grade": "grade", "School": "school", "Traffic source": "traffic_source", "Source lead": "source_lead", "UTM source": "utm_source"}
STAGE = {"lead": "Leads", "qualified": "Qualified", "discovery_set": "Discovery call set", "discovery_attended": "Discovery call attended",
         "ambition_interview": "Ambition interview", "architect_session": "Architect session", "signed": "Signed up"}


def open_stage(stage, start, end):
    """The leads that reached one stage, in a dialog. Clicking a lead sets fn_lead and reruns; the page opens the lead (a dialog cannot open another)."""
    rows = data.query("funnel", "stage_leads", start, end, stage=stage)

    @st.dialog(STAGE[stage], width="large", on_dismiss="rerun")
    def body():
        st.caption(f"{len(rows):,} leads created {start:%d %b} to {end:%d %b %Y} reached this stage. Click a lead to open it.")
        table = pd.DataFrame({"Lead": rows["lead_id"], "Student": rows["student_name"], "Parent": rows["parent_name"], "City": rows["city"],
                              "Created": rows["created_at"].map(fmt.date), "Reached": rows["reached_at"].map(fmt.date)})
        lead = pick(table, rows["lead_id"], "stage_leads_table", 460)
        if lead:
            st.session_state["fn_lead"] = lead
            st.rerun()
    body()


def open_campaign(campaign_id, start, end):
    """The leads a campaign brought in the period, in a dialog."""
    everyone = data.query("funnel", "lead_list", start, end)
    open_leads(campaign_id, everyone[everyone["campaign_id"] == campaign_id], start, end)


def open_group(label, column, value, start, end):
    """The leads in one row of the attribute breakdown, in a dialog. A missing attribute is the group Unknown (utm_source: Not from an ad), as in by_dimension."""
    everyone = data.query("funnel", "lead_list", start, end)
    have = everyone[column].astype("string") if column != "grade" else everyone[column].map(lambda g: None if g != g else str(int(g))).astype("string")
    unknown = "Not from an ad" if column == "utm_source" else "Unknown"
    open_leads(f"{label}: {value}", everyone[have.fillna(unknown) == value], start, end)


def open_leads(title, rows, start, end):
    """A dialog listing leads. Clicking a lead sets fn_lead and reruns; the page opens the lead (a dialog cannot open another)."""
    rows = rows.reset_index(drop=True)

    @st.dialog(title, width="large", on_dismiss="rerun")
    def body():
        st.caption(f"{len(rows):,} leads created {start:%d %b} to {end:%d %b %Y}, newest first. Click a lead to open it.")
        table = pd.DataFrame({"Lead": rows["lead_id"], "Student": rows["student_name"], "City": rows["city"], "Grade": rows["grade"],
                              "Created": rows["created_at"].map(fmt.date),
                              "Furthest stage": rows["furthest_stage"].map(lambda x: leads.STAGE.get(x, "-")), "Status": rows["status"]})
        lead = pick(table, rows["lead_id"], "campaign_leads_table", 460)
        if lead:
            st.session_state["fn_lead"] = lead
            st.rerun()
    body()


def page():
    start, end = header("Funnel", "Meta-ad leads from first contact to signing, for the leads created in the selected period.")

    lead = st.session_state.pop("fn_lead", None)
    if lead:
        leads.open_lead(lead, end)

    section("Top metrics")
    h = data.query("funnel", "headline", start, end).iloc[0]
    tiles([("Cost per qualified lead", fmt.inr(num(h["cost_per_qualified_lead"])), "paid spend / qualified paid leads", None),
           ("Program conversion", fmt.pct(num(h["program_conversion_rate"])), "paid program or trial buyers / leads created in the period", None),
           ("Organic leads", fmt.num(num(h["organic_leads"])), "no campaign attached", None),
           ("Average lead journey", "–" if num(h["avg_journey_days"]) is None else f"{h['avg_journey_days']:.1f} days", "first contact to last stage", None)])

    section("Lead journey", "How many leads reached each stage.")
    stages = data.query("funnel", "stage_counts", start, end)
    top = stages["leads"].iloc[0] if len(stages) else 0
    stages["Stage"] = stages["stage"].map(STAGE)
    stages["label"] = [f"{n:,}" + (f" ({n / top:.0%})" if top else "") for n in stages["leads"]]
    if top:
        charts.hbars(stages, "Stage", "leads", text="label")
        st.caption("Click a stage to see its leads.")
        stage = pick(stages[["Stage", "leads"]], stages["stage"], "stage_table")
        if stage:
            open_stage(stage, start, end)
    else:
        st.info("No leads were created in this period.")

    ex = data.query("funnel", "exits", start, end).iloc[0]
    tiles([("Rejected at review", fmt.num(num(ex["rejected"])), "did not meet the qualification criteria", None),
           ("Moved to nurture", fmt.num(num(ex["nurture"])), "attended the discovery call, not taken further", None)])

    sd = data.query("funnel", "show_up_and_drop", start, end).iloc[0]
    tiles([("Discovery call show-up rate", fmt.pct(num(sd["discovery_show_up_rate"])), f"{fmt.num(sd['discovery_attended'])} attended of {fmt.num(sd['discovery_set'])} calls set", None),
           ("Ambition interview drop-off rate", fmt.pct(num(sd["ambition_drop_off_rate"])),
            f"{fmt.num(sd['ambition_interview'] - sd['architect_session'])} of {fmt.num(sd['ambition_interview'])} interviews did not reach an architect session", None)])

    section("By campaign", "Leads created in the period, and what they cost.")
    camp = data.query("funnel", "by_campaign", start, end)
    if camp.empty:
        st.info("No campaign had leads or spend in this period.")
    else:
        st.caption("Click a campaign to see its leads.")
        table = pd.DataFrame({"Campaign": camp["campaign_id"], "Kind": camp["kind"], "Leads": camp["leads"].map(fmt.num), "Qualified": camp["qualified"].map(fmt.num),
                              "Signed up": camp["signed"].map(fmt.num), "Spend": camp["spend"].map(fmt.inr), "Cost per qualified lead": camp["cost_per_qualified_lead"].map(fmt.inr)})
        campaign = pick(table, camp["campaign_id"], "campaign_table")
        if campaign:
            open_campaign(campaign, start, end)

    section("Breakdown by lead attribute", "Which kinds of leads qualify and sign. Read the lead count first: small groups give noisy rates, and recent leads have not had time to sign.")
    label = st.selectbox("Break down by", list(DIMENSIONS), key="fn_dim")
    rows = data.query("funnel", "by_dimension", start, end)
    rows = rows[rows["dimension"] == DIMENSIONS[label]]
    if rows.empty:
        st.info("No leads were created in this period.")
    else:
        charts.hbars(rows.head(10), "value", "leads")
        if len(rows) > 10:
            st.caption(f"The chart shows the 10 largest of {len(rows)} groups; the table lists all of them.")
        st.caption("Click a row to see its leads.")
        rows = rows.reset_index(drop=True)
        table = pd.DataFrame({label: rows["value"], "Leads": rows["leads"].map(fmt.num), "Qualified": rows["qualified"].map(fmt.num), "Signed up": rows["signed"].map(fmt.num),
                              "Qualified share": rows["qualified_rate"].map(fmt.pct), "Signed-up share": rows["signed_rate"].map(fmt.pct)})
        value = pick(table, rows["value"], "dimension_table")
        if value is not None:
            open_group(label, DIMENSIONS[label], value, start, end)
