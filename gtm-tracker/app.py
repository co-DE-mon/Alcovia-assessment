"""GTM tracker dashboard (dummy data). Run from gtm-tracker/:  streamlit run app.py"""
import streamlit as st

import nav
import ui
from views import campaigns, definitions, funnel, leads, overview, rca, revenue

st.set_page_config(page_title="GTM tracker · Alcovia (dummy data)", page_icon=":material/monitoring:", layout="wide", initial_sidebar_state="auto")
st.markdown(ui.CSS, unsafe_allow_html=True)

nav.PAGES.update({
    "overview": st.Page(overview.page, title="Overview", icon=":material/dashboard:", default=True),
    "revenue": st.Page(revenue.page, title="Revenue", icon=":material/payments:", url_path="revenue"),
    "funnel": st.Page(funnel.page, title="Funnel", icon=":material/filter_alt:", url_path="funnel"),
    "campaigns": st.Page(campaigns.page, title="Campaigns", icon=":material/campaign:", url_path="campaigns"),
    "rca": st.Page(rca.page, title="Root cause analysis", icon=":material/troubleshoot:", url_path="rca"),
    "leads": st.Page(leads.page, title="Leads", icon=":material/groups:", url_path="leads"),
    "definitions": st.Page(definitions.page, title="Definitions", icon=":material/menu_book:", url_path="definitions"),
})
st.navigation(list(nav.PAGES.values())).run()
