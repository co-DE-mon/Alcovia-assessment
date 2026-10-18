"""Seeded dummy data for the student tracker. Everything is fake and every id starts DEMO-.

build() is deterministic: the same seed and as_of give the same rows, and it never reads the real clock.
Schema: sql/schema/student.sql. Table plan: README.md#source-and-schema-reference. KPI definitions: README.md#kpi-catalogue.

Planted stories (tests/test_seed.py checks each one):
- 19 students enrolled; 7 stopped using the app 9 to 45 days ago; one left the program on 30 Sep; one joined 19 days ago.
- Advisor DEMO-ADV-3 lags on the monthly inputs and has the weakest-engaged students.
- DEMO-S09 has no career counsellor, so no career sessions are ever scheduled for them.
- The 22 Sep workshop was cancelled; the 8 Aug workshop was rated poorly.
- Every month one pod (D) has 4 students instead of 5; it is also the worst-rated pod.
- Wearable data is mostly absent: one Whoop student, one whose Whoop lapsed, three manual loggers, the rest nothing.
- DEMO-S01, the one active Whoop student, has a rough last week: low recovery, short sleep, high strain.
- The quiz is cancelled on three days; most focus sessions fail (as on the real test account).
- A ClickUp run failed on 20 Oct and an app run on 18 Oct (both recovered); Whoop has been partial since 22 Oct, so it is stale.
"""

import csv
import random
import tempfile
from collections import namedtuple
from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb
import yaml

from metrics import month_add, quarter_for

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AS_OF = date(2026, 10, 24)
HISTORY_DAYS = 90  # daily facts cover as_of - 89 days .. as_of
SUBJECTS = ["Maths", "Science", "English", "Social Science", "Hindi"]
EST_HOURS = {"Maths": 32.0, "Science": 28.0, "English": 20.0, "Social Science": 22.0, "Hindi": 14.0}
QUIZ_TOPICS = ["sports", "history", "logical reasoning", "brand logos", "general knowledge"]
PROFESSIONS = ["Product manager", "Doctor", "Architect", "Sports analyst", "Filmmaker", "Lawyer"]
POD_THEMES = ["Dreams", "Aspirations", "Fears", "Vulnerabilities"]
INDUSTRIES = ["Design", "Medicine", "Finance", "Film", "Law", "Technology", "Sports", "Journalism"]

Student = namedtuple("Student", "id num name grade adv cc e wearable last_active start left "
                                "wear_on wear_off cal_on cal_off")

# num, grade, advisor index, counsellor index (None = unassigned), engagement 0-1, wearable, days since last app use
_PROFILES = [
    (1, 10, 0, 0, 0.92, "whoop", 0), (2, 9, 0, 0, 0.80, "whoop", 0), (3, 11, 0, 1, 0.75, "manual", 0),
    (4, 10, 0, 1, 0.70, "manual", 0), (5, 12, 0, 0, 0.65, "manual", 0), (6, 8, 0, 0, 0.85, "none", 0),
    (7, 9, 1, 1, 0.78, "none", 0), (8, 10, 1, 0, 0.60, "none", 2), (9, 11, 1, None, 0.55, "none", 1),
    (10, 10, 1, 0, 0.50, "none", 4), (11, 12, 1, 1, 0.42, "none", 9), (12, 9, 1, 0, 0.38, "none", 12),
    (13, 10, 1, 1, 0.35, "none", 15), (14, 11, 2, 0, 0.30, "none", 20), (15, 8, 2, 1, 0.28, "none", 26),
    (16, 12, 2, 0, 0.25, "none", 33), (17, 9, 2, 1, 0.22, "none", 45), (18, 10, 2, 0, 0.40, "none", 3),
    (19, 10, 2, 1, 0.35, "none", 0), (20, 11, 2, 0, 0.30, "none", 0),
]
ADVISOR_DILIGENCE = [0.92, 0.82, 0.55]  # chance a monthly input is done; DEMO-ADV-3 lags
COUNSELLOR_DILIGENCE = 0.85
STORY_START = date(2026, 1, 5)  # students start 9 days apart from here, all before the history window


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v


def _insert(con, table, rows):
    """Bulk-load through a temporary CSV. Binding thousands of rows one by one takes seconds; COPY takes milliseconds."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{table}.csv"
        with open(path, "w", newline="") as f:
            csv.writer(f).writerows([[_fmt(v) for v in row] for row in rows])
        # an empty field is a NULL
        con.execute(f"COPY {table} FROM '{path}' (FORMAT csv, HEADER false)")


def _at(d, hour, minute=0):
    return datetime.combine(d, time(hour, minute))


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def quarter_of(as_of, cfg):
    """First day of the quarter containing as_of and its label."""
    first, _, label = quarter_for(as_of, cfg)
    return first, label


def study_hours_plan(s):
    """Weekday and weekend study hours a student has set; three students never set them [A54]."""
    return (None, None) if s.num in (13, 16, 17) else (2 + int(s.e * 3), 4 + int(s.e * 4))


def make_students(as_of):
    out = []
    for num, grade, adv, cc, e, wear, dormant in _PROFILES:
        start = as_of - timedelta(days=19) if num == 19 else STORY_START + timedelta(days=9 * num)
        left = date(2026, 9, 30) if num == 20 else None
        last = as_of - timedelta(days=dormant)
        wear_on = wear_off = None
        if num == 1:
            wear_on = date(2026, 8, 2)
        if num == 2:
            wear_on, wear_off = date(2026, 8, 10), as_of - timedelta(days=21)
        cal_on = start + timedelta(days=3) if num not in (13, 16) else None  # two never connected a calendar
        cal_off = last - timedelta(days=2) if dormant > 7 and cal_on else None
        out.append(Student(f"DEMO-S{num:02d}", num, f"Demo Student {num:02d}", grade, adv, cc, e, wear, last, start, left,
                           wear_on, wear_off, cal_on, cal_off))
    return out


class World:
    """Holds the rows being generated and the helpers shared by every fill function."""

    def __init__(self, rng, cfg, as_of):
        self.rng, self.cfg, self.as_of = rng, cfg, as_of
        self.now = datetime.combine(as_of, time(23, 59))
        self.first_day = as_of - timedelta(days=HISTORY_DAYS - 1)
        self.q_start, self.q_label = quarter_of(as_of, cfg)
        self.months = [month_add(as_of.replace(day=1), i - 2) for i in range(3)]  # last three calendar months: monthly activities
        self.qmonths = [month_add(self.q_start, i) for i in range(3)]             # the academic quarter's months: themes, syllabus
        self.students = make_students(as_of)
        self.events, self.att, self.attempts, self.fb = [], [], [], []
        self.fb_n = 0

    def enrolled(self, s, d):
        return s.start <= d and (s.left is None or s.left > d)

    def engaged(self, s, d):
        return self.enrolled(s, d) and d <= s.last_active

    def roster(self, d):
        return [s for s in self.students if self.enrolled(s, d)]

    def p_att(self, s, d, base, slope):
        return base + slope * s.e if self.engaged(s, d) else 0.04

    def status(self, planned, p_held):
        if planned > self.now:
            return "planned"
        return "held" if self.rng.random() < p_held else "cancelled"

    def ratings(self, quality, e, n=3):
        r = self.rng
        return [int(_clamp(round(quality + 0.8 * (e - 0.5) + r.gauss(0, 0.7)), 1, 5)) for _ in range(n)]

    def add_feedback(self, s, event_id, kind, quality, when, p_scale=1.0, one_question=False):
        r = self.rng
        if r.random() > (0.35 + 0.5 * s.e) * p_scale:
            return
        when = min(when + timedelta(minutes=r.randint(10, 2400)), self.now)
        q = self.ratings(quality, s.e, 1 if one_question else 3)
        q += [None] * (3 - len(q))
        got = [x for x in q if x is not None]
        self.fb_n += 1
        self.fb.append((f"DEMO-FB-{self.fb_n:05d}", s.id, event_id, kind, q[0], q[1], q[2],
                        round(sum(got) / len(got), 2), r.random() < 0.3, when))

    def run_event(self, kind, eid, title, planned, p_held, invitees, base, slope, *, group=None, owner=None,
                  source="clickup", fb=None, quality=3.8, fb_scale=1.0, one_question=False, forced=None,
                  post_after=None, outcome=None, nps=False):
        """Create an event and its attendance rows (and feedback for those who came). Returns (status, posted_on)."""
        r = self.rng
        status = forced or self.status(planned, p_held)
        posted = views = shares = None
        if post_after and status == "held":
            posted = planned.date() + timedelta(days=r.randint(*post_after))
            if posted > self.as_of:
                posted = None
            else:
                age = (self.as_of - posted).days
                views = int(r.uniform(150, 600) * (1 + age / 3.0) * (0.5 + r.random()))
                shares = int(views * r.uniform(0.02, 0.08))
        nps_score = round(_clamp(2 * quality + r.gauss(0, 0.4), 0, 10), 1) if nps and status == "held" else None
        self.events.append((eid, kind, title, planned, status, group, owner, posted, views, shares, source, nps_score))
        for s in invitees:
            came = None
            if status == "held":
                came = r.random() < self.p_att(s, planned.date(), base, slope)
            out = outcome(r) if (outcome and came) else None
            self.att.append((eid, s.id, True, came, out))
            if came and fb:
                self.add_feedback(s, eid, fb, quality, planned + timedelta(hours=1), fb_scale, one_question)
        return status, posted


def fill_staff_students(con, w):
    staff = [(f"DEMO-ADV-{i + 1}", f"Demo Advisor {i + 1}", "advisor") for i in range(3)]
    staff += [(f"DEMO-CC-{i + 1}", f"Demo Counsellor {i + 1}", "career_counsellor") for i in range(2)]
    _insert(con, "staff", staff)
    rows = []
    for s in w.students:
        rows.append((s.id, s.name, s.grade, "CBSE", f"DEMO-ADV-{s.adv + 1}",
                     None if s.cc is None else f"DEMO-CC-{s.cc + 1}", s.start, s.left,
                     "whoop" if s.wearable == "whoop" else "none", s.wear_on, s.wear_off, s.cal_on, s.cal_off, *study_hours_plan(s)))
    _insert(con, "students", rows)


def fill_daily(w):
    """8pm quiz, per day, for every enrolled student."""
    r, cfg = w.rng, w.cfg["quiz"]
    cancelled = {w.as_of - timedelta(days=n) for n in (55, 40, 17)}
    for i in range(HISTORY_DAYS):
        d = w.first_day + timedelta(days=i)
        planned = _at(d, cfg["start_hour"])
        eid = f"DEMO-QZ-{d:%Y%m%d}"
        status, _ = w.run_event("quiz", eid, QUIZ_TOPICS[i % len(QUIZ_TOPICS)], planned, 1.0, [], 0, 0, source="app_api",
                                forced="cancelled" if d in cancelled else None)
        for s in w.roster(d):
            started = status == "held" and w.engaged(s, d) and r.random() < 0.85 * s.e
            w.att.append((eid, s.id, True, started if status == "held" else None, None))
            if not started:
                continue
            late = r.random() > 0.85
            start = planned + timedelta(minutes=r.randint(16, 45) if late else r.randint(0, 14), seconds=r.randint(0, 59))
            done = r.random() < 0.92
            score = int(_clamp(round(10 * (0.35 + 0.4 * s.e + r.gauss(0, 0.12))), 0, 10)) if done else None
            w.attempts.append((eid, s.id, start, start + timedelta(minutes=r.randint(6, 12)) if done else None,
                               score, 10 if done else None))


def fill_focus(con, w):
    r, rows, n = w.rng, [], 0
    for i in range(HISTORY_DAYS):
        d = w.first_day + timedelta(days=i)
        for s in w.roster(d):
            if not w.engaged(s, d) or r.random() > s.e * 0.6:
                continue
            for _ in range(r.choice([1, 1, 2, 3])):
                n += 1
                planned = r.choice([25, 25, 30, 45, 60, 90])
                failed = r.random() < 0.75 - 0.5 * s.e
                reason = r.choices(["app_switch", "give_up", "abandoned", "interrupted"], [40, 40, 10, 10])[0] if failed else None
                actual = round(planned * r.uniform(0.1, 0.9), 1) if failed else float(planned)
                rows.append((f"DEMO-FS-{n:05d}", s.id, _at(d, r.randint(16, 21), r.randint(0, 59)), planned, actual,
                             "failed" if failed else "completed", reason))
    _insert(con, "focus_sessions", rows)


def fill_wearable(con, w):
    r, rows = w.rng, []
    for i in range(HISTORY_DAYS):
        d = w.first_day + timedelta(days=i)
        for s in w.students:
            if s.wearable == "whoop" and s.wear_on and d >= s.wear_on and (s.wear_off is None or d <= s.wear_off):
                if r.random() < 0.95:
                    rough = s.num == 1 and d > w.as_of - timedelta(days=7)  # DEMO-S01 has a rough last week
                    rows.append((s.id, d, round(_clamp(r.gauss(15 if rough else 11, 2 if rough else 3), 2, 20), 1),
                                 round(_clamp(r.gauss(27 if rough else 58, 8 if rough else 20), 5, 99)),
                                 round(_clamp(r.gauss(5.4 if rough else 7.2, 0.6 if rough else 0.9), 4.5, 9.5), 1), "whoop"))
            elif s.wearable == "manual" and w.engaged(s, d) and r.random() < 0.35:
                rows.append((s.id, d, None, None, round(_clamp(r.gauss(7.0, 1.0), 4, 10), 1), "manual"))
    _insert(con, "wearable_daily", rows)


def fill_todos(con, w):
    r, rows, n = w.rng, [], 0
    sources, weights = ["manual", "admin_assigned", "coaching_report", "session_action", "n8n"], [44, 19, 10, 9, 8]
    week = w.first_day
    while week <= w.as_of + timedelta(days=7):
        for s in w.students:
            if not w.enrolled(s, week):
                continue
            for _ in range(r.randint(2, 5)):
                n += 1
                due = week + timedelta(days=r.randint(0, 6))
                created = min(_at(due - timedelta(days=r.randint(1, 7)), r.randint(8, 20), r.randint(0, 59)), w.now)
                src = r.choices(sources, weights)[0]
                if src == "manual" and created.date() > s.last_active:
                    continue  # a student who stopped using the app creates no to-dos of their own
                if due > w.as_of:
                    status = "in_progress" if r.random() < 0.3 else "pending"
                    updated = min(created, w.now)
                else:
                    done = due <= s.last_active and r.random() < 0.35 + 0.6 * s.e
                    status = "done" if done else "missed"
                    late = r.random() < (1 - s.e) * 0.5
                    updated = _at(due + timedelta(days=r.randint(1, 3) if late else 0), r.randint(9, 22), r.randint(0, 59)) if done else created
                    updated = min(updated, w.now)
                rows.append((f"DEMO-TD-{n:05d}", s.id, src,
                             f"{r.choice(SUBJECTS)} task {n % 40 + 1}", due, status, created, updated))
        week += timedelta(days=7)
    _insert(con, "todos", rows)


def fill_monthly(w):
    r, rng_adv = w.rng, w.rng
    for mi, m in enumerate(w.months):
        roster = w.roster(min(m + timedelta(days=14), w.as_of))
        for k, day in enumerate((8, 22)):  # workshops: 2 a month [A17]
            planned = _at(m.replace(day=day), 17)
            poor = (m.month, day) == (8, 8)
            w.run_event("workshop", f"DEMO-WS-{m:%Y%m}-{k + 1}", PROFESSIONS[(mi * 2 + k) % len(PROFESSIONS)], planned, 1.0,
                        roster, 0.25, 0.7, fb="workshop", quality=2.6 if poor else 4.1, nps=True,
                        forced="cancelled" if (m.month, day) == (9, 22) else None)
        groups = [roster[i:i + 5] for i in range(0, len(roster), 5)]  # last pod is short: 4 students [A35]
        for g, members in enumerate(groups):
            planned = _at(m.replace(day=12 + g * 3), 16)
            w.run_event("pod", f"DEMO-POD-{'ABCD'[g]}-{m:%Y-%m}", POD_THEMES[(mi + g) % 4], planned, 0.93, members, 0.3, 0.65,
                        group=f"DEMO-POD-{'ABCD'[g]}", owner=f"DEMO-ADV-{members[0].adv + 1}", fb="pod",
                        quality=[4.3, 3.9, 3.4, 2.9][g % 4])
        for s in roster:
            sid = s.id
            w.run_event("mentor_call", f"DEMO-MC-{sid}-{m:%Y-%m}", f"Mentor call: {r.choice(INDUSTRIES)}",
                        _at(m.replace(day=r.randint(3, 27)), r.randint(16, 20)), 0.88, [s], 0.55, 0.4, fb="mentor", quality=4.0)
            for kind, count in w.cfg["sessions"]["policy_per_month"].items():
                if kind == "career" and s.cc is None:
                    continue  # DEMO-S09 has no counsellor, so no career sessions exist [A29]
                owner = f"DEMO-CC-{s.cc + 1}" if kind == "career" else f"DEMO-ADV-{s.adv + 1}"
                for n in range(count):
                    day = min(2 + n * (26 // count) + r.randint(0, 3), 28)
                    w.run_event(f"{kind}_session", f"DEMO-SS-{sid}-{kind[:3]}-{m:%Y%m}-{n + 1}", None,
                                _at(m.replace(day=day), r.randint(16, 19)), 0.9, [s], 0.6, 0.38, owner=owner,
                                source="app_api", fb="session", quality=3.8)
            w.run_event("branding_shoot", f"DEMO-BR-{sid}-{m:%Y-%m}", None, _at(m.replace(day=r.randint(2, 26)), r.randint(10, 17)),
                        0.7, [s], 0.6, 0.35, post_after=(3, 14))
        for i in range(0, len(roster) - 1, 2):  # peer sessions: advisor pairs two students [A18]
            pair = roster[i:i + 2]
            w.run_event("peer_session", f"DEMO-PS-{i // 2 + 1:02d}-{m:%Y-%m}", None, _at(m.replace(day=r.randint(4, 25)), 17),
                        0.8, pair, 0.6, 0.35, group=f"DEMO-PAIR-{i // 2 + 1:02d}", owner=f"DEMO-ADV-{pair[0].adv + 1}",
                        fb="session", quality=3.8, fb_scale=0.3)


def fill_quarterly(w):
    r, q = w.rng, w.q_start
    roster = w.roster(w.as_of)
    by_num = {s.num: s for s in w.students}
    for n, (day_off, host) in enumerate([(22, 1), (50, 6), (71, 3), (89, 8)]):  # podcasts, the last one is still planned
        planned = _at(q + timedelta(days=day_off), 15)
        status, posted = w.run_event("podcast", f"DEMO-PC-{n + 1}", None, planned, 0.95, [by_num[host]], 0.9, 0.0,
                                     fb="podcast_shoot", quality=4.4, fb_scale=1.5, post_after=(10, 16) if n != 1 else (26, 30))
        if posted and status == "held":
            w.add_feedback(by_num[host], f"DEMO-PC-{n + 1}", "podcast_post", 4.2, _at(posted, 12), 1.5)
    invited = [s for s in roster if s.num % 3 != 0 or s.num > 15][:12]  # about 12 students get a competition
    for n, day_off in enumerate((29, 57, 85)):
        grp = invited[n * 4:(n + 1) * 4]
        w.run_event("competition", f"DEMO-CP-{n + 1}", None, _at(q + timedelta(days=day_off), 10), 0.9, grp, 0.5, 0.45,
                    fb="competition", quality=3.6, forced="held" if n == 0 else None,
                    outcome=lambda rr: rr.choices(["entered", "shortlisted", "placed"], [60, 25, 15])[0])
    w.run_event("parent_workshop", "DEMO-PW-1", "Parent-child workshop", _at(date(2026, 9, 13), 11), 1.0, roster, 0.35, 0.55,
                fb="workshop", quality=4.3, fb_scale=0.6, forced="held")
    w.run_event("trip", "DEMO-TR-1", "Out-of-city trip", _at(date(2026, 10, 11), 7), 1.0, roster, 0.3, 0.65,
                fb="workshop", quality=4.5, forced="held")
    rev = list(reversed(roster))  # Alcovia organises social work in groups of 5 [A26]
    for g in range(4):
        members = rev[g * 5:(g + 1) * 5]
        for n in range(6):
            planned = _at(q + timedelta(days=4 + n * 15 + g), 15)
            w.run_event("social_work", f"DEMO-SW-{g + 1}-{n + 1}", f"Social work activity {n + 1}", planned, 0.9, members,
                        0.3, 0.65, group=f"DEMO-SW-{g + 1}", fb="social_work", quality=3.7, one_question=True, fb_scale=0.7)
    for s in roster:  # monthly roadmap check-in, not tied to an event
        for m in w.months:
            when = _at(m.replace(day=28), 12)
            if when <= w.now:
                w.add_feedback(s, None, "roadmap", 3.6, when, 0.6)


def maybe_done(w, s, p, due, max_late=4):
    """done_at for a roadmap item, or None. Nothing is done after the student went dormant."""
    r = w.rng
    if r.random() > p:
        return None
    done = _at(due - timedelta(days=r.randint(0, 6)) + timedelta(days=r.randint(1, max_late) if r.random() < (1 - s.e) * 0.4 else 0), r.randint(9, 20))
    done = min(done, w.now)
    return done if done.date() <= s.last_active else None


def fill_roadmaps(con, w):
    r, rows, n = w.rng, [], 0

    def item(s, roadmap, level, title, created, due, p):
        nonlocal n
        n += 1
        scale = 1.0 if due <= w.as_of else 0.45  # items not yet due are only partly done
        rows.append((f"DEMO-RM-{n:05d}", s.id, roadmap, level, title, created, due, maybe_done(w, s, p * scale, due), "clickup"))

    for s in w.students:
        if s.left is not None or s.num in (9, 15, 17):  # three students have no career roadmap yet [A29]
            pass
        else:
            item(s, "career", "annual", "Career roadmap", _at(date(2026, 8, 3), 10), date(2026, 12, 31), 0.05 + 0.2 * s.e)
            item(s, "career", "quarterly", "Explore three careers", _at(date(2026, 8, 3), 10), w.q_start + timedelta(days=91), 0.3 + 0.5 * s.e)
        for m in w.months:
            if not w.enrolled(s, m + timedelta(days=14)) and not w.enrolled(s, w.as_of):
                continue
            end = month_add(m, 1) - timedelta(days=1)
            for k in (1, 2):
                item(s, "personal", "monthly", f"Personal milestone {k}", _at(m, 9), end, 0.3 + 0.6 * s.e)
            item(s, "academic", "monthly", f"Chapter target {m:%b}", _at(m, 9), end, 0.3 + 0.6 * s.e)
        item(s, "academic", "quarterly", "Quarter syllabus target", _at(w.q_start, 9), w.q_start + timedelta(days=91), 0.2 + 0.4 * s.e)
        for m, title in zip(w.qmonths, ["Group plan approved", "Field activity done", "Impact report"]):
            item(s, "social_work", "monthly", title, _at(w.q_start, 9), month_add(m, 1) - timedelta(days=1), 0.3 + 0.65 * s.e)
    _insert(con, "roadmap_items", rows)


def fill_entrepreneurship(con, w):
    """The entrepreneurship theme [A61]: each active student builds a startup over the quarter, with three monthly milestones, and gets a one-tap rating prompt
    when a theme month ends [A21]. It uses a random stream of its own, so adding it moves no number of the existing dummy data."""
    r = random.Random(w.q_start.toordinal())
    items, fb = [], []
    for s in w.students:
        if s.left is not None:
            continue
        for k, (m, title) in enumerate(zip(w.qmonths, ["Startup idea approved", "Prototype built", "Final pitch given"])):
            due = month_add(m, 1) - timedelta(days=1)
            p = (0.3 + 0.65 * s.e) * (1.0 if due <= w.as_of else 0.45)
            done = None
            if r.random() <= p:
                done = min(_at(due - timedelta(days=r.randint(0, 6)), r.randint(9, 20)), w.now)
                done = done if done.date() <= s.last_active else None
            items.append((f"DEMO-RM-E{s.num:02d}{k + 1}", s.id, "entrepreneurship", "monthly", title, _at(w.q_start, 9), due, done, "clickup"))
            when = _at(due, 12)
            if when <= w.now and r.random() <= 0.3 + 0.5 * s.e:     # the one-tap rating: one star question, answered by some students
                rating = max(1, min(5, round(3.9 + 0.6 * (s.e - 0.5) + r.gauss(0, 0.8))))
                fb.append((f"DEMO-FB-E{s.num:02d}{k + 1}", s.id, None, "entrepreneurship", rating, None, None, float(rating), False, when))
    _insert(con, "roadmap_items", items)
    _insert(con, "feedback", fb)


def fill_summer(con, w):
    """Summer program closure [A66]: four application-support sessions across the quarter, every student invited, a one-tap rating for those who came, and the
    application result noted on the attendance row of the students who have submitted or been accepted. Own random stream, so no existing number moves."""
    r = random.Random(w.q_start.toordinal() + 1)
    events, att, fb = [], [], []
    state = {s.id: ("accepted" if r.random() < 0.25 + 0.2 * s.e else "submitted") if r.random() < 0.2 + 0.65 * s.e else None for s in w.students}
    for n, day in enumerate((10, 38, 66, 90), start=1):
        planned = _at(w.q_start + timedelta(days=day), 16)
        status = "planned" if planned > w.now else ("held" if r.random() < 0.9 or n == 1 else "cancelled")
        eid = f"DEMO-SP-{n}"
        events.append((eid, "summer_support", f"Application support session {n}", planned, status, None, None, None, None, None, "clickup", None))
        for s in w.roster(planned.date()):
            came = None if status != "held" else r.random() < 0.35 + 0.5 * s.e
            att.append((eid, s.id, True, came, state[s.id] if came else None))
            if came and r.random() < 0.3 + 0.5 * s.e:     # the one-tap rating
                rating = max(1, min(5, round(3.7 + 0.6 * (s.e - 0.5) + r.gauss(0, 0.8))))
                fb.append((f"DEMO-FB-S{n}{s.num:02d}", s.id, eid, "summer_support", rating, None, None, float(rating), False, min(planned + timedelta(hours=2), w.now)))
    _insert(con, "events", events)
    _insert(con, "event_attendance", att)
    _insert(con, "feedback", fb)


def fill_academics(con, w):
    r, chapters, hours, exams = w.rng, [], [], []
    prev_label = quarter_for(w.q_start - timedelta(days=1), w.cfg)[2]
    # (planned month, quarter label, stage a typical student reaches): the last month of the previous quarter, then the current quarter
    plan = [(month_add(w.q_start, -1), prev_label, 5.8), (w.qmonths[0], w.q_label, 4.6),
            (w.qmonths[1], w.q_label, 1.6), (w.qmonths[2], w.q_label, 0.3)]
    for s in w.students:
        if s.left is not None:
            continue
        for subj in SUBJECTS:
            for c in range(8):
                pm, label, typical = plan[c // 2]
                stage = int(_clamp(round(typical * (0.4 + 0.65 * s.e) + r.gauss(0, 0.8)), 0, 5))
                upd = _at(max(s.last_active - timedelta(days=r.randint(0, 25)), w.first_day), 18)
                chapters.append((s.id, f"DEMO-CH-{subj[:3].upper()}-{c + 1}", subj, label, pm, stage, upd))
            ratio = _clamp(0.35 + 0.9 * s.e + r.gauss(0, 0.15), 0.1, 1.6)
            snap = w.as_of  # weekly snapshots counted back from as_of, so the latest one is always as_of itself
            while snap >= w.q_start:
                if snap >= s.start:
                    frac = (min(snap, s.last_active) - w.q_start).days / 91
                    actual = 0.0 if (s.e < 0.3 and subj == "Hindi") else round(EST_HOURS[subj] * max(frac, 0) * ratio, 1)
                    hours.append((s.id, subj, w.q_label, snap, EST_HOURS[subj], actual))
                snap -= timedelta(days=7)
            for et in ("formative", "unit_test", "mid_term"):
                target = float(r.randint(68, 92))
                actual = None if et == "mid_term" else round(_clamp(target + r.gauss(-4 + 8 * (s.e - 0.5), 7), 20, 100), 1)
                exams.append((s.id, subj, et, target, actual))
    _insert(con, "chapter_progress", chapters)
    _insert(con, "study_hours", hours)
    _insert(con, "exam_targets", exams)


def fill_syllabus(con, w):
    """Daily syllabus completion: each student follows the cumulative pace (25% a quarter) times how engaged they are, and freezes when they stop."""
    r, rows = w.rng, []
    per_quarter = w.cfg["syllabus"]["quarter_target_pct"]

    def pace(day):
        first, end, label = quarter_for(day, w.cfg)
        return per_quarter * (int(label[-1]) - 1 + ((day - first).days + 1) / ((end - first).days + 1))

    for s in w.students:
        if s.left is not None:
            continue
        total = 55 + (s.num * 7) % 40
        ratio = _clamp(0.3 + 0.95 * s.e + r.gauss(0, 0.05), 0.2, 1.3)
        for i in range(HISTORY_DAYS):
            day = w.first_day + timedelta(days=i)
            if day >= s.start:
                rows.append((s.id, day, int(total * min(100.0, pace(min(day, s.last_active)) * ratio) / 100), total))
    _insert(con, "syllabus_daily", rows)


def fill_advisor_inputs(con, w):
    r, rows = w.rng, []
    for m in w.months:
        for s in w.students:
            if not w.enrolled(s, m + timedelta(days=14)) and not w.enrolled(s, w.as_of):
                continue
            for kind in w.cfg["advisor_input_kinds"]:
                if kind == "career_roadmap_reviewed":
                    p = 0.0 if s.cc is None else COUNSELLOR_DILIGENCE
                else:
                    p = ADVISOR_DILIGENCE[s.adv]
                p *= 0.97 if m < w.months[-1] else 0.7  # the current month is not finished
                rows.append((s.id, m, kind, r.random() < p, "clickup"))
    _insert(con, "advisor_inputs", rows)


def fill_ingest_log(con, w):
    r, rows, n = w.rng, [], 0
    lost = sum(1 for s in w.students if s.wearable == "whoop" and s.wear_off is not None)   # the Whoop students who disconnected: the ones the dashboard lists
    for back in range(13, -1, -1):
        d = w.as_of - timedelta(days=back)
        for source in ("app_api", "clickup", "whoop"):
            n += 1
            start = _at(d, 2, r.randint(0, 20))
            status, err, count = "ok", None, r.randint(40, 600)
            if source == "clickup" and back == 4:
                status, err, count = "failed", "ClickUp API rate limit (429) after 3 retries", None
            elif source == "whoop" and back <= 2:
                status, err = "partial", f"{lost} student{'s need' if lost != 1 else ' needs'} to reconnect Whoop (needsReconnect)"
            elif source == "app_api" and back == 6:
                status, err, count = "failed", "Bearer token expired and refresh failed; signed in again on the next run", None
            rows.append((f"DEMO-RUN-{n:03d}", source, start, start + timedelta(minutes=r.randint(1, 6)), status, count, err))
    _insert(con, "ingest_log", rows)


def build(db_path, seed=42, as_of=DEFAULT_AS_OF):
    """Create the database from sql/schema/student.sql and fill all 16 tables. Returns the path."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    w = World(random.Random(seed), cfg, as_of)
    con = duckdb.connect(str(path))
    con.execute((ROOT / "sql" / "schema" / "student.sql").read_text())
    con.execute((ROOT / "sql" / "schema" / "macros.sql").read_text())
    fill_staff_students(con, w)
    fill_daily(w)
    fill_monthly(w)
    fill_quarterly(w)
    _insert(con, "events", w.events)
    _insert(con, "event_attendance", w.att)
    _insert(con, "quiz_attempts", w.attempts)
    _insert(con, "feedback", w.fb)
    fill_focus(con, w)
    fill_wearable(con, w)
    fill_todos(con, w)
    fill_roadmaps(con, w)
    fill_entrepreneurship(con, w)
    fill_summer(con, w)
    fill_academics(con, w)
    fill_syllabus(con, w)
    fill_advisor_inputs(con, w)
    fill_ingest_log(con, w)
    con.close()
    return path
