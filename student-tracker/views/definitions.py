"""Read metric definitions and assumptions from the student tracker README."""
from pathlib import Path

import streamlit as st

import ui
from views.common import show

README = Path(__file__).resolve().parent.parent / "README.md"


def section(text, title):
    return text.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0].strip()


def page():
    text = README.read_text()
    show(ui.page_header("Definitions", "How every number is calculated, and what we assumed along the way."))
    how, catalogue, assumptions = st.tabs(["How to read this", "KPI catalogue", "Assumptions"])
    with how:
        st.markdown(section(text, "Approach and metric choices"))
        st.caption("The README describes the default configuration; config.yaml controls the running dashboard.")
    with catalogue:
        st.markdown(section(text, "KPI catalogue"))
    with assumptions:
        st.markdown(section(text, "Assumptions and limits"))
        st.markdown(section(text, "Assumption reference index"))
