"""Student progress dashboard (dummy data). Run from student-tracker/:  streamlit run app.py"""
import streamlit as st

import data
import nav
import ui
from views import cadence, definitions, health, overview, students

st.set_page_config(page_title="Student progress · Alcovia (dummy data)", page_icon=":material/monitoring:", layout="wide", initial_sidebar_state="auto")
st.markdown(ui.CSS, unsafe_allow_html=True)


def daily():
    cadence.page("daily")


def weekly():
    cadence.page("weekly")


def monthly():
    cadence.page("monthly")


def quarterly():
    cadence.page("quarterly")


def roadmaps():
    cadence.page("roadmaps")


nav.PAGES.update({
    "overview": st.Page(overview.page, title="Overview", icon=":material/dashboard:", default=True),
    "daily": st.Page(daily, title="Daily", icon=":material/today:", url_path="daily"),
    "weekly": st.Page(weekly, title="Weekly", icon=":material/date_range:", url_path="weekly"),
    "monthly": st.Page(monthly, title="Monthly", icon=":material/calendar_month:", url_path="monthly"),
    "quarterly": st.Page(quarterly, title="Quarterly", icon=":material/event_repeat:", url_path="quarterly"),
    "roadmaps": st.Page(roadmaps, title="Roadmaps", icon=":material/route:", url_path="roadmaps"),
    "students": st.Page(students.page, title="Students", icon=":material/groups:", url_path="students"),
    "health": st.Page(health.page, title="Data health", icon=":material/vital_signs:", url_path="data-health"),
    "definitions": st.Page(definitions.page, title="Definitions", icon=":material/menu_book:", url_path="definitions"),
})
pg = st.navigation({
    "": [nav.PAGES["overview"]],
    "Cadences": [nav.PAGES[k] for k in ("daily", "weekly", "monthly", "quarterly", "roadmaps")],
    "People": [nav.PAGES["students"]],
    "System": [nav.PAGES["health"], nav.PAGES["definitions"]],
})

low, high = data.bounds()
with st.sidebar:
    st.date_input("As-of date", value=high, min_value=low, max_value=high, key="as_of", format="DD/MM/YYYY",
                  help=f"Daily, weekly and monthly KPIs use the {data.config()['scorecard']['window_days']} days up to this date. Quarterly and roadmap KPIs use the quarter so far.")
    if st.button("Refresh data",key="refresh-data"):
        data.refresh()
        st.rerun()
    st.caption("Dummy data. Built for the Alcovia assessment.")

st.markdown(ui.banner(), unsafe_allow_html=True)
pg.run()
