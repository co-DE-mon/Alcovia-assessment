"""What a product owner reads off the numbers: a verdict, the biggest gaps, where students drop off, who to act on. Pure functions with no Streamlit
import, so they can be tested. Every sentence is built from thresholds and counts, so the same data always gives the same words."""
import ui

# KPIs measured over a period that is not finished (see sql/metrics/given.sql, rigour_adherence). They read low by construction, so they are shown on
# their own card but never named as the biggest gap or the weakest point.
UNFINISHED_PERIOD = {("Academic roadmap", "Monthly rigour adherence")}


def with_data(rows):
    return [r for r in rows if r["value"] is not None]


def rankable(rows):
    return [r for r in with_data(rows) if (r["activity"], r["kpi"]) not in UNFINISHED_PERIOD]


def weakest(rows):
    rows = rankable(rows)
    return min(rows, key=lambda r: (r["value"], r["kpi"])) if rows else None


def strongest(rows):
    rows = [r for r in rankable(rows) if r["status"] == "on_track"]
    return max(rows, key=lambda r: (r["value"], r["kpi"])) if rows else None


def gaps(rows, n=5):
    """The n KPIs furthest from on track, worst first. A KPI at or above the on-track line is not a gap."""
    return sorted((r for r in rankable(rows) if r["status"] != "on_track"), key=lambda r: (r["value"], r["kpi"]))[:n]


def bright_spots(rows, n=3):
    return sorted((r for r in rankable(rows) if r["status"] == "on_track"), key=lambda r: (-r["value"], r["kpi"]))[:n]


def movement(rows):
    """(up, down) = how many KPIs rose or fell by at least a share point against the earlier window; None when there is no earlier window."""
    deltas = [r["delta"] for r in rows if r.get("delta") is not None]
    if not deltas:
        return None
    return sum(d >= ui.FLAT for d in deltas), sum(d <= -ui.FLAT for d in deltas)


def kpis(n):
    return "KPI" if n == 1 else "KPIs"


def summary(rows, cfg):
    """Sentences for a set of KPIs: how many are on track, the biggest gap, and how the set moved against the earlier window."""
    measurable = with_data(rows)
    if not measurable:
        return ["No KPI here has data yet."]
    on = sum(r["status"] == "on_track" for r in measurable)
    out = [f"{on} of {len(measurable)} measurable KPIs are on track."]
    low = weakest(rows)
    if low["status"] != "on_track":
        count = f", {low['detail']}" if low.get("detail") else ""
        out.append(f"Biggest gap: {low['kpi']} ({low['activity']}) at {ui.pct(low['value'], cfg)}{count}.")
    move = movement(rows)
    if move is not None:
        out.append(f"Against the previous {cfg["scorecard"]["window_days"]} days: up on {move[0]} {kpis(move[0])}, down on {move[1]}.")
    return out


def activity_verdict(rows, cfg):
    """(status, text) for one activity's KPIs: its weakest KPI sets the status, and the text says which one and why it matters."""
    low = weakest(rows)
    if low is None:
        return "no_data", "No KPI for this activity has data yet."
    n = len(with_data(rows))
    if low["status"] == "on_track":
        return "on_track", f"All {n} measurable KPIs are on track." if n > 1 else "On track."
    best = strongest(rows)
    text = f"Weakest: {low['kpi']} at {ui.pct(low['value'], cfg)}"
    text += f", {low['detail']}." if low.get("detail") else "."
    if best is not None and best is not low:
        text += f" Strongest: {best['kpi']} at {ui.pct(best['value'], cfg)}."
    return low["status"], text


def engagement(people, cfg):
    """How many students show each behaviour, for the engagement panel: [{label, count, base, note}]. The base is the students it applies to."""
    watch, n = cfg["scorecard"]["watch_min"], cfg["scorecard"]["lookback_days"]
    def item(label, note, test, number, applies):
        """who: one (student, shows the behaviour: True / False / None when it does not apply to them, the number behind it) per student."""
        who = [(s, bool(test(s)) if applies(s) else None, number(s)) for s in people]
        known = [w for w in who if w[1] is not None]
        return {"label": label, "note": note, "count": sum(w[1] for w in known), "base": len(known), "who": who}

    pct = lambda v: "–" if v is None else f"{v * 100:.0f}%"
    return [
        item("Took a quiz recently", f"at least one 8pm quiz in the last {n} days", lambda s: s["quizzes_started"] > 0,
             lambda s: f'{s["quizzes_started"]} of {s["quizzes_due"]} quizzes', lambda s: True),
        item("Did focus time recently", f"at least one completed focus session in the last {n} days", lambda s: s["focus_minutes"] > 0,
             lambda s: f'{s["focus_minutes"]:.0f} focus minutes', lambda s: True),
        item("Finishing their to-dos", f"at least {round(watch * 100)}% of to-dos due were done", lambda s: s["task_completion_rate"] >= watch,
             lambda s: f'{pct(s["task_completion_rate"])} of to-dos done', lambda s: s["task_completion_rate"] is not None),
        item("On the syllabus pace", "covered enough of the syllabus for this date", lambda s: s["syllabus_on_track"],
             lambda s: "no syllabus record" if s["syllabus_pct"] is None else f'{s["syllabus_pct"]:.0f}% covered, pace is {s["syllabus_pace_pct"]:.0f}%', lambda s: s["syllabus_on_track"] is not None),
        item("Roadmap items on time", "most roadmap items done by their deadline", lambda s: s["roadmap_on_track"],
             lambda s: "nothing due" if s["roadmap_pct"] is None else f'{s["roadmap_pct"]:.0f}% done by deadline', lambda s: s["roadmap_on_track"] is not None),
    ]


def by_advisor(listed):
    """[(advisor_id, [students])] for the students who need attention, the advisor with the most of them first."""
    groups = {}
    for s in listed:
        groups.setdefault(s["advisor_id"], []).append(s)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
