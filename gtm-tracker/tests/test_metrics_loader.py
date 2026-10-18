from datetime import date

import duckdb
import pytest

import metrics
from tests.conftest import ROOT


def test_loader_names_and_missing_param(tmp_path, monkeypatch):
    (tmp_path / "t.sql").write_text("-- name: one\nSELECT 1 AS a;\n-- name: two\nSELECT $x AS b\n")
    monkeypatch.setattr(metrics, "SQL_DIR", tmp_path)
    metrics.load.cache_clear()
    assert set(metrics.load("t")) == {"one", "two"}
    con = duckdb.connect()
    assert metrics.run(con, "t", "two", {"x": 5}) == [{"b": 5}]
    with pytest.raises(KeyError, match="x"):
        metrics.run(con, "t", "two", {})
    metrics.load.cache_clear()


def test_params_flattens_config_and_adds_period():
    prm = metrics.params({"a": {"b": 1}, "c": [4, 7]}, date(2026, 10, 1), date(2026, 10, 18))
    assert prm["a_b"] == 1 and prm["c_0"] == 4 and prm["c_1"] == 7
    assert prm["start"] == date(2026, 10, 1) and prm["end"] == date(2026, 10, 18)


def test_schema_loads_all_tables():
    con = duckdb.connect()
    con.execute((ROOT / "sql" / "schema" / "gtm.sql").read_text())
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert tables == {"enrollments", "invoices", "workshops", "workshop_payments", "revenue_targets", "campaigns", "ad_sets", "ads",
                      "ad_daily", "ad_set_daily", "landing_page_daily", "leads", "lead_stages", "snapshot_meta"}


def test_describe_returns_the_comment_block_under_each_name(tmp_path, monkeypatch):
    (tmp_path / "t.sql").write_text("-- preamble\n\n-- name: one\n-- Definition: first thing.\n-- Grain: one row.\nSELECT 1\n\n-- name: two\n-- Definition: second.\nSELECT 2\n")
    monkeypatch.setattr(metrics, "SQL_DIR", tmp_path)
    assert metrics.describe("t") == {"one": "Definition: first thing.\nGrain: one row.", "two": "Definition: second."}


def test_every_shipped_query_documents_definition_grain_source_and_edge_cases():
    for file in ("revenue", "funnel", "campaigns", "rca"):
        for name, text in metrics.describe(file).items():
            for key in ("Definition:", "Grain:", "Source", "Edge cases:"):
                assert key in text, (file, name, key)
