import pandas as pd
import streamlit as st

import data
import fmt
import ui
from views.common import header, pick, section

STAGE = {"lead": "Form filled", "review": "Under review", "qualified": "Qualified", "conveyed": "Qualification conveyed", "discovery_set": "Discovery call scheduled",
         "discovery_attended": "Discovery call completed", "ambition_interview": "Ambition call", "architect_session": "Architect call", "signed": "Conversion",
         "rejected": "Rejected", "nurture": "Moved to nurture"}
SOURCE = {"paid_ads": "Paid ads", "brochure": "Brochure", "organic": "Organic"}
UTM = {"instagram": "Instagram", "meta": "Meta"}
TRAFFIC = {"instagram": "Instagram", "facebook": "Facebook", "google": "Google", "direct": "Direct"}
STATUSES = ["All", "In progress", "Signed up", "Rejected", "Nurture"]
SOURCES = ["All", "Paid ads", "Brochure", "Organic"]
SHOWN = 200                    # rows drawn at once; a table of thousands of leads is slow and unreadable


def _squash(text):
    return str(text).lower().replace(" ", "")


def apply_filters(df, status="All", source="All", city="All", grade="All", stage="All", search=""):
    """Rows of the lead list that satisfy every filter ("All" and an empty search mean no filter). Search matches the lead id, student, parent or phone,
    ignoring case and spaces. The input frame is not changed."""
    keep = pd.Series(True, index=df.index)
    if status != "All":
        keep &= df["status"] == status
    if source != "All":
        keep &= df["source_lead"].map(SOURCE) == source
    if city != "All":
        keep &= df["city"] == city
    if grade != "All":
        keep &= df["grade"].astype(str) == grade
    if stage != "All":
        keep &= df["furthest_stage"].map(STAGE) == stage
    needle = _squash(search)
    if needle:
        haystack = df["lead_id"].map(_squash) + df["student_name"].map(_squash) + df["parent_name"].map(_squash) + df["phone"].map(_squash)
        keep &= haystack.str.contains(needle, regex=False)
    return df[keep]


def _choice(label, options, key, container):
    """A selectbox whose options come from the data; a remembered choice that is no longer an option (the timeline changed) falls back to All."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = "All"
    return container.selectbox(label, options, key=key)


def _when(value):
    return fmt.DASH if fmt.missing(value) else f"{pd.Timestamp(value):%d %b %Y, %H:%M}"


def _detail(d, lead_id, end):
    st.caption(f"{lead_id} · {d['status']}. Furthest stage: {STAGE.get(d['furthest_stage'], fmt.DASH)}.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Contact and profile**")
        st.markdown(ui.facts([("Student", d["student_name"]), ("Parent", d["parent_name"]), ("Phone", d["phone"]), ("Grade", d["grade"]), ("School", d["school"]),
                              ("City", d["city"]), ("Created", _when(d["created_at"]))]), unsafe_allow_html=True)
        st.markdown("**Source**")
        st.markdown(ui.facts([("Source lead", SOURCE.get(d["source_lead"])), ("UTM source", UTM.get(d["utm_source"])), ("Traffic source", TRAFFIC.get(d["traffic_source"]))]),
                    unsafe_allow_html=True)
        st.markdown("**Campaign**")
        st.markdown(ui.facts([("Campaign", d["campaign_name"]), ("Ad set", d["ad_set_name"]), ("Asset", d["asset_name"])]), unsafe_allow_html=True)
    with right:
        st.markdown("**Journey**")
        steps = data.query("funnel", "lead_timeline", end, end, lead_id=lead_id).to_dict("records")
        st.markdown(ui.table(steps, [("stage", "Stage", STAGE.get), ("reached_at", "Reached", _when),
                                     ("days_since_previous", "Days since the stage before", lambda v: fmt.DASH if fmt.missing(v) else f"{v:.1f}")]), unsafe_allow_html=True)
        st.markdown("**Money**")
        money = data.query("funnel", "lead_money", end, end, lead_id=lead_id).to_dict("records")
        if money:
            st.markdown(ui.table(money, [("item", "Item", None), ("reference", "Reference", None), ("amount", "Amount", fmt.inr),
                                         ("on_date", "Date", fmt.date), ("state", "State", None)]), unsafe_allow_html=True)
        else:
            st.markdown('<div class="gt-empty">No workshop seat, enrollment or invoice for this lead.</div>', unsafe_allow_html=True)


def open_lead(lead_id, end):
    """The lead in a dialog, as the student dashboard opens a student: everything known about them, and closing it returns to the table."""
    detail = data.query("funnel", "lead_detail", end, end, lead_id=lead_id)
    if detail.empty:
        @st.dialog("Lead not found", on_dismiss="rerun")
        def missing():
            st.info(f"No lead with the id {lead_id}.")
        missing()
        return
    d = detail.iloc[0]

    @st.dialog(f"{d['student_name']} · {lead_id}", width="large", on_dismiss="rerun")
    def body():
        _detail(d, lead_id, end)
    body()


def page():
    start, end = header("Leads", "Every lead created in the selected period, as ClickUp records it. Names, phone numbers and schools are generated. Click any cell in a row to open the lead.")
    leads = data.query("funnel", "lead_list", start, end)
    total = len(leads)
    first = st.columns([2, 1, 1])
    first[0].text_input("Search", key="ld_search", placeholder="Lead id, student, parent or phone")
    status = _choice("Status", STATUSES, "ld_status", first[1])
    source = _choice("Source lead", SOURCES, "ld_source", first[2])
    second = st.columns(3)
    cities = ["All"] + (sorted(leads["city"].dropna().unique()) if total else [])
    grades = ["All"] + ([str(g) for g in sorted(leads["grade"].dropna().astype(int).unique())] if total else [])
    stages = ["All"] + ([STAGE[s] for s in STAGE if s in set(leads["furthest_stage"].dropna())] if total else [])
    city = _choice("City", cities, "ld_city", second[0])
    grade = _choice("Grade", grades, "ld_grade", second[1])
    stage = _choice("Furthest stage", stages, "ld_stage", second[2])

    matching = apply_filters(leads, status, source, city, grade, stage, st.session_state.get("ld_search", "")) if total else leads
    section("Leads")
    selected = st.session_state.get("ld_open")
    if matching.empty:
        st.info("No leads match these filters in this period.")
    else:
        shown = matching.head(SHOWN).reset_index(drop=True)
        st.caption(f"Showing {len(shown):,} of {len(matching):,} matching leads "
                   f"({total:,} created in the period), newest first.")
        table = pd.DataFrame({"Lead": shown["lead_id"], "Student": shown["student_name"], "Parent": shown["parent_name"], "Phone": shown["phone"], "Grade": shown["grade"],
                              "School": shown["school"], "City": shown["city"], "Source lead": shown["source_lead"].map(SOURCE),
                              "Created": shown["created_at"].map(fmt.date),
                              "Furthest stage": shown["furthest_stage"].map(lambda s: STAGE.get(s, fmt.DASH)), "Status": shown["status"]})
        picked = pick(table, shown["lead_id"], "leads_table", 760)
        st.caption("Click any cell in a row to open the lead: profile, source, campaign, journey and money.")
        selected = picked or selected
    if selected:
        open_lead(selected, end)
