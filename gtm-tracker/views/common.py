"""The page header every data page shares: dummy-data banner, title, and the timeline selector. The choice is remembered across pages."""
from html import escape as e

import streamlit as st

import data
import fmt
import timeline
import ui


def _remember():
    st.session_state["_tl_choice"] = st.session_state["tl_choice"]
    st.session_state["_tl_custom"] = st.session_state.get("tl_custom")


def title(text, blurb=None):
    st.markdown(ui.banner(), unsafe_allow_html=True)
    st.markdown(f'<h1 class="gt-title">{e(text)}</h1>' + (f'<p class="gt-blurb">{e(blurb)}</p>' if blurb else ""), unsafe_allow_html=True)


def header(text, blurb):
    """Draw banner, title and selector; return the chosen (start, end). A bad custom range shows its message and stops the page."""
    title(text, blurb)
    if "tl_choice" not in st.session_state:
        st.session_state["tl_choice"] = st.session_state.get("_tl_choice", timeline.DEFAULT_CHOICE)
    if st.session_state["tl_choice"] == "Custom" and "tl_custom" not in st.session_state:
        last = data.as_of()
        st.session_state["tl_custom"] = st.session_state.get("_tl_custom") or (last.replace(day=1), last)
    pick, custom, span = st.columns([1, 1.4, 2])
    pick.selectbox("Timeline", timeline.CHOICES, key="tl_choice", on_change=_remember)
    if st.session_state["tl_choice"] == "Custom":
        custom.date_input("Custom range", key="tl_custom", max_value=data.as_of(), on_change=_remember)
    try:
        start, end = data.period()
    except ValueError as err:
        st.error(str(err))
        st.stop()
    span.markdown(f'<div class="gt-span">{start:%d %b %Y} to {end:%d %b %Y}</div>', unsafe_allow_html=True)
    return start, end


def section(text, sub=None):
    st.markdown(f'<h2 class="gt-h2">{e(text)}</h2>' + (f'<p class="gt-sub-h">{e(sub)}</p>' if sub else ""), unsafe_allow_html=True)


def tiles(items):
    """items = [(label, value, sub, status)]; one row of tiles."""
    cols = st.columns(len(items))
    for col, (label, value, sub, status) in zip(cols, items):
        col.markdown(ui.tile(label, value, sub, status), unsafe_allow_html=True)


def num(x):
    """None for a missing number (pandas gives NaN), otherwise the number."""
    return None if fmt.missing(x) else x


def pick(table, ids, key, cap=None):
    """Show `table` where clicking any cell picks that row: returns the matching entry of `ids` (a Series aligned with the rows), or None.
    A counter in the widget key means the next run draws a fresh table, so the cell is not still selected when a dialog opened by the click is closed.
    `cap` limits the height in pixels; without it the table is as tall as its rows."""
    st.session_state.setdefault(key, 0)
    height = "auto" if cap is None else min(35 * (len(table) + 1) + 3, cap)
    picked = st.dataframe(table, hide_index=True, width="stretch", height=height, on_select="rerun", selection_mode="single-cell", key=f"{key}-{st.session_state[key]}")
    if picked.selection.cells:
        st.session_state[key] += 1
        return ids.iloc[picked.selection.cells[0][0]]
