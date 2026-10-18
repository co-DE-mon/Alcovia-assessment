import pandas as pd
import streamlit as st

import data
import fmt
from views import charts, leads
from views.common import header, pick, section

KIND_LABEL = {"program": "Program", "workshop": "Workshop"}


def open_adset(ad_set_id, start, end):
    """One ad set in a dialog: its daily frequency and its ads (clicking an ad sets cp_ad; the page opens it)."""
    daily = data.query("campaigns", "adset_daily_frequency", start, end, ad_set_id=ad_set_id)
    rows = data.query("campaigns", "adset_ads", start, end, ad_set_id=ad_set_id)

    @st.dialog(ad_set_id, width="large", on_dismiss="rerun")
    def body():
        st.caption(f"{start:%d %b} to {end:%d %b %Y}. Frequency is the average times a person has seen the ads that day; 3 or more means the ad set needs a change.")
        if daily.empty:
            st.info("No data for this ad set in this period.")
        else:
            daily["Ad set"] = ad_set_id
            charts.lines(daily, "day", "frequency", "Ad set", fmt=".1f")
        st.markdown("**Ads in this ad set.** Click one to open it.")
        table = pd.DataFrame({"Ad": rows["ad_id"], "Asset": rows["asset_name"], "Spend": rows["spend"].map(fmt.inr), "Impressions": rows["impressions"].map(fmt.num),
                              "Clicks": rows["clicks"].map(fmt.num), "CTR": rows["ctr"].map(lambda v: fmt.pct(v, 2))})
        ad = pick(table, rows["ad_id"], "adset_ads_table", 300)
        if ad:
            st.session_state["cp_ad"] = ad
            st.rerun()
    body()


def open_campaign(campaign_id, name, start, end):
    """The ads behind one campaign row, in a dialog."""
    rows = data.query("campaigns", "campaign_ads", start, end, campaign_id=campaign_id)

    @st.dialog(campaign_id, width="large", on_dismiss="rerun")
    def body():
        st.caption(f"{name}. {len(rows):,} ads with activity, {start:%d %b} to {end:%d %b %Y}, biggest spend first.")
        table = pd.DataFrame({"Ad": rows["ad_id"], "Asset": rows["asset_name"], "Ad set": rows["ad_set_id"], "Spend": rows["spend"].map(fmt.inr),
                              "Impressions": rows["impressions"].map(fmt.num), "Clicks": rows["clicks"].map(fmt.num), "CTR": rows["ctr"].map(lambda v: fmt.pct(v, 2))})
        st.caption("Click an ad to see its daily CTR and the leads it brought in.")
        ad = pick(table, rows["ad_id"], "campaign_ads_table", 460)
        if ad:
            st.session_state["cp_ad"] = ad      # a dialog cannot open another: the page opens the ad on the rerun
            st.rerun()
    body()


def open_day(campaign_id, day, start, end):
    """The ads behind one campaign-day of the CTR table, in a dialog."""
    rows = data.query("campaigns", "campaign_day_ads", start, end, campaign_id=campaign_id, day=day)

    @st.dialog(f"{campaign_id} · {pd.Timestamp(day):%d %b %Y}", width="large", on_dismiss="rerun")
    def body():
        spend, impressions, clicks = rows["spend"].sum(), rows["impressions"].sum(), rows["clicks"].sum()
        st.caption(f"{len(rows):,} ads, spend {fmt.inr(spend)}, CTR {fmt.pct(clicks / impressions if impressions else None, 2)}. Click an ad to open it.")
        table = pd.DataFrame({"Ad": rows["ad_id"], "Asset": rows["asset_name"], "Ad set": rows["ad_set_id"], "Spend": rows["spend"].map(fmt.inr),
                              "Impressions": rows["impressions"].map(fmt.num), "Clicks": rows["clicks"].map(fmt.num), "CTR": rows["ctr"].map(lambda v: fmt.pct(v, 2))})
        ad = pick(table, rows["ad_id"], "day_ads_table", 460)
        if ad:
            st.session_state["cp_ad"] = ad
            st.rerun()
    body()


def open_ad(ad_id, start, end):
    """One ad in a dialog: its daily CTR, what its leads did, and the leads themselves (clicking one sets cp_lead; the page opens it)."""
    daily = data.query("campaigns", "ad_daily_ctr", start, end, ad_id=ad_id)
    got = data.query("campaigns", "ad_leads", start, end, ad_id=ad_id)

    @st.dialog(ad_id, width="large", on_dismiss="rerun")
    def body():
        spend, clicks, impressions = daily["spend"].sum(), daily["clicks"].sum(), daily["impressions"].sum()
        qualified, signed = int(got["qualified"].sum()) if len(got) else 0, int(got["signed"].sum()) if len(got) else 0
        st.caption(f"{start:%d %b} to {end:%d %b %Y}. Spend {fmt.inr(spend)}, CTR {fmt.pct(clicks / impressions if impressions else None, 2)}, "
                   f"{len(got):,} leads, {qualified:,} qualified, {signed:,} signed up, "
                   f"{fmt.inr(spend / qualified) if qualified else '-'} per qualified lead.")
        if daily.empty:
            st.info("No ad activity in this period.")
        else:
            daily["Ad"] = ad_id
            charts.lines(daily, "day", "ctr", "Ad", fmt=".1%")
        st.markdown("**Leads from this ad.** Click one to open it.")
        if got.empty:
            st.info("No leads came from this ad in this period.")
            return
        table = pd.DataFrame({"Lead": got["lead_id"], "Student": got["student_name"], "City": got["city"], "Created": got["created_at"].map(fmt.date),
                              "Qualified": got["qualified"].map({True: "Yes", False: "No"}), "Signed up": got["signed"].map({True: "Yes", False: "No"})})
        lead = pick(table, got["lead_id"], "ad_leads_table", 300)
        if lead:
            st.session_state["cp_lead"] = lead
            st.rerun()
    body()


def open_pending(start, end):
    """Open the dialog a click in a dialog asked for (a dialog cannot open another, so the click set a flag and reran). Shared with the root cause page."""
    lead, ad = st.session_state.pop("cp_lead", None), st.session_state.pop("cp_ad", None)
    adset, camp = st.session_state.pop("cp_adset", None), st.session_state.pop("cp_campaign", None)
    if lead:
        leads.open_lead(lead, end)
    elif ad:
        open_ad(ad, start, end)
    elif adset:
        open_adset(adset, start, end)
    elif camp:
        names = dict(data.query("campaigns", "campaign_summary", start, end)[["campaign_id", "name"]].values)
        open_campaign(camp, names.get(camp, ""), start, end)


def page():
    start, end = header("Campaigns", "Spend and click-through for the program and workshop campaigns, and which assets and pages need attention.")

    open_pending(start, end)

    section("Campaign performance")
    summary = data.query("campaigns", "campaign_summary", start, end)
    if summary.empty:
        st.info("No ad activity in this period.")
        return
    summary["Campaign"] = summary["campaign_id"].map(charts.short)
    charts.hbars(summary, "Campaign", "spend", color="kind", domain=charts.KIND_DOMAIN, fmt="~s")
    st.caption("Spend in rupees. Blue is a program campaign, orange a workshop campaign.")
    st.caption("Click a campaign to see its ads.")
    summary = summary.reset_index(drop=True)
    names = dict(zip(summary["campaign_id"], summary["name"]))
    table = pd.DataFrame({"Campaign": summary["campaign_id"], "Name": summary["name"], "Kind": summary["kind"].map(KIND_LABEL), "Spend": summary["spend"].map(fmt.inr),
                          "Impressions": summary["impressions"].map(fmt.num), "Clicks": summary["clicks"].map(fmt.num), "CTR": summary["ctr"].map(lambda v: fmt.pct(v, 2))})
    camp = pick(table, summary["campaign_id"], "campaign_perf_table")
    if camp:
        open_campaign(camp, names.get(camp, ""), start, end)

    section("CTR by day", "Click-through rate for each campaign.")
    daily = data.query("campaigns", "ctr_daily", start, end)
    daily["Campaign"] = daily["campaign_id"].map(charts.short)
    charts.lines(daily, "day", "ctr", "Campaign")
    st.caption("Click a day to see that campaign's ads.")
    daily = daily.reset_index(drop=True)
    table = pd.DataFrame({"Campaign": daily["Campaign"], "Day": daily["day"].map(fmt.date), "Spend": daily["spend"].map(fmt.inr),
                          "CTR": daily["ctr"].map(lambda v: fmt.pct(v, 2))})
    row = pick(table, pd.Series(daily.index), "ctr_day_table", 420)
    if row is not None:
        open_day(daily.loc[row, "campaign_id"], daily.loc[row, "day"], start, end)

    assets = data.query("campaigns", "asset_ctr", start, end).dropna(subset=["ctr"]).sort_values("ctr")
    def _assets(rows, key):
        rows = rows.reset_index(drop=True)
        table = pd.DataFrame({"Ad": rows["ad_id"], "Asset": rows["asset_name"], "Campaign": rows["campaign_id"], "CTR": rows["ctr"].map(lambda v: fmt.pct(v, 2))})
        ad = pick(table, rows["ad_id"], key)
        if ad:
            st.session_state["cp_ad"] = ad
            st.rerun()
    best, worst = st.columns(2)
    with best:
        section("Highest CTR assets", "Keep these running.")
        _assets(assets.tail(5).iloc[::-1], "assets_best")
    with worst:
        section("Lowest CTR assets", "Refresh these first.")
        _assets(assets.head(5), "assets_worst")

    section("Ad-set frequency", "Average times a person has seen the ad, on the last day of the period. 3 or more means the ad set needs a change.")
    st.caption("The frequency and the status do not change with the timeline's start day: they describe the last day. Only the peak column covers the whole period.")
    freq = data.query("campaigns", "adset_frequency", start, end).sort_values("frequency", ascending=False)
    freq = freq.reset_index(drop=True)
    st.caption("Click an ad set to see its daily frequency and its ads.")
    table = pd.DataFrame({"Ad set": freq["ad_set_id"], "Campaign": freq["campaign_id"], "Frequency": freq["frequency"].map(lambda v: f"{v:.2f}"),
                          "Peak in period": freq["peak_frequency"].map(lambda v: f"{v:.2f}"), "Status": freq["needs_change"].map(lambda n: "Needs a change" if n else "Fine")})
    adset = pick(table, freq["ad_set_id"], "freq_table")
    if adset:
        open_adset(adset, start, end)

    section("Landing page health", "Share of visitors who leave straight away, and how long the page takes to load.")
    lp = data.query("campaigns", "landing_health", start, end).sort_values("drop_off_rate", ascending=False).reset_index(drop=True)
    st.caption("Click a campaign to see its ads.")
    table = pd.DataFrame({"Campaign": lp["campaign_id"], "Sessions": lp["sessions"].map(fmt.num), "Drop-off rate": lp["drop_off_rate"].map(fmt.pct),
                          "Load time": lp["avg_load_seconds"].map(lambda v: f"{v:.1f} s")})
    camp = pick(table, lp["campaign_id"], "landing_table")
    if camp:
        open_campaign(camp, names.get(camp, ""), start, end)
