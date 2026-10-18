"""A selected event or group must lead to its underlying records."""
import data
import metrics
from tests.conftest import AS_OF


def test_event_selection_returns_attendance_and_feedback(db):
    event_id = db.execute("SELECT event_id FROM events WHERE kind = 'workshop' AND status = 'held' AND planned_for::DATE <= ? ORDER BY planned_for DESC LIMIT 1", [AS_OF]).fetchone()[0]
    detail = metrics.run(db, "profile", "event_detail", {"event_id": event_id, "end": AS_OF})
    attendance = metrics.run(db, "profile", "event_people", {"event_id": event_id, "end": AS_OF})
    assert detail[0]["Event ID"] == event_id
    assert attendance and all("ID" in row for row in attendance)


def test_group_selection_returns_its_events(db):
    group_id = db.execute("SELECT group_id FROM events WHERE group_id IS NOT NULL LIMIT 1").fetchone()[0]
    rows = metrics.run(db, "profile", "group_events", {"group_id": group_id, "end": AS_OF})
    assert rows and all(row["Group"] == group_id and row["Date"] <= AS_OF for row in rows)


def test_daily_trend_can_show_events_and_focus_sessions(db):
    day = db.execute("SELECT started_at::DATE FROM focus_sessions WHERE started_at::DATE <= ? LIMIT 1", [AS_OF]).fetchone()[0]
    focus = metrics.run(db, "profile", "day_focus", {"day": day, "end": AS_OF})
    events = metrics.run(db, "profile", "day_events", {"day": day, "end": AS_OF})
    assert focus and all(row["Started"].date() == day and row["ID"] for row in focus)
    assert all(row["Scheduled"].date() == day and row["Event ID"] for row in events)
