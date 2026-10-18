/* normalise.js: the mapping step of the student-app-daily-poll workflow.
 *
 * Pure: no network, no database and no clock (the run time is passed in), so it is unit tested under plain Node (tests/normalise.test.js) and
 * the same text is embedded in the workflow's two Code nodes by build/build.py. Edit this file, never the generated JSON.
 *
 * What it does with the student app's responses:
 *   - converts UTC timestamps to IST (+05:30), because the schema stores IST;
 *   - maps every status word explicitly and REJECTS an unknown one instead of guessing, because one bad value would otherwise fail the
 *     whole table batch at the database CHECK constraint (a reject is logged and the rest of the rows still load) [A43][A52];
 *   - removes duplicate keys inside one payload, because INSERT .. ON CONFLICT cannot touch the same row twice in one statement;
 *   - treats a failed or truncated response as a failed source, never as "no rows".
 * Assumption numbers refer to student-tracker/README.md#assumption-reference-index.
 */
'use strict';

const IST_OFFSET_MS = 330 * 60 * 1000;

// Primary key of each table, in the order build/build.py uses for ON CONFLICT. A unit test checks this against sql/postgres-schema.sql.
const KEYS = {
  staff: ['staff_id'],
  students: ['student_id'],
  study_hours: ['student_id', 'subject', 'quarter', 'as_of'],
  focus_sessions: ['session_id'],
  todos: ['todo_id'],
  events: ['event_id'],
  event_attendance: ['event_id', 'student_id'],
  syllabus_daily: ['student_id', 'day'],
  wearable_daily: ['student_id', 'day'],
  roadmap_items: ['item_id'],
};
const TABLE_ORDER = Object.keys(KEYS);

// The app's words, compared after lower-casing and dropping spaces, underscores and hyphens: "InProgress", "in_progress" and "In Progress" match.
const norm = (s) => String(s).toLowerCase().replace(/[\s_-]/g, '');
const FOCUS_STATUS = { completed: 'completed', failed: 'failed' };
const FOCUS_NOT_FINAL = new Set(['running', 'active', 'started', 'inprogress']); // still running: skipped, loaded when it ends
const FAIL_REASON = new Set(['give_up', 'app_switch', 'abandoned', 'interrupted']);
const TODO_STATUS = { done: 'done', pending: 'pending', inprogress: 'in_progress', missed: 'missed' };
const TODO_SOURCE = new Set(['manual', 'admin_assigned', 'coaching_report', 'session_action', 'n8n']);
const SESSION_KIND = {
  academic: 'academic_session', career: 'career_session', personal: 'personal_session', mindset: 'mindset_session',
  deepwork: 'deep_work_session', mentor: 'mentor_call', workshop: 'workshop', podsession: 'pod',
};
const ATTENDANCE = { present: true, absent: false, upcoming: null }; // A52
const GOAL_ROADMAP = { career: 'career', personal: 'personal', academic: 'academic', venture: 'entrepreneurship' }; // A50
const GOAL_STATUS = new Set(['notstarted', 'inprogress', 'achieved']);

class Reject extends Error {}
const must = (cond, message) => { if (!cond) throw new Reject(message); };
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const text = (v) => (typeof v === 'string' ? v.trim() : '');
const pad = (n) => String(n).padStart(2, '0');

/** Milliseconds for an ISO timestamp that carries a zone (Z or +hh:mm); null for anything else, so a zone-less value is never read as local time. */
function instant(v) {
  if (typeof v !== 'string') return null;
  const match=/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})$/.exec(v);
  if (!match || !validDay(match[1]) || Number(match[2])>23 || Number(match[3])>59 || Number(match[4])>59) return null;
  const t=Date.parse(v);return Number.isFinite(t)?t:null;
}
function validDay(value) {
  if(typeof value!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const parsed=Date.parse(value+'T00:00:00Z');
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0,10)===value;
}
function ist(ms) {
  const d = new Date(ms + IST_OFFSET_MS);
  return { date: `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`, time: `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}` };
}
const toIst = (v) => { const t = instant(v); if (t === null) return null; const p = ist(t); return `${p.date} ${p.time}`; };
const istDate = (v) => { const t = instant(v); return t === null ? null : ist(t).date; };
const plainDate = value => validDay(value)?value:null;

// Persist classifications, not untrusted upstream message bodies: arbitrary text may contain credentials.
const errorText = (error) => {
  const raw=typeof error==='string'?error:error && typeof error==='object'?error.message || error.description:'';
  const message=typeof raw==='string'?raw.trim():'';
  if(!message)return 'unknown error';
  if(/Failed query:/i.test(message))return 'the database rejected the write (details omitted)';
  const safe=['Authorization failed','schedule activation failed','success=false','no response','no result from the database'];
  if(safe.includes(message))return message;
  if(/^node Fetch (profile|wearable status|time budget|focus today|todos|sessions|syllabus history|wellness history|annual goals|quarterly goals) did not run$/.test(message))return message;
  if(/relation .*does not exist/i.test(message))return 'database relation unavailable';
  if(/timeout|timed out/i.test(message))return 'request timed out';
  const status=message.match(/\b([45]\d{2})\b/);
  return status?'HTTP '+status[1]+' request failed':'request failed (details omitted)';
};

/**
 * One source's n8n items -> {data} or {error}. n8n turns a bare JSON list into one item per element, wraps nothing for single objects, and with
 * "continue on error" emits {error: ...}. The app answers {success, data, meta?}; paged endpoints send one such item per page.
 */
function unwrap(items) {
  if (!Array.isArray(items)) return { error: 'no response' };
  const live = items.filter((i) => i && typeof i === 'object' && Object.keys(i).length > 0);
  if (live.length === 0) return { data: [] };
  const failed = live.find((i) => i.error || i.success === false);
  if (failed) return { error: errorText(failed.error || 'success=false') };
  if (live.every((i) => 'success' in i && 'data' in i)) {
    const pages = live.map((i) => i.data);
    const data = pages.length === 1 ? pages[0] : pages.every(Array.isArray) ? [].concat(...pages) : pages;
    const totals=live.map(i=>i.meta?.total).filter(value=>value!==undefined);
    if(totals.some(value=>!Number.isInteger(value) || value<0) || new Set(totals).size>1)return {error:'inconsistent pagination totals'};
    const total=totals[0];
    if(total!==undefined && Array.isArray(data)) {
      // Paged app records use stable id (sessions/goals), or date (syllabus history).
      const identities=data.map(row=>row && typeof row==='object'?(row.id??row.date):undefined);
      const count=identities.every(key=>typeof key==='string' && key)?new Set(identities).size:data.length;
      if(count<total)return {error:`truncated: ${count} of ${total} unique rows received`};
      if(count>total)return {error:'inconsistent pagination total versus received rows'};
    }
    return { data };
  }
  return { data: live };
}
// A single-object endpoint arrives wrapped ({success, data: {...}}) or bare, and n8n may hand either over as a one-element list.
const one = (d) => (Array.isArray(d) ? (d.length === 1 ? d[0] : null) : d);
const list = (x) => (Array.isArray(x) ? x : x === null || x === undefined ? [] : [x]);

/**
 * input = { runAt: ISO timestamp, sources: { signin, me, whoop, timeBudget, focus, todos, sessions, syllabus, wellness, annual, quarterly } } where each
 * source is the array of item.json values the matching HTTP node produced.
 * Returns { status, rows: {table: [row]}, counts, rejects, failedSources, duplicates, skipped, rowsTotal, note, runAtIst, today }.
 */
function normalise(input) {
  const runMs = instant(input.runAt);
  if (runMs === null) throw new Error('runAt must be an ISO timestamp with a zone');
  const now = ist(runMs);
  const today = now.date;
  const runAtIst = `${now.date} ${now.time}`;
  const out = { tables: {}, rejects: [], failedSources: [], duplicates: 0, skipped: 0, fatal: null };
  TABLE_ORDER.forEach((t) => { out.tables[t] = new Map(); });

  const src = (name) => {
    const r = unwrap((input.sources || {})[name]);
    if (!r.error && name === 'focus' && !Array.isArray(one(r.data)?.sessions)) r.error = 'invalid focus response: sessions must be an array';
    if (r.error) { out.failedSources.push({ source: name, error: r.error }); return null; }
    return r.data;
  };
  const put = (table, row) => {
    const key = KEYS[table].map((k) => String(row[k])).join('\u0001');
    if (out.tables[table].has(key)) out.duplicates += 1;
    out.tables[table].set(key, row); // the later copy wins
  };
  const attempt = (table, id, build) => {
    try { const row = build(); if (row) put(table, row); } catch (e) {
      if (!(e instanceof Reject)) throw e;
      out.rejects.push({ table, id: id === undefined || id === null ? null : String(id), reason: e.message });
    }
  };

  const signinData = src('signin');
  const me = one(src('me'));
  const signed = one(signinData);
  const user = signed && signed.user ? signed.user : {};
  if (!me || !text(me.id)) {
    out.fatal = 'cannot identify the student: /users/me returned no id';
    return finish(out, today, runAtIst);
  }
  const studentId = me.id;

  // students and staff
  const whoop = one(src('whoop'));
  const tb = one(src('timeBudget'));
  attempt('students', studentId, () => {
    must(whoop, 'wearable status unavailable, so the student row is skipped this run');
    must(text(me.name), 'name missing');
    must(Number.isInteger(user.grade) && user.grade >= 8 && user.grade <= 12, `grade missing or outside 8-12: ${user.grade}`);
    must(text(me.advisorId), 'advisor_id missing');
    const start = istDate(me.programStartDate);
    must(start, 'program_start_date missing or not an ISO timestamp with a zone');
    const connected = whoop.isConnected === true;
    const hours = (v) => (isNum(v) && v >= 0 ? Math.round(v) : null);
    return {
      student_id: studentId, name: me.name.trim(), grade: user.grade, board: text(me.board) || text(user.board) || null,
      advisor_id: me.advisorId, career_counsellor_id: text(me.careerCounselorId) || null, program_start_date: start, left_on: null,
      wearable: connected ? 'whoop' : 'none',
      wearable_connected_on: connected ? today : null, // the database keeps the first date it ever saw [A45]
      wearable_disconnected_on: connected ? null : today,
      calendar_connected_on: null, calendar_disconnected_on: null, // no calendar status call yet: the database keeps what it has
      weekday_study_hours: tb ? hours(tb.weekdayStudyHours) : null, weekend_study_hours: tb ? hours(tb.weekendStudyHours) : null,
    };
  });
  for (const [role, person] of [['advisor', me.advisor], ['career_counsellor', me.careerCounselor]]) {
    if (!person) continue;
    attempt('staff', person.id, () => {
      must(text(person.id) && text(person.name), `${role} without an id or a name`);
      return { staff_id: person.id, name: person.name.trim(), role };
    });
  }

  // study hours: the quarter that contains today
  if (tb) {
    const quarter = list(tb.quarters).find((q) => {
      const s = instant(q && q.dateRange && q.dateRange.start);
      const e = instant(q && q.dateRange && q.dateRange.end);
      return s !== null && e !== null && s <= runMs && runMs <= e;
    });
    if (!quarter) out.rejects.push({ table: 'study_hours', id: null, reason: 'no quarter contains today' });
    for (const s of quarter ? list(quarter.subjects) : []) {
      attempt('study_hours', s && s.subjectName, () => {
        must(text(s && s.subjectName), 'subject name missing');
        must(text(tb.academicYear) && text(quarter.quarterName), 'academic year or quarter name missing');
        must(isNum(s.totalEstHours) && s.totalEstHours >= 0, 'totalEstHours missing or negative');
        must(isNum(s.totalActualHours) && s.totalActualHours >= 0, 'totalActualHours missing or negative');
        return { student_id: studentId, subject: s.subjectName.trim(), quarter: `${tb.academicYear}-${quarter.quarterName}`, as_of: today,
                 estimated_hours: s.totalEstHours, actual_hours: s.totalActualHours };
      });
    }
  }

  // focus sessions: the app only lists today's, so a missed day cannot be rebuilt at session level [A47]
  const focus = one(src('focus'));
  for (const s of focus ? list(focus.sessions) : []) {
    const word = norm(s && s.status);
    if (FOCUS_NOT_FINAL.has(word)) { out.skipped += 1; continue; }
    attempt('focus_sessions', s && s.id, () => {
      must(text(s && s.id), 'session id missing');
      must(FOCUS_STATUS[word], `unknown focus status: ${s.status}`);
      const started = toIst(s.startTime);
      must(started, 'startTime missing or not an ISO timestamp with a zone');
      must(isNum(s.durationMinutes) && s.durationMinutes >= 0, 'durationMinutes missing or negative');
      const reason = s.failReason === null || s.failReason === undefined ? null : String(s.failReason).toLowerCase();
      must(reason === null || FAIL_REASON.has(reason), `unknown fail reason: ${s.failReason}`);
      const status = FOCUS_STATUS[word];
      return { session_id: s.id, student_id: studentId, started_at: started, planned_minutes: null, actual_minutes: s.durationMinutes,
               status, fail_reason: status === 'failed' ? reason : null };
    });
  }

  // to-dos
  for (const t of list(src('todos'))) {
    attempt('todos', t && t.id, () => {
      must(text(t && t.id), 'todo id missing');
      must(text(t.title), 'title missing');
      const status = TODO_STATUS[norm(t.status)];
      must(status, `unknown todo status: ${t.status}`);
      must(TODO_SOURCE.has(String(t.source)), `unknown todo source: ${t.source}`);
      const due = istDate(t.dueDate), created = toIst(t.createdAt), updated = toIst(t.updatedAt);
      must(due && created && updated, 'dueDate, createdAt or updatedAt missing or not an ISO timestamp with a zone');
      return { todo_id: t.id, student_id: studentId, source: t.source, title: t.title.trim(), due_date: due, status, created_at: created, updated_at: updated };
    });
  }

  // sessions: events, and this student's attendance
  for (const s of list(src('sessions'))) {
    attempt('events', s && s.id, () => {
      must(text(s && s.id), 'session id missing');
      const kind = SESSION_KIND[norm(s.sessionType)];
      must(kind, `unknown session type: ${s.sessionType}`);
      const planned = toIst(s.startTime);
      must(planned, 'startTime missing or not an ISO timestamp with a zone');
      const startMs = instant(s.startTime);
      const status = s.cancelledAt ? 'cancelled' : startMs < runMs ? 'held' : 'planned';
      const clickup = Object.keys(s).some((k) => /^clickup.*TaskId$/.test(k) && s[k]);
      const nps = isNum(s.workshopNpsScore) && s.workshopNpsScore >= 0 && s.workshopNpsScore <= 10 ? s.workshopNpsScore : null;
      return { event_id: s.id, kind, title: text(s.name) || null, planned_for: planned, status, group_id: null, owner_staff_id: text(s.createdById) || null,
               posted_on: null, views: null, shares: null, source: clickup ? 'clickup' : 'app_api', nps_score: nps };
    });
    for (const p of list(s && s.participants).filter((x) => x && x.userId === studentId)) {
      attempt('event_attendance', s.id, () => {
        const key = norm(p.status);
        must(Object.prototype.hasOwnProperty.call(ATTENDANCE, key), `unknown attendance status: ${p.status}`);
        return { event_id: s.id, student_id: studentId, invited: true, attended: ATTENDANCE[key], outcome: null };
      });
    }
  }

  // syllabus history (the request asks for the last few days, so a missed run heals itself)
  for (const h of list(src('syllabus'))) {
    attempt('syllabus_daily', h && h.date, () => {
      const day = plainDate(h && h.date);
      must(day, 'date missing or not YYYY-MM-DD');
      must(Number.isInteger(h.chaptersCompleted) && h.chaptersCompleted >= 0 && Number.isInteger(h.totalChapters) && h.totalChapters >= 0, 'chapter counts missing or negative');
      must(h.chaptersCompleted <= h.totalChapters, 'more chapters completed than exist');
      return { student_id: studentId, day, chapters_completed: h.chaptersCompleted, total_chapters: h.totalChapters };
    });
  }

  // wellness history: Whoop days only. Strain and recovery come straight from the app; sleep is the three stage durations summed, and only when all
  // three are present (a missing stage is an unknown night, never a short one). Manual days carry no usable reading in this endpoint, so they are skipped.
  const wellness = src('wellness');
  const wellnessRows = wellness === null ? [] : one(wellness) && Array.isArray(one(wellness).history) ? one(wellness).history : null;
  if (wellnessRows === null) out.failedSources.push({ source: 'wellness', error: 'invalid wellness response: history must be an array' });
  for (const w of wellnessRows || []) {
    attempt('wearable_daily', w && w.date, () => {
      const day = plainDate(w && w.date);
      must(day, 'date missing or not YYYY-MM-DD');
      must(['WHOOP', 'MANUAL'].includes(w.dataSource), `unknown data source: ${w.dataSource}`);
      if (w.dataSource === 'MANUAL') return null;
      const within = (v, hi, label) => {
        if (v === null || v === undefined) return null;
        must(isNum(v) && v >= 0 && v <= hi, `${label} outside 0-${hi}: ${v}`);
        return v;
      };
      const stages = ['sleepStageLightMs', 'sleepStageDeepMs', 'sleepStageRemMs'].map((k) => w[k]);
      must(stages.every((v) => v === null || v === undefined || (typeof v === 'string' && /^\d+$/.test(v))), 'sleep stage is not a millisecond count');
      const sleep = stages.every((v) => typeof v === 'string') ? within(stages.reduce((a, v) => a + Number(v), 0) / 3600000, 24, 'sleep hours') : null;
      const row = { student_id: studentId, day, strain: within(w.dayStrain, 21, 'strain'), recovery_pct: within(w.recoveryScore, 100, 'recovery'), sleep_hours: sleep, data_source: 'whoop' };
      if (row.strain === null && row.recovery_pct === null && row.sleep_hours === null) return null;
      return row;
    });
  }

  // roadmap items = goals. The app gives no completion time for quarterly and monthly goals, so done_at is the first run that sees "Achieved"; the
  // database keeps the first value, and created_at is the first run that saw the goal [A50]. Some goals have no due date: they are loaded with a
  // NULL due_date, so they count as having a roadmap but can never be late [A58].
  const goal = (level, id, categoryWord, title, due, statusWord, createdAt) => attempt('roadmap_items', `${level}:${id}`, () => {
    must(text(id), 'goal id missing');
    const roadmap = GOAL_ROADMAP[norm(categoryWord)];
    must(roadmap, `unknown goal category: ${categoryWord}`);
    must(GOAL_STATUS.has(norm(statusWord)), `unknown goal status: ${statusWord}`);
    return { item_id: `${level}:${id}`, student_id: studentId, roadmap, level, title: text(title) || `${roadmap} ${level} goal`, created_at: createdAt || runAtIst,
             due_date: due, done_at: norm(statusWord) === 'achieved' ? runAtIst : null, source: 'app_api' };
  });
  for (const a of list(src('annual'))) {
    goal('annual', a && a.id, a && a.category, a && a.title, Number.isInteger(a && a.year) ? `${a.year}-12-31` : null, a && a.status, toIst(a && a.createdAt)); // A58
  }
  for (const g of list(src('quarterly'))) {
    const category = g && g.category && g.category.type;
    goal('quarterly', g && g.id, category, g && g.description, istDate(g && g.dueDate), g && g.status, null);
    for (const m of list(g && g.monthlyGoals)) goal('monthly', m && m.id, category, m && m.description, istDate(m && m.dueDate), m && m.status, null);
  }

  return finish(out, today, runAtIst);
}

function finish(out, today, runAtIst) {
  const rows = {};
  const counts = {};
  let rowsTotal = 0;
  for (const t of TABLE_ORDER) { rows[t] = [...out.tables[t].values()]; counts[t] = rows[t].length; rowsTotal += rows[t].length; }
  const status = out.fatal ? 'failed' : out.failedSources.length || out.rejects.length ? 'partial' : 'ok';
  const parts = [];
  if (out.fatal) parts.push(out.fatal);
  if (out.failedSources.length) parts.push(`failed sources: ${out.failedSources.map((f) => `${f.source} (${f.error})`).join('; ')}`);
  if (out.rejects.length) {
    const per = {};
    out.rejects.forEach((r) => { per[r.table] = (per[r.table] || 0) + 1; });
    const by = Object.entries(per).map(([t, c]) => `${t} ${c}`).join(', ');
    parts.push(`${out.rejects.length} rows rejected (${by}), for example ${out.rejects.slice(0, 3).map((r) => `${r.table} ${r.id}: ${r.reason}`).join('; ')}${out.rejects.length > 3 ? '; ...' : ''}`);
  }
  return { status, rows, counts, rejects: out.rejects, failedSources: out.failedSources, duplicates: out.duplicates, skipped: out.skipped, rowsTotal,
           note: parts.join(' | ').slice(0, 900) || null, runAtIst, today };
}

/**
 * Final status and the ingest_log row, from the normaliser's result and what the database said about each table batch.
 * tableResults[i] is the Postgres node's item for tables[i]: {upserted: n} on success, {error: ...} on failure.
 */
function summarise({ run, tables, tableResults, runId, finishedAt }) {
  const fin = instant(finishedAt);
  if (fin === null) throw new Error('finishedAt must be an ISO timestamp with a zone');
  const failed = [];
  let upserted = 0;
  tables.forEach((t, i) => {
    const r = tableResults[i];
    if (!r || r.error || !isNum(Number(r.upserted))) failed.push(`${t.table}: ${errorText((r && r.error) || 'no result from the database')}`);
    else upserted += Number(r.upserted);
  });
  const real = tables.filter((t) => t.table !== 'none');
  let status = run.status;
  if (failed.length) status = real.length && failed.length >= real.length ? 'failed' : 'partial';
  const note = [run.note, failed.length ? `database errors: ${failed.join('; ')}` : null].filter(Boolean).join(' | ').slice(0, 1000) || null;
  const f = ist(fin);
  return { run_id: runId, source: 'app_api', started_at: run.runAtIst, finished_at: `${f.date} ${f.time}`, status, rows_upserted: upserted, error: status === 'ok' ? null : note };
}

const api = { normalise, summarise, unwrap, toIst, istDate, KEYS, TABLE_ORDER };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
