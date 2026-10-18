"""views.common.pick: a click on a table cell returns that row's id and draws a fresh table next run. AppTest cannot click a dataframe, so st is replaced."""
from types import SimpleNamespace

import pandas as pd

from views import common


def fake_streamlit(cells):
    seen = {}

    def dataframe(table, **kwargs):
        seen.update(kwargs, rows=len(table))
        return SimpleNamespace(selection=SimpleNamespace(cells=cells))
    return SimpleNamespace(session_state={}, dataframe=dataframe), seen


def test_a_clicked_cell_returns_its_rows_id_and_changes_the_widget_key(monkeypatch):
    st, seen = fake_streamlit([(1, 0)])
    monkeypatch.setattr(common, "st", st)
    table = pd.DataFrame({"a": [1, 2, 3]})
    assert common.pick(table, pd.Series(["x", "y", "z"]), "t") == "y"
    assert seen["key"] == "t-0" and st.session_state["t"] == 1
    common.pick(table, pd.Series(["x", "y", "z"]), "t")
    assert seen["key"] == "t-1"


def test_no_click_returns_none_and_keeps_the_key(monkeypatch):
    st, seen = fake_streamlit([])
    monkeypatch.setattr(common, "st", st)
    assert common.pick(pd.DataFrame({"a": [1]}), pd.Series(["x"]), "t") is None
    assert seen["key"] == "t-0" and st.session_state["t"] == 0


def test_height_is_automatic_unless_capped(monkeypatch):
    st, seen = fake_streamlit([])
    monkeypatch.setattr(common, "st", st)
    table = pd.DataFrame({"a": range(100)})
    common.pick(table, pd.Series(range(100)), "t")
    assert seen["height"] == "auto"
    common.pick(table, pd.Series(range(100)), "t", 300)
    assert seen["height"] == 300
    common.pick(table.head(2), pd.Series(range(2)), "t", 300)
    assert seen["height"] == 35 * 3 + 3
