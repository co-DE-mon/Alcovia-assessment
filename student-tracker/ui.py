"""HTML building blocks for the dashboard. Pure functions with no Streamlit import, so they can be tested.

Design rules (from the dataviz guidance):
- The four status colours are the fixed status palette, never themed, and a status is never shown by colour alone: every one carries an icon and a label.
- The app is light-theme only (.streamlit/config.toml): cards are white and text uses the page's own ink (currentColor, with opacity for secondary text).
- A single ratio against a limit is a meter (a track with the on-track and watch lines marked), not a pie. A headline number is a tile.
- Every value that comes from user-visible data goes through html.escape. Markup is built on one line: Markdown would treat indented HTML as code.
"""
import math
from html import escape as e

STATUS = {   # label, icon glyph, fill, glyph colour (dark glyph on amber for contrast)
    "on_track": ("On track", "✓", "#3aa675", "#ffffff"),
    "watch": ("Watch", "!", "#e9b44c", "#0b0b0b"),
    "off_track": ("Off track", "✕", "#dc6b6b", "#ffffff"),
    "no_data": ("No data", "–", "#9aa3b5", "#ffffff"),
}
LENS_LABEL = {"conducted": "Conducted", "liked": "Liked", "performed": "Performed"}
LENS_QUESTION = {"conducted": "Did Alcovia run it?", "liked": "Did students like it?", "performed": "How did students perform?"}
CADENCE_LABEL = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "quarterly": "Quarterly", "roadmaps": "Roadmaps"}
CADENCE_BLURB = {
    "daily": "Timetable, the 8pm quiz, focus time, active minutes and recovery.",
    "weekly": "The academic roadmap, advisor input and academic sessions, with the five success metrics.",
    "monthly": "Workshops, pod and peer sessions, mentor calls and personal branding.",
    "quarterly": "Podcast, competition prep, parent-child bonding, the out-of-city trip and the quarter's themes.",
    "roadmaps": "Career, personal and academic roadmaps, syllabus completion and rigour.",
}
REASON_SHORT = {"no_quiz": "No quiz", "no_focus": "No focus time", "syllabus_behind": "Behind on syllabus",
                "roadmap_off_track": "Roadmap slipping", "tasks_slipping": "To-dos slipping"}

# One plain-English line per KPI: the question the number answers, so a percentage is never shown without its meaning.
KPI_PLAIN = {
    "Quizzes held / days": "On how many days did an 8pm quiz actually run?",
    "Quizzes finished / started (proxy)": "Of the quizzes students opened, how many did they finish? Few finishing suggests they didn't enjoy it.",
    "Regular quiz takers (proxy)": "What share of students took at least {regular} of the last {regular_of} quizzes? Regulars suggest they like it.",
    "Started inside the entry window": "What share of students started within {entry} minutes of 8pm, before the entry window closed?",
    "Student-days with a session": "Out of all student-days, on how many did the student run at least one focus session?",
    "Sessions not given up (proxy)": "Of the focus sessions started, how many were not abandoned halfway?",
    "Student-days at the focus target": "On what share of student-days did the student reach the daily focus-minutes target?",
    "Student-days with a to-do due": "On what share of student-days did the student have a to-do planned? No to-do means no timetable.",
    "Calendar still connected (proxy)": "Of students who connected their calendar, how many still have it connected after {retained} days?",
    "To-dos done on their due date": "Of the to-dos that fell due, how many were finished on that same day?",
    "Student-days with wearable strain": "On what share of student-days did the wearable send activity data?",
    "Wearable still connected (proxy)": "Of students who connected a wearable, how many still have it connected after {retained} days?",
    "Strain inside the target band": "On what share of days was the student's physical strain in the healthy range (not too low, not too high)?",
    "Sleep at or above target": "On what share of nights with data did the student sleep at least the target hours?",
    "Study-hour plan set": "How many students have set their weekday and weekend study hours?",
    "Students on the syllabus pace": "How many students have covered as much of the syllabus as the {pace}%-a-quarter pace says they should by now?",
    "Task completion rate": "Of the to-dos that fell due, how many did students finish?",
    "Deadline adherence": "Of the to-dos students finished, how many were finished by the deadline?",
    "Time estimation accuracy": "How close were the study hours students planned to the hours they actually spent? 100% is a perfect estimate.",
    "Chapter readiness score": "On average, how ready are students across their chapters (the five stages from reading to exam accuracy)?",
    "Monthly rigour adherence": "Of the chapters planned for the month, how many reached the full rigour standard?",
    "Advisor-assigned to-dos done": "Of the to-dos advisors assigned, how many did the student finish? Low can mean advisors assign too much, or students ignore them.",
    "Advisor-assigned to-dos done on time": "Of the to-dos advisors assigned, how many were finished by their deadline?",
    "Students filling in their inputs": "How many students filled in their weekly inputs (a to-do of their own or a completion) in the last {input_days} days?",
    "Academic sessions held vs policy": "Did Alcovia hold as many academic sessions as the monthly policy promises? 100% means as many as promised.",
    "Session feedback (average rating / 5)": "How did students rate their sessions (average of 3 star questions, out of 5)?",
    "Academic sessions attended": "Of the sessions held, how many did the invited student attend?",
    "Workshops held vs expected": "Did Alcovia hold the two workshops a month it plans?",
    "Workshop rating (average / 5)": "How did students rate the workshops, out of 5?",
    "Workshop NPS (/ 10)": "How likely are students to recommend the workshops, out of 10?",
    "Workshop attendance": "Of the students invited to a workshop, how many came?",
    "Pods held vs expected": "Did Alcovia hold as many pod sessions as planned (one per pod a month)?",
    "Pod rating (average / 5)": "How did students rate the pod sessions, out of 5?",
    "Pod attendance": "Of the students invited to a pod session, how many came?",
    "Peer sessions held vs expected": "Did Alcovia arrange as many peer sessions as the target (our own target, not Alcovia's)?",
    "Peer session rating (average / 5)": "How did students rate peer sessions, out of 5?",
    "Peer session attendance": "Of the students invited to a peer session, how many came?",
    "Mentor calls held vs expected": "Did every student get their one mentor call a month?",
    "Mentor call rating (average / 5)": "How did students rate their mentor calls, out of 5?",
    "Mentor call attendance": "Of the mentor calls booked, how many did the student show up to?",
    "Shoots held / scheduled": "Of the personal-branding shoots scheduled, how many actually happened?",
    "Shoots posted": "Of the shoots that happened, how many clips were posted?",
    "Podcasts held / scheduled": "Of the podcast shoots scheduled this quarter, how many happened?",
    "Podcast rating (average / 5)": "How did students rate their podcast shoot, out of 5?",
    "Episodes posted": "Of the podcasts shot, how many episodes have been published?",
    "Students assigned a competition": "How many students have been given a competition to prepare for this quarter?",
    "Competition rating (average / 5)": "How did students rate the competition prep support, out of 5?",
    "Assigned students who entered": "Of the students assigned a competition, how many actually entered it?",
    "Parent workshop held": "Has the parent-child workshop happened this quarter?",
    "Parent workshop rating (average / 5)": "How did students rate the parent-child workshop, out of 5?",
    "Parent workshop attendance": "Of the families invited, how many attended?",
    "Trip held": "Has the out-of-city trip happened this quarter?",
    "Trip rating (average / 5)": "How did students rate the trip, out of 5?",
    "Trip attendance": "Of the students invited on the trip, how many went?",
    "Social work activities held / scheduled": "Of the social-work activities scheduled, how many happened?",
    "Groups formed": "Were the expected social-work groups formed?",
    "Social work rating (average / 5)": "How did students rate the social-work theme, out of 5?",
    "Social work attendance": "Of the students invited to social-work activities, how many attended?",
    "Theme milestones done by deadline": "Of the theme's milestones that are due, how many were done by their deadline?",
    "Students with a career roadmap": "How many students have a career roadmap set up?",
    "Career roadmap items done": "Of all items on students' career roadmaps, how many are done?",
    "Students with monthly milestones": "How many students have their personal milestones set for the month?",
    "Milestones done by deadline": "Of the personal milestones that are due, how many were done by their deadline?",
    "Students with an academic roadmap": "How many students have an academic roadmap set up?",
    "Advisor inputs done": "Of the inputs the brief assigns to the academic advisor, how many have been done?",
    "Academic items done by deadline": "Of the academic roadmap items that are due, how many were done by their deadline?",
    "Exam scores at or above target": "Of the scored subject results, how many reached the student's target score?",
    "Roadmap check-in rating (average / 5)": "In the monthly roadmap check-in, how did students rate their progress, how invested they feel and how confident they are, out of 5?",
    "Monthly syllabus reviews done": "Did the advisor hold the monthly syllabus re-evaluation with each student? Counted per student and month.",
    "Chapters covered against the syllabus pace": "Across all students, how many chapters are done compared with the number the {pace}%-a-quarter pace says should be done by now? 100% means on pace.",
    "Rigour checks done by the advisor": "Did the advisor do the rigour check with each student this quarter? Counted per student and month.",
    "Sprints made when a timeline was missed": "When a student missed a timeline, did the advisor make a catch-up sprint? Counted per student and month.",
    "Students still working through their chapters (proxy)": "How many students moved a chapter forward in the last {days} days? A student who has stopped has probably stopped liking the work.",
    "Chapters from past months fully complete": "Of the chapters planned for months that have ended, how many went through all five stages, from reading to exam accuracy?",
    "Application support sessions held / scheduled": "Of the summer-program application support sessions scheduled, how many were held?",
    "Summer support rating (average / 5)": "How did students rate the application support, out of 5? (A one-tap rating, proposed.)",
    "Students who submitted an application": "Of the students invited to application support, how many have submitted a summer application?",
    "Student-days with a recovery reading": "On what share of student-days did the wearable send a recovery reading? No reading means no recovery data for that day.",
    "Whoop students still syncing (proxy)": "Of students who connected a Whoop, how many are still sending data? A student who disconnected or went silent counts as not liking it enough to keep it on.",
    "Roadmap check-in: pace of progress (average / 5)": "In the monthly check-in, how did students rate the pace of their progress, out of 5?",
    "Academic session rating (average / 5)": "How did students rate their academic coaching sessions, out of 5?",
    "Posted clips reaching the view target (proxy)": "Of the clips posted, how many got at least the view target? Views stand in for whether the audience liked it.",
    "Students with a startup plan": "How many students have their entrepreneurship milestones set up?",
    "Entrepreneurship rating (average / 5)": "How did students rate the entrepreneurship theme in the one-tap rating at the end of each month, out of 5?",
    "Check-in: confidence the roadmap leads to the goals (average / 5)": "In the monthly check-in, how confident are students that their roadmap leads to their goals, out of 5?",
    "Check-in: how invested students feel (average / 5)": "In the monthly check-in, how invested do students feel in their personal goals, out of 5?",
}


def plain_text(kpi, cfg):
    """The plain-English line for a KPI, with the numbers it mentions (windows, targets) read from config.yaml."""
    q = cfg["quiz"]
    return KPI_PLAIN.get(kpi, "").format(
        days=cfg["scorecard"]["window_days"], input_days=cfg["weekly"]["input_window_days"], pace=cfg["syllabus"]["quarter_target_pct"],
        entry=q["entry_window_minutes"], retained=cfg["wellness"]["connected_after_days"], regular=q["regular_taker_days"][0], regular_of=q["regular_taker_days"][1])


LENS_HOWTO = {
    "conducted": "Is Alcovia delivering the activity? Low means the activity itself isn't happening enough.",
    "liked": "Do students value it? Uses the app's own feedback rating where one exists; otherwise behaviour (finishing, staying connected) stands in, marked (proxy).",
    "performed": "Are students doing what is asked of them? Low means the activity runs but students don't follow through.",
}


def fmt_date(d):
    return f"{d.day} {d:%b %Y}"


def fmt_short(d):
    return f"{d.day} {d:%b}"


def ago(days):
    if days is None:
        return "never"
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def pct(value, cfg=None):
    """A share as a percent. A value just under a threshold shows one decimal, so 79.7% never reads as the on-track 80%."""
    if value is None:
        return "—"
    x = value * 100
    if cfg is not None:
        sc = cfg["scorecard"]
        for line in (sc["on_track_min"] * 100, sc["watch_min"] * 100):
            if x < line <= round(x):
                return f"{math.floor(x * 10) / 10:.1f}%"
    return f"{x:.0f}%"


def icon(status):
    label, glyph, fill, ink = STATUS[status]
    return f'<span class="sv-ico" style="background:{fill};color:{ink}" aria-hidden="true">{glyph}</span>'


def chip(status, label=None):
    text = label or STATUS[status][0]
    return f'<span class="sv-chip sv-s-{status}">{icon(status)}<span>{e(text)}</span></span>'


def meter(value, status, cfg, label):
    """A track from 0 to 100% with the watch and on-track lines marked and the fill in the status colour."""
    sc = cfg["scorecard"]
    fill = STATUS[status][2]
    width = 0 if value is None else max(0.0, min(1.0, value)) * 100
    now = "" if value is None else f' aria-valuenow="{width:.0f}"'
    return (f'<div class="sv-meter" role="meter" aria-valuemin="0" aria-valuemax="100"{now} aria-label="{e(label)}">'
            f'<div class="sv-meter-fill" style="width:{width:.1f}%;background:{fill}"></div>'
            f'<i class="sv-tick" style="left:{sc["watch_min"] * 100:.0f}%"></i><i class="sv-tick" style="left:{sc["on_track_min"] * 100:.0f}%"></i></div>')


def counts_text(counts):
    text = f'{counts["on_track"]} on track · {counts["watch"]} watch · {counts["off_track"]} off track'
    return text + (f' · {counts["no_data"]} no data' if counts["no_data"] else "")


def tile(label, value, sub="", chip_html="", title=""):
    t = f' title="{e(title)}"' if title else ""
    return (f'<div class="sv-tile"{t}><div class="sv-tile-label">{e(label)}</div><div class="sv-tile-value">{e(str(value))}</div>'
            f'<div class="sv-tile-sub">{e(sub)}{chip_html}</div></div>')


def tile_row(items):
    """A row of tiles or cards as one CSS grid: equal heights, and it wraps by itself on narrow screens."""
    return f'<div class="sv-tiles">{"".join(items)}</div>'


def page_header(title, sub="", dummy=True):
    badge = '<span class="sv-badge">Dummy data</span>' if dummy else ""
    return f'<div class="sv-head"><h1 class="sv-h1">{e(title)}{badge}</h1><p class="sv-lede">{e(sub)}</p></div>'


def banner():
    return ('<div class="sv-banner" role="note"><b>Dummy data.</b> Every student, score and event here is generated for this assessment. '
            'Nothing is real, and no real student is identified.</div>')


def legend(cfg):
    sc = cfg["scorecard"]
    on, watch = round(sc["on_track_min"] * 100), round(sc["watch_min"] * 100)
    return ('<div class="sv-legend">' + chip("on_track", f"On track ≥ {on}%") + chip("watch", f"Watch {watch}–{on}%")
            + chip("off_track", f"Off track < {watch}%") + chip("no_data", "No data: nothing to measure") + "</div>")


def scorecard_grid(grid, cadences, cfg, windows):
    """The front-page grid: one row per cadence, one column per lens. windows maps cadence -> the period it covers."""
    head = '<div class="sv-gh"></div>' + "".join(
        f'<div class="sv-gh"><b>{LENS_LABEL[l]}</b><span>{LENS_QUESTION[l]}</span></div>' for l in LENS_LABEL)
    body = []
    for c in cadences:
        body.append(f'<div class="sv-rowlabel"><b>{e(CADENCE_LABEL[c])}</b><span>{e(windows[c])}</span></div>')
        for l in LENS_LABEL:
            cell = grid[c][l]
            s = cell["status"]
            label = f'{CADENCE_LABEL[c]} {LENS_LABEL[l].lower()}: {pct(cell["value"], cfg)}, {STATUS[s][0].lower()}'
            sub = counts_text(cell["counts"]) if cell["with_data"] else "No KPI had data in this window"
            body.append(f'<div class="sv-cell sv-s-{s}"><span class="sv-lens">{LENS_LABEL[l]}</span>'
                        f'<div class="sv-cell-top">{chip(s)}<span class="sv-cell-val">{pct(cell["value"], cfg)}</span></div>'
                        f'{meter(cell["value"], s, cfg, label)}<div class="sv-sub">{e(sub)}</div></div>')
    return f'<div class="sv-grid">{head}{"".join(body)}</div>'


FLAT = 0.01   # a change smaller than one share point reads as no change


def delta_parts(delta):
    """(direction, text) for a change in share points: ('up', '▲ 4 pts'), ('down', '▼ 5 pts'), ('flat', 'no change'); (None, '') without one."""
    if delta is None:
        return None, ""
    pts = round(abs(delta) * 100)
    if abs(delta) < FLAT or pts == 0:
        return "flat", "no change"
    return ("up", f"▲ {pts} pts") if delta > 0 else ("down", f"▼ {pts} pts")


def delta_chip(delta, days):
    """The change against the earlier window, as a small arrow and number. The arrow and the words carry it, so colour is never the only signal."""
    kind, text = delta_parts(delta)
    if kind is None:
        return ""
    return f'<span class="sv-delta sv-delta-{kind}" title="Against the previous {days} days">{text}</span>'


def verdict_card(sentences, status):
    """The page's headline: a few plain sentences in a card edged in the status colour of the page's weakest point."""
    lead, rest = sentences[0], sentences[1:]
    body = "".join(f"<p>{e(x)}</p>" for x in rest)
    return f'<div class="sv-verdict sv-s-{status}"><p class="sv-verdict-lead">{e(lead)}</p>{body}</div>'


def engagement_row(label, count, base, note, status, cfg):
    share = None if not base else count / base
    value = "—" if share is None else f"{count} of {base}"
    return (f'<div class="sv-eng"><div class="sv-eng-head"><span class="sv-kpi-name">{e(label)}</span><span class="sv-kpi-val">{icon(status)}{value}</span></div>'
            f'{meter(share, status, cfg, f"{label}: {value}")}<div class="sv-sub">{e(note)}</div></div>')


def advisor_header(advisor, n):
    return f'<div class="sv-advisor"><b>{e(advisor)}</b><span class="sv-muted"> · {n} student{"s" if n != 1 else ""} need attention</span></div>'


def kpi_row(row, cfg):
    s = row["status"]
    value = pct(row["value"], cfg)
    shown = f'<span class="sv-kpi-val">{icon(s)}{value}</span>' if row["value"] is not None else f'<span class="sv-kpi-val sv-muted">{icon(s)}No data</span>'
    plain = f'<div class="sv-kpi-plain">{e(plain_text(row["kpi"], cfg))}</div>' if row["kpi"] in KPI_PLAIN else ""
    if row.get("detail"):
        plain += f'<div class="sv-kpi-count">{e(row["detail"])}</div>'
    return (f'<div class="sv-kpi" title="Source: {e(row["source"])}"><div class="sv-kpi-head"><span class="sv-kpi-name">{e(row["kpi"])}</span>{delta_chip(row.get("delta"), cfg["scorecard"]["window_days"])}{shown}</div>'
            f'{plain}{meter(row["value"], s, cfg, row["kpi"] + ": " + value)}</div>')


def reason_tags(reasons, explanations):
    return "".join(f'<span class="sv-tag" title="{e(x)}">{e(REASON_SHORT[r])}</span>' for r, x in zip(reasons, explanations))


def attention_row(s):
    new = '<span class="sv-tag sv-tag-new" title="Enrolled for less than the scorecard window">New student</span>' if s["new_student"] else ""
    quiet = "no activity recorded" if s["days_since_activity"] is None else f'last active {ago(s["days_since_activity"])}'
    return (f'<div class="sv-att"><div class="sv-att-main"><b>{e(s["name"])}</b><span class="sv-muted"> · {e(s["student_id"])} · {e(s["advisor_id"])} · {e(quiet)}</span>{new}</div>'
            f'<div class="sv-tags">{reason_tags(s["reasons"], s["explanations"])}</div></div>')


def source_card(r):
    fresh = not r["stale"]
    chip_html = chip("on_track", "Fresh") if fresh else chip("off_track", "Stale")
    if r["last_ok_at"] is None:
        ok = "No successful run yet"
    else:
        ok = f'Last successful run {fmt_short(r["last_ok_at"])}, {r["last_ok_at"]:%H:%M} · {r["hours_since_ok"]} h ago'
    last = "Never run" if r["last_status"] is None else f'Latest run: {r["last_status"]}'
    extra = f'{r["failed_7d"]} failed and {r["partial_7d"]} partial in the last 7 days'
    err = f'<div class="sv-err">{e(r["last_error"])}</div>' if r["last_error"] and r["last_status"] != "ok" else ""
    return (f'<div class="sv-src"><div class="sv-src-top"><b>{e(r["source"])}</b>{chip_html}</div>'
            f'<div class="sv-sub">{e(ok)}</div><div class="sv-sub">{e(last)} · {e(extra)}</div>{err}</div>')


def quiz_strip(timeline):
    """One small square per day: filled = started the quiz, hollow = quiz held and not started, dot = no quiz that day. The legend names all three."""
    cells = []
    for r in timeline:
        if not r["quiz_held"]:
            kind, text = "none", "no quiz"
        elif r["quiz_started"]:
            kind, text = "yes", "started the quiz"
        else:
            kind, text = "no", "quiz held, not started"
        cells.append(f'<span class="sv-day sv-day-{kind}" title="{fmt_short(r["day"])}: {text}"></span>')
    return (f'<div class="sv-strip" role="img" aria-label="Daily quiz record">{"".join(cells)}</div>'
            '<div class="sv-sub"><span class="sv-day sv-day-yes"></span> started · <span class="sv-day sv-day-no"></span> held, not started · '
            '<span class="sv-day sv-day-none"></span> no quiz that day</div>')


CSS = """
<style>
.block-container{padding:2.2rem 2rem 3rem;max-width:none}
.sv-head{margin:0 0 .9rem}
.sv-h1{font-size:1.9rem;font-weight:700;margin:0;padding:0;line-height:1.2;letter-spacing:-.01em}
.sv-lede{margin:.25rem 0 0;opacity:.72;font-size:1rem}
.sv-badge{display:inline-block;margin-left:.7rem;padding:.12rem .55rem;border:1px solid #cdd6f6;border-radius:999px;background:#eaeefc;color:#4a5aa8;font-size:.72rem;font-weight:600;vertical-align:middle;letter-spacing:.02em}
.sv-banner{border:1px solid #efe4bf;border-left:4px solid #e9c46a;border-radius:8px;padding:.5rem .8rem;font-size:.88rem;margin:0 0 1rem;background:#fdf9ec}
.sv-muted{opacity:.68}
.sv-sub{font-size:.8rem;opacity:.72;margin-top:.3rem}
.sv-ico{display:inline-flex;align-items:center;justify-content:center;width:1.05rem;height:1.05rem;border-radius:50%;font-size:.68rem;font-weight:800;line-height:1;flex:none}
.sv-chip{display:inline-flex;align-items:center;gap:.35rem;padding:.12rem .55rem .12rem .3rem;border:1px solid #dde3f1;background:#fff;border-radius:999px;font-size:.78rem;font-weight:600;margin:0 .35rem .25rem 0;white-space:nowrap}
.sv-legend{display:flex;flex-wrap:wrap;gap:.1rem;margin:.2rem 0 .8rem}
.sv-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin:0 0 1rem}
.sv-tile{border:1px solid #e4e8f3;border-top:4px solid #8ea6ee;border-radius:12px;padding:.9rem 1.05rem;background:#fff;box-shadow:0 1px 2px rgba(60,80,140,.06);height:100%;box-sizing:border-box}
.sv-tile-label{font-size:.82rem;opacity:.75;font-weight:600}
.sv-tile-value{font-size:2.2rem;font-weight:700;line-height:1.15;margin:.15rem 0}
.sv-tile-sub{font-size:.8rem;opacity:.8}
.sv-tile-sub .sv-chip{margin-left:.4rem;margin-bottom:0}
.sv-grid{display:grid;grid-template-columns:150px repeat(3,minmax(0,1fr));gap:.6rem;align-items:stretch;margin:.2rem 0 .6rem}
.sv-gh{font-size:.82rem;padding:0 .2rem}.sv-gh b{display:block;font-size:.95rem}.sv-gh span{opacity:.7}
.sv-rowlabel{display:flex;flex-direction:column;justify-content:center;padding-right:.4rem}.sv-rowlabel b{font-size:1rem}.sv-rowlabel span{font-size:.74rem;opacity:.7}
.sv-cell{border:1px solid #e4e8f3;border-left-width:5px;border-radius:10px;padding:.65rem .8rem;background:#fff;box-shadow:0 1px 2px rgba(60,80,140,.06)}
.sv-cell.sv-s-on_track{border-left-color:#3aa675}.sv-cell.sv-s-watch{border-left-color:#e9b44c}.sv-cell.sv-s-off_track{border-left-color:#dc6b6b}.sv-cell.sv-s-no_data{border-left-color:#9aa3b5}
.sv-cell-top{display:flex;align-items:center;justify-content:space-between;gap:.5rem;margin-bottom:.35rem}
.sv-cell-val{font-size:1.6rem;font-weight:700;line-height:1}
.sv-lens{display:none;font-size:.75rem;font-weight:700;opacity:.75;margin-bottom:.15rem}
.sv-meter{position:relative;height:8px;border-radius:4px;background:#e8ecf6;margin:.3rem 0 .15rem;overflow:hidden}
.sv-meter-fill{height:100%;border-radius:4px}
.sv-tick{position:absolute;top:0;bottom:0;width:2px;background:rgba(128,128,128,.85)}
.sv-kpi{padding:.4rem 0 .45rem;border-bottom:1px solid #edf0f7}
.sv-kpi:last-child{border-bottom:none}
.sv-kpi-head{display:flex;justify-content:space-between;align-items:center;gap:.6rem;font-size:.88rem}
.sv-kpi-name{opacity:.92}
.sv-kpi-count{font-size:.8rem;font-weight:600;margin:.1rem 0 .3rem}
.sv-kpi-plain{font-size:.76rem;opacity:.65;margin:.15rem 0 .3rem;line-height:1.3}
.sv-kpi-val{display:inline-flex;align-items:center;gap:.35rem;font-weight:700;white-space:nowrap}
.sv-att{display:flex;justify-content:space-between;align-items:center;gap:.8rem;flex-wrap:wrap;padding:.55rem .1rem;border-bottom:1px solid #e8ecf6}
.sv-att-main{font-size:.9rem}
.sv-tags{display:flex;flex-wrap:wrap;gap:.3rem}
.sv-tag{display:inline-block;padding:.08rem .5rem;border:1px solid #d6ddf2;border-radius:6px;font-size:.74rem;background:#f0f3fc;color:#46528c;white-space:nowrap}
.sv-tag-new{margin-left:.5rem;border-style:dashed}
.sv-src{border:1px solid #e4e8f3;border-radius:12px;padding:.8rem 1rem;background:#fff;box-shadow:0 1px 2px rgba(60,80,140,.06);height:100%;box-sizing:border-box}
.sv-src-top{display:flex;justify-content:space-between;align-items:center;gap:.5rem}
.sv-err{margin-top:.45rem;padding:.35rem .5rem;border-radius:6px;background:#fcefef;font-size:.78rem}
.sv-strip{display:flex;flex-wrap:wrap;gap:3px;margin:.3rem 0}
.sv-day{display:inline-block;width:15px;height:15px;border-radius:3px;box-sizing:border-box;vertical-align:middle}
.sv-day-yes{background:#6b86e8}.sv-day-no{border:2px solid #6b86e8;background:transparent}.sv-day-none{width:7px;height:7px;border-radius:50%;background:rgba(128,128,128,.5);margin:4px}
.sv-h2{font-size:1.2rem;font-weight:700;margin:1.3rem 0 .15rem}
/* soft light surfaces: pastel accents and a faint wash in each status colour */
.sv-h1,.sv-h2{color:#2f3a5f}
.sv-tiles .sv-tile:nth-child(3n+2){border-top-color:#8fcfc4}.sv-tiles .sv-tile:nth-child(3n+3){border-top-color:#f0bf86}
.sv-cell.sv-s-on_track{background:linear-gradient(90deg,#eef8f2,#fff 65%)}.sv-cell.sv-s-watch{background:linear-gradient(90deg,#fdf6e4,#fff 65%)}
.sv-cell.sv-s-off_track{background:linear-gradient(90deg,#fcefef,#fff 65%)}.sv-cell.sv-s-no_data{background:linear-gradient(90deg,#f0f2f7,#fff 65%)}
[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-color:#e4e8f3!important;border-radius:14px!important;box-shadow:0 1px 3px rgba(60,80,140,.06)}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"]{background:#dde5fa;color:#2f3f86;font-weight:600}
.sv-verdict{background:#fff;border:1px solid #e4e8f3;border-left:6px solid #9aa3b5;border-radius:12px;padding:.9rem 1.2rem;margin:0 0 1rem;box-shadow:0 1px 2px rgba(60,80,140,.06)}
.sv-verdict p{margin:.15rem 0;font-size:.95rem}.sv-verdict-lead{font-size:1.15rem!important;font-weight:700;color:#2f3a5f}
.sv-verdict.sv-s-on_track{border-left-color:#3aa675;background:linear-gradient(90deg,#eef8f2,#fff 60%)}.sv-verdict.sv-s-watch{border-left-color:#e9b44c;background:linear-gradient(90deg,#fdf6e4,#fff 60%)}
.sv-verdict.sv-s-off_track{border-left-color:#dc6b6b;background:linear-gradient(90deg,#fcefef,#fff 60%)}
.sv-delta{font-size:.74rem;font-weight:600;margin-left:auto;margin-right:.7rem;white-space:nowrap}
.sv-delta-up{color:#2e8a5e}.sv-delta-down{color:#c4524f}.sv-delta-flat{color:#7b859b}
.sv-eng{padding:.45rem 0;border-bottom:1px solid #edf0f7}.sv-eng:last-child{border-bottom:none}
.sv-eng-head{display:flex;justify-content:space-between;align-items:center;gap:.6rem;font-size:.9rem}
.sv-advisor{margin:.9rem 0 .2rem;padding:.35rem .7rem;background:#eef2fb;border-radius:8px;font-size:.9rem}
.sv-act-head{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;margin:0 0 .5rem}.sv-act-head .sv-h2{margin:0}
.sv-act-text{font-size:.85rem;opacity:.8;margin:-.2rem 0 .6rem}
@media (max-width:800px){.sv-grid{grid-template-columns:1fr}.sv-gh{display:none}.sv-lens{display:block}.sv-rowlabel{padding-top:.6rem}}
@media (forced-colors:active){.sv-meter-fill{forced-color-adjust:none}.sv-cell{border-color:CanvasText}}
</style>
"""


def h2(text, sub=""):
    lede = f'<div class="sv-sub" style="margin-top:0">{e(sub)}</div>' if sub else ""
    return f'<div class="sv-h2">{e(text)}</div>{lede}'
