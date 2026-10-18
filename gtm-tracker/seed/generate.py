"""Dummy GTM data: a seeded DuckDB file with six planted stories (see STORIES). Every id starts DEMO-; nothing here is real.

Run:  python -m seed.generate out.duckdb
"""
import math
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SEED = 7
DEFAULT_AS_OF = date(2026, 10, 18)
WINDOW_DAYS = 365                                     # a year of history, so trends and month-on-month views have something to show
GROWTH = (0.75, 1.25)                                 # lead volume rises by this factor from the first day to the last (all campaigns, organic included)
PRICE_PER_SEAT = 3999
PROGRAM_AMOUNT = 500000                               # full-year program, from the Founder's Office email (Rs 5,00,000)
TRIAL_AMOUNT = PROGRAM_AMOUNT * 35 // 100            # trial program is 35% of the full-year fee (Rs 1,75,000)
STAGES = ["qualified", "discovery_set", "discovery_attended", "ambition_interview", "architect_session", "signed"]   # chain[i] is the chance of passing STAGES[i]
CITIES = ["Delhi", "Mumbai", "Bengaluru", "Pune", "Hyderabad", "Chennai", "Gurugram", "Kolkata"]
BROCHURE_LEADS_PER_DAY = 0.35                         # leads from the printed brochure: neither paid nor organic
# days a lead waits between one stage and the next: (min, max)
STAGE_GAP = {"review": (0, 1), "conveyed": (0, 1), "rejected": (0, 1), "nurture": (0, 2), "qualified": (0, 1), "discovery_set": (1, 3), "discovery_attended": (1, 4), "ambition_interview": (2, 6), "architect_session": (3, 8), "signed": (2, 10)}

STORIES = {
    "scale": "DEMO-C-PROG-SCALE", "fatigue": "DEMO-C-PROG-FATIGUE", "asset": "DEMO-C-PROG-ASSET", "landing": "DEMO-C-PROG-LP",
    "volume": "DEMO-C-WS-VOLUME", "workshop_ok": "DEMO-C-WS-OK", "decline": "DEMO-C-PROG-DECLINE", "new": "DEMO-C-PROG-NEW",
    "fatigue_ad_set": "DEMO-AS-FATIGUE-1", "weak_asset": "DEMO-AD-ASSET-3",
}

# Optional keys: launch = days before as_of that the campaign went live (no rows before that); lead_trend = (first, last) multiplier on its lead volume.
# Per-campaign profile: kind, short code, ad sets x ads, rupees per day, CPM, base CTR, expected leads per day,
# conditional chance of passing each stage in STAGES, landing page (bounce share, load seconds).
CAMPAIGNS = [
    dict(id=STORIES["scale"], short="SCALE", name="Program: parents of Class 10, lookalike", kind="program", sets=2, ads=3, spend=2500, cpm=180, ctr=0.021,
         leads=1.4, chain=[.72, .76, .86, .82, .82, .74], bounce=.30, load=1.9),
    dict(id=STORIES["fatigue"], short="FATIGUE", name="Program: founder story video", kind="program", sets=2, ads=3, spend=3500, cpm=260, ctr=0.018,
         leads=1.1, chain=[.40, .65, .75, .70, .70, .60], bounce=.34, load=2.2),
    dict(id=STORIES["asset"], short="ASSET", name="Program: student outcomes carousel", kind="program", sets=2, ads=3, spend=3000, cpm=240, ctr=0.016,
         leads=1.1, chain=[.45, .65, .75, .70, .70, .60], bounce=.36, load=2.4),
    dict(id=STORIES["landing"], short="LP", name="Program: roadmap quiz", kind="program", sets=1, ads=3, spend=2800, cpm=230, ctr=0.017,
         leads=0.8, chain=[.35, .60, .70, .65, .65, .55], bounce=.68, load=4.8),
    dict(id=STORIES["decline"], short="DECLINE", name="Program: Class 9 early-bird", kind="program", sets=2, ads=2, spend=2400, cpm=210, ctr=0.019,
         leads=1.6, lead_trend=(2.0, 0.3), chain=[.55, .70, .80, .70, .70, .60], bounce=.31, load=2.1),
    dict(id=STORIES["new"], short="NEW", name="Program: parent testimonials", kind="program", sets=1, ads=3, spend=2000, cpm=190, ctr=0.026,
         leads=1.0, launch=24, chain=[.60, .72, .82, .76, .76, .66], bounce=.29, load=2.0),
    dict(id=STORIES["volume"], short="WSVOL", name="Workshop: free-tips reels", kind="workshop", sets=2, ads=2, spend=2000, cpm=200, ctr=0.015,
         leads=2.8, chain=[.20, .40, .60, .50, .50, .30], bounce=.38, load=2.6),
    dict(id=STORIES["workshop_ok"], short="WSOK", name="Workshop: parent webinar", kind="workshop", sets=1, ads=3, spend=2200, cpm=220, ctr=0.019,
         leads=1.4, chain=[.35, .55, .70, .65, .65, .55], bounce=.33, load=2.3),
]
ORGANIC = dict(leads=0.9, chain=[.50, .70, .80, .75, .75, .70])
WORKSHOP_BUY_RATE = {STORIES["volume"]: .08, STORIES["workshop_ok"]: .20}


def _poisson(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _month_start(d):
    return d.replace(day=1)


def _month_add(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def _growth(day_index):
    return GROWTH[0] + (GROWTH[1] - GROWTH[0]) * day_index / (WINDOW_DAYS - 1)


def _decay(day_index, ad_set):
    """CTR multiplier for the fatigued ad set: flat, then falling to 0.45 over the last 60 days. 1 everywhere else."""
    if ad_set != STORIES["fatigue_ad_set"]:
        return 1.0
    t = max(0, day_index - (WINDOW_DAYS - 60)) / 60
    return 1.0 - 0.55 * t


def _frequency(rng, day_index, ad_set):
    if ad_set == STORIES["fatigue_ad_set"]:
        t = max(0, day_index - (WINDOW_DAYS - 60)) / 60
        return round(1.8 + 1.8 * t + rng.uniform(-.05, .05), 2)
    return round(rng.uniform(1.3, 2.2), 2)


def build(path, as_of=DEFAULT_AS_OF, seed=SEED):
    path = Path(path)
    if path.exists():
        path.unlink()
    rng = random.Random(seed)
    con = duckdb.connect(str(path))
    con.execute((ROOT / "sql" / "schema" / "gtm.sql").read_text())
    days = [as_of - timedelta(days=WINDOW_DAYS - 1 - i) for i in range(WINDOW_DAYS)]
    end_of_data = datetime.combine(as_of, time(23, 59, 59))

    campaigns, ad_sets, ads, ad_daily, ad_set_daily, landing = [], [], [], [], [], []
    leads, stages = [], []
    campaign_ads = {}
    lead_n = 0

    attrs = random.Random(seed + 1)          # lead attributes draw from their own stream, so adding them does not move the planted stories

    def attributes(n, source_lead):
        """(parent_name, student_name, grade, school, phone, city, utm_source, traffic_source): all generated, none real."""
        if source_lead == "paid_ads":
            utm = attrs.choices(["meta", "instagram"], [.6, .4])[0]
            traffic = "instagram" if utm == "instagram" else "facebook"
        else:
            utm = None
            traffic = "direct" if source_lead == "brochure" else attrs.choices(["google", "direct", "instagram"], [.5, .3, .2])[0]
        return (f"Demo Parent {n:05d}", f"Demo Student {n:05d}", attrs.choice(range(8, 13)), f"Demo School {attrs.randint(1, 14):02d}", f"+91 00000 {n:05d}",
                attrs.choice(CITIES), utm, traffic)

    def new_lead(source_lead, camp_id, set_id, ad_id, created, chain):
        """One lead walking the ClickUp path: Form Filled, Under Review, then Qualified or Rejected, Qualification Conveyed, the discovery call,
        then the ambition call, architect call and conversion. A lead that attends the discovery call but goes no further moves to nurture."""
        nonlocal lead_n
        lead_n += 1
        lead_id = f"DEMO-L-{lead_n:05d}"
        leads.append((lead_id, source_lead, camp_id, set_id, ad_id, created) + attributes(lead_n, source_lead))
        stages.append((lead_id, "lead", created))
        at = created
        def step(stage):
            nonlocal at
            lo, hi = STAGE_GAP[stage]
            at = at + timedelta(days=rng.randint(lo, hi), hours=rng.randint(0, 8), minutes=rng.randint(1, 59))      # at least a minute, so two stages never share a timestamp
            if at > end_of_data:
                return False
            stages.append((lead_id, stage, at))
            return True
        if not step("review"):
            return lead_id
        p = dict(zip(STAGES, chain))
        if rng.random() > p["qualified"]:
            step("rejected")
            return lead_id
        if not step("qualified") or not step("conveyed"):
            return lead_id
        for stage in ("discovery_set", "discovery_attended"):
            if rng.random() > p[stage] or not step(stage):
                return lead_id
        for stage in ("ambition_interview", "architect_session", "signed"):
            if rng.random() > p[stage]:
                if stage == "ambition_interview":
                    step("nurture")
                return lead_id
            if not step(stage):
                return lead_id
        return lead_id

    for c in CAMPAIGNS:
        campaigns.append((c["id"], c["name"], c["kind"]))
        ids = []
        for s in range(1, c["sets"] + 1):
            set_id = f"DEMO-AS-{c['short']}-{s}"
            ad_sets.append((set_id, c["id"], f"{c['name']} / audience {s}"))
            for a in range(1, c["ads"] + 1):
                n = (s - 1) * c["ads"] + a
                ad_id = f"DEMO-AD-{c['short']}-{n}"
                ads.append((ad_id, set_id, f"{c['short'].title()} asset {n}"))
                ids.append((ad_id, set_id))
        campaign_ads[c["id"]] = ids
        launch_day = as_of - timedelta(days=c["launch"]) if "launch" in c else None
        for i, day in enumerate(days):
            if launch_day and day < launch_day:
                continue
            set_impr, clicks_total, mult_sum = {}, 0, 0.0
            for ad_id, set_id in ids:
                weak = .35 if ad_id == STORIES["weak_asset"] else 1.0
                mult = _decay(i, set_id) * weak * rng.uniform(.9, 1.1)
                spend = c["spend"] / len(ids) * rng.uniform(.9, 1.1)
                impr = int(spend / c["cpm"] * 1000)
                clicks = int(impr * c["ctr"] * mult)
                ad_daily.append((ad_id, day, round(spend, 2), impr, clicks))
                set_impr[set_id] = set_impr.get(set_id, 0) + impr
                clicks_total += clicks
                mult_sum += _decay(i, set_id)
            for set_id, impr in set_impr.items():
                freq = _frequency(rng, i, set_id)
                ad_set_daily.append((set_id, day, int(impr / freq), freq))
            sessions = int(clicks_total * .85)
            bounces = int(sessions * min(.95, c["bounce"] * rng.uniform(.93, 1.07)))
            landing.append((c["id"], day, sessions, bounces, round(c["load"] * rng.uniform(.9, 1.1), 2)))
            lo, hi = c.get("lead_trend", (1.0, 1.0))
            expected = c["leads"] * (mult_sum / len(ids)) * _growth(i) * (lo + (hi - lo) * i / (WINDOW_DAYS - 1))      # fatigue lowers the leads too
            for _ in range(_poisson(rng, expected)):
                ad_id, set_id = rng.choice(ids)
                created = datetime.combine(day, time(rng.randint(7, 23), rng.randint(0, 59)))
                new_lead("paid_ads", c["id"], set_id, ad_id, created, c["chain"])
    for i, day in enumerate(days):
        for _ in range(_poisson(rng, ORGANIC["leads"] * _growth(i))):
            created = datetime.combine(day, time(rng.randint(7, 23), rng.randint(0, 59)))
            new_lead("organic", None, None, None, created, ORGANIC["chain"])
        for _ in range(_poisson(rng, BROCHURE_LEADS_PER_DAY * _growth(i))):
            created = datetime.combine(day, time(rng.randint(9, 19), rng.randint(0, 59)))
            new_lead("brochure", None, None, None, created, ORGANIC["chain"])

    # Revenue: one enrollment per signed lead, plus a few trials planted to renew inside the next 30 days.
    signed = sorted((at, lead_id) for lead_id, stage, at in stages if stage == "signed")
    enrollments, invoices = [], []
    def add_enrollment(lead_id, started, kind):
        n = len(enrollments) + 1
        eid, amount = f"DEMO-EN-{n:04d}", TRIAL_AMOUNT if kind == "trial_3m" else PROGRAM_AMOUNT
        enrollments.append((eid, f"DEMO-ST-{n:04d}", lead_id, kind, started, started + timedelta(days=90) if kind == "trial_3m" else None, amount))
        if started > as_of:                   # one invoice for the full fee at sign-up: the founder's email gives a price, not installments
            return
        never_pays = rng.random() < .04                             # a small share never pays
        pays_on = started + timedelta(days=rng.randint(0, 3))       # the rest pay within three days of the invoice
        paid = None if never_pays or pays_on > as_of else pays_on
        invoices.append([f"DEMO-INV-{len(invoices) + 1:04d}", eid, started, started + timedelta(days=7), amount, paid])
    for at, lead_id in signed:
        add_enrollment(lead_id, at.date(), "trial_3m" if rng.random() < .45 else "program")
    for offset in (84, 76, 70, 66):
        add_enrollment(None, as_of - timedelta(days=offset), "trial_3m")
    overdue = [inv for inv in invoices if inv[5] is not None and as_of - timedelta(days=45) <= inv[3] <= as_of - timedelta(days=5)]
    for inv in overdue[:3]:
        inv[5] = None                                       # planted: unpaid and past due

    # Workshops: fortnightly, alternating campaigns; seats bought by that campaign's recent leads.
    workshops, payments = [], []
    ws_campaigns = [STORIES["volume"], STORIES["workshop_ok"]]
    held = as_of - timedelta(days=3)
    held_dates = []
    while held >= days[0]:
        held_dates.append(held)
        held -= timedelta(days=14)
    for k, held_on in enumerate(sorted(held_dates)):
        camp = ws_campaigns[k % 2]
        wid = f"DEMO-WS-{k + 1:02d}"
        workshops.append((wid, camp, f"Fortnightly workshop {k + 1}", held_on))
        pool = [l for l in leads if l[2] == camp and held_on - timedelta(days=14) <= l[5].date() <= held_on]
        for lead in pool:
            if rng.random() < WORKSHOP_BUY_RATE[camp]:
                seats = rng.choice([1, 1, 1, 2])
                paid_at = datetime.combine(min(held_on, lead[5].date() + timedelta(days=rng.randint(0, 5))), time(rng.randint(8, 22), rng.randint(0, 59)))
                payments.append((f"DEMO-PAY-{len(payments) + 1:04d}", wid, lead[0], paid_at, seats, seats * PRICE_PER_SEAT))
    # Synthetic scenario for the workshop follow-up metric: a few workshop buyers later buy the full program, within 60 days of their seat.
    # Explicitly illustrative (ids DEMO-EN-WS-*), drawn from their own random stream so nothing above shifts, each paid once like every other enrollment.
    # The seats are bought in the default 90-day view's first 30 days, so every buyer has a complete 60-day follow-up on the as-of date.
    later = random.Random(seed + 2)
    enrolled_leads = {e[2] for e in enrollments if e[2]}
    for n, (campaign, count) in enumerate([(STORIES["workshop_ok"], 3), (STORIES["volume"], 1)]):
        owners = {w[0]: w[1] for w in workshops}
        pool = sorted({(p[3].date(), p[2]) for p in payments if p[2] and owners[p[1]] == campaign and p[2] not in enrolled_leads
                       and as_of - timedelta(days=89) <= p[3].date() <= as_of - timedelta(days=60)})
        assert len(pool) >= count, f"not enough workshop buyers for {campaign}"
        for paid_on, lead_id in later.sample(pool, count):
            k = len([e for e in enrollments if e[0].startswith("DEMO-EN-WS-")]) + 1
            started = paid_on + timedelta(days=later.randint(5, 40))
            enrollments.append((f"DEMO-EN-WS-{k:02d}", f"DEMO-ST-WS-{k:02d}", lead_id, "program", started, None, PROGRAM_AMOUNT))
            invoices.append([f"DEMO-INV-{len(invoices) + 1:04d}", f"DEMO-EN-WS-{k:02d}", started, started + timedelta(days=7), PROGRAM_AMOUNT, started + timedelta(days=later.randint(0, 3))])

    # Targets are dummy plan figures set a little above or below each month's cash, so the dashboard shows both ahead and behind months.
    # The current (partial) month's plan follows the average of the three months before it.
    cash = {}
    for inv in invoices:
        if inv[5] is not None:
            cash[_month_start(inv[5])] = cash.get(_month_start(inv[5]), 0) + inv[4]
    for p in payments:
        cash[_month_start(p[3].date())] = cash.get(_month_start(p[3].date()), 0) + p[5]
    targets, m, factors = [], _month_start(days[0]), [1.08, 0.94, 1.12, 0.90, 1.04, 0.97]
    while m < _month_start(as_of):
        targets.append((m, int(round(cash.get(m, 0) * factors[len(targets) % len(factors)], -4)) or 10000))
        m = _month_add(m, 1)
    last_three = [cash.get(_month_add(_month_start(as_of), -k), 0) for k in (1, 2, 3)]
    targets.append((_month_start(as_of), int(round(sum(last_three) / 3 * 1.05, -4))))

    for table, rows in [("campaigns", campaigns), ("ad_sets", ad_sets), ("ads", ads), ("ad_daily", ad_daily), ("ad_set_daily", ad_set_daily),
                        ("landing_page_daily", landing), ("leads", leads), ("lead_stages", stages), ("enrollments", enrollments), ("invoices", invoices),
                        ("workshops", workshops), ("workshop_payments", payments), ("revenue_targets", targets)]:
        if rows:
            frame = pd.DataFrame([tuple(r) for r in rows])      # one bulk insert per table: executemany is far slower
            con.register("frame", frame)
            con.execute(f"INSERT INTO {table} SELECT * FROM frame")
            con.unregister("frame")
    con.execute("INSERT INTO snapshot_meta VALUES (true, ?, ?)", [as_of, seed])
    con.close()
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "gtm.duckdb"))
