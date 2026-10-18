import streamlit as st

import metrics
from views.common import section, title

FILES = {"revenue": "Revenue", "funnel": "Funnel", "campaigns": "Campaigns", "rca": "Root cause analysis"}


def page():
    title("Definitions", "Every number on the other pages comes from one of these queries. The text is read from the SQL file itself, so it cannot drift.")
    for file, label in FILES.items():
        section(label)
        for name, text in metrics.describe(file).items():
            with st.expander(name):
                st.code(text, language=None)
