"""The drill-downs: every KPI has one, and the rows behind a KPI add up to the KPI's headline number."""
import pytest

import drill
import metrics
import scorecard as sc
from tests.conftest import AS_OF

KEYS = [(k.activity, k.name) for k in sc.KPIS]


def test_every_kpi_has_a_drill():
    assert [k for k in KEYS if k not in drill.SPECS] == []
    assert [k for k in drill.SPECS if k not in KEYS] == []


@pytest.fixture(scope="module")
def seeded(db):
    """The dummy database the dashboard runs on, with the headline value of every KPI."""
    cfg = metrics.load_config()
    return db, cfg, {(r["activity"], r["kpi"]): r["value"] for r in sc.kpi_rows(db, cfg, AS_OF)}


@pytest.mark.parametrize("key", KEYS, ids=[f"{a}: {n}" for a, n in KEYS])
def test_drill_adds_up_to_the_headline(seeded, key):
    con, cfg, headline = seeded
    out = drill.fetch(con, cfg, AS_OF, *key)
    if out["kind"] == "list":
        assert out["headline"] is None
        return
    want = headline[key]
    if want is None:
        assert out["headline"] is None
    else:
        assert out["headline"] is not None, "the KPI has a value but its drill-down has no rows"
        assert out["headline"] == pytest.approx(min(1.0, max(0.0, want)), abs=1e-9)


@pytest.mark.parametrize("text,tone", [("✓ Yes", "good"), ("✓ 3 of 3", "good"), ("✕ No", "bad"), ("✕ 0 of 5", "bad"), ("✕ 2 of 5", "partial"), ("–", None)])
def test_result_tone(text, tone):
    assert drill.result_tone(text) == tone


def test_a_student_profile_has_every_section_and_matches_the_student_table(seeded):
    import student_profile as prof
    con, cfg, _ = seeded
    people = sc.student_table(con, cfg, AS_OF)
    sid = people[0]["student_id"]
    out = prof.fetch(con, cfg, AS_OF, sid)
    assert out["identity"]["ID"] == sid and set(out["sections"]) == set(prof.SECTIONS)
    quizzes = dict(out["sections"]["Quizzes"])["Last 30 days of 8pm quizzes"]
    started = sum(r["Start"] != "Not started" for r in quizzes)
    assert started >= 0 and len(quizzes) > 0
    for tab, parts in out["sections"].items():
        assert all(isinstance(rows, list) for _, rows in parts), tab
    assert any(rows for parts in out["sections"].values() for _, rows in parts)
