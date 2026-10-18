"""Page registry: app.py fills it in, pages use link() to point at each other. Outside the app (in tests) it is empty and link() does nothing."""
import streamlit as st

PAGES = {}


def link(key, label):
    page = PAGES.get(key)
    if page is not None:
        st.page_link(page, label=label)
