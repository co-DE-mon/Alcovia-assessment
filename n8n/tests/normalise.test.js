// Unit tests for code/normalise.js. Run:  node --test tests/*.test.js     (plain Node 20+, no packages)
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { normalise, summarise, unwrap, toIst, istDate, KEYS } = require('../code/normalise.js');

const fx = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
// What the HTTP nodes would hand over: a bare list becomes one item per element, a wrapped answer stays one item.
const asItems = (body) => (Array.isArray(body) ? body : [body]);
const RUN_AT = '2026-10-17T20:30:00.000Z'; // 18 Oct 2026, 02:00 IST

function sources(over = {}) {
  const todos = fx('todos.json');
  return {
    signin: [fx('signin.json')], me: [fx('me.json')], whoop: [fx('whoop_status.json')], timeBudget: [fx('time_budget.json')], focus: [fx('focus_today.json')],
    todos: asItems(todos.data), sessions: [fx('sessions.json')], syllabus: [fx('syllabus_history.json')], wellness: [fx('wellness_history.json')], annual: [fx('annual_goals.json')], quarterly: [fx('quarterly_goals.json')],
    ...over,
  };
}
const run = (over) => normalise({ runAt: RUN_AT, sources: sources(over) });
const reasons = (r, table) => r.rejects.filter((x) => x.table === table).map((x) => x.reason);

test('time zone: UTC becomes IST and the date moves when the UTC time is after 18:30', () => {
  assert.equal(toIst('2026-10-17T17:40:54.427Z'), '2026-10-17 23:10:54');
  assert.equal(istDate('2026-10-17T18:29:59Z'), '2026-10-17');
  assert.equal(istDate('2026-10-17T18:30:00Z'), '2026-10-18');
  assert.equal(istDate('2026-04-09T00:00:00.000Z'), '2026-04-09'); // 05:30 IST, same day
  assert.equal(toIst('2026-10-17T23:10:54+05:30'), '2026-10-17 23:10:54'); // an explicit offset is honoured
});

test('a timestamp without a zone is never read as local time', () => {
  assert.equal(toIst('2026-10-17T17:40:54'), null);
  assert.equal(toIst('2026-10-17'), null);
  assert.equal(toIst(null), null);
  assert.equal(toIst(1760000000000), null);
});

test('the real-shaped fixtures load cleanly into every table', () => {
  const r = run();
  assert.equal(r.status, 'ok', r.note);
  assert.deepEqual(r.rejects, []);
  assert.deepEqual(r.failedSources, []);
  const c = r.counts;
  assert.equal(c.students, 1); assert.equal(c.staff, 1); assert.equal(c.todos, 30); assert.equal(c.events, 40);
  assert.equal(c.focus_sessions, 13); assert.ok(c.study_hours > 0); assert.equal(c.syllabus_daily, 1); assert.equal(c.wearable_daily, 2);
  assert.ok(c.roadmap_items > 12); assert.equal(c.event_attendance, 39); // the cancelled session has no participant row
  assert.equal(r.rowsTotal, Object.values(c).reduce((a, b) => a + b, 0));
  assert.equal(r.today, '2026-10-18');
  assert.equal(r.runAtIst, '2026-10-18 02:00:00');
});

test('every row has exactly the columns of its table and a value for each key column', () => {
  const r = run();
  const columns = {
    students: 'student_id name grade board advisor_id career_counsellor_id program_start_date left_on wearable wearable_connected_on wearable_disconnected_on calendar_connected_on calendar_disconnected_on weekday_study_hours weekend_study_hours',
    staff: 'staff_id name role', todos: 'todo_id student_id source title due_date status created_at updated_at',
    focus_sessions: 'session_id student_id started_at planned_minutes actual_minutes status fail_reason',
    study_hours: 'student_id subject quarter as_of estimated_hours actual_hours',
    events: 'event_id kind title planned_for status group_id owner_staff_id posted_on views shares source nps_score',
    event_attendance: 'event_id student_id invited attended outcome', syllabus_daily: 'student_id day chapters_completed total_chapters', wearable_daily: 'student_id day strain recovery_pct sleep_hours data_source',
    roadmap_items: 'item_id student_id roadmap level title created_at due_date done_at source',
  };
  for (const [table, cols] of Object.entries(columns)) {
    for (const row of r.rows[table]) {
      assert.deepEqual(Object.keys(row).sort(), cols.split(' ').sort(), table);
      for (const k of KEYS[table]) assert.ok(row[k] !== null && row[k] !== undefined && row[k] !== '', `${table}.${k}`);
    }
  }
});

test('live values map as documented: statuses lower-cased, quarter label, IST dates, advisor as staff', () => {
  const r = run();
  assert.ok(r.rows.focus_sessions.every((s) => s.status === 'failed' && s.planned_minutes === null && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s.started_at)));
  assert.ok(r.rows.focus_sessions.some((s) => s.fail_reason === null) && r.rows.focus_sessions.some((s) => s.fail_reason === 'app_switch'));
  assert.ok(r.rows.todos.every((t) => t.status === 'done'));
  assert.deepEqual([...new Set(r.rows.study_hours.map((s) => s.quarter))], ['2026-27-Q3']); // 18 Oct 2026 is in Sep-Nov
  assert.ok(r.rows.study_hours.every((s) => s.as_of === '2026-10-18'));
  assert.deepEqual(r.rows.staff[0].role, 'advisor');
  const me = r.rows.students[0];
  assert.equal(me.grade, 10); assert.equal(me.wearable, 'none'); assert.equal(me.wearable_connected_on, null); assert.equal(me.weekday_study_hours, 2); assert.equal(me.weekend_study_hours, 5);
  assert.equal(me.career_counsellor_id, null); assert.equal(me.program_start_date, '2026-03-01');
  assert.ok(r.rows.events.some((e) => e.kind === 'workshop' && e.nps_score !== null));
  assert.ok(r.rows.events.some((e) => e.status === 'cancelled'));
  assert.ok(r.rows.event_attendance.some((a) => a.attended === true) && r.rows.event_attendance.some((a) => a.attended === false));
});

test('sessions: type words map to schema kinds, an upcoming session is planned and has no attendance yet', () => {
  const s = fx('sessions.json').data[0];
  const mk = (over) => ({ ...s, id: 'S-' + Math.random(), ...over });
  const r = run({ sessions: [{ success: true, data: [
    mk({ sessionType: 'DeepWork', startTime: '2026-10-17T10:00:00.000Z', cancelledAt: null, participants: [{ userId: s.participants[0].userId, status: 'Present' }] }),
    mk({ sessionType: 'PodSession', startTime: '2026-10-25T10:00:00.000Z', cancelledAt: null, participants: [{ userId: s.participants[0].userId, status: 'Upcoming' }] }),
    mk({ sessionType: 'Mentor', startTime: '2026-10-10T10:00:00.000Z', cancelledAt: '2026-10-09T00:00:00.000Z', participants: [] }),
  ], meta: { page: 1, limit: 100, total: 3 } }] });
  const byKind = Object.fromEntries(r.rows.events.map((e) => [e.kind, e]));
  assert.equal(byKind.deep_work_session.status, 'held'); assert.equal(byKind.pod.status, 'planned'); assert.equal(byKind.mentor_call.status, 'cancelled');
  const att = Object.fromEntries(r.rows.event_attendance.map((a) => [a.event_id, a.attended]));
  assert.equal(att[byKind.deep_work_session.event_id], true); assert.equal(att[byKind.pod.event_id], null);
  assert.equal(r.rows.event_attendance.length, 2);
});

test('an unknown status or category is rejected and named, and the other rows still load', () => {
  const todos = fx('todos.json').data;
  const bad = [{ ...todos[0], id: 'T-bad-status', status: 'Snoozed' }, { ...todos[1], id: 'T-bad-source', source: 'whatsapp' }, ...todos.slice(2, 5)];
  const r = run({ todos: bad });
  assert.equal(r.status, 'partial');
  assert.equal(r.counts.todos, 3);
  assert.deepEqual(reasons(r, 'todos').sort(), ['unknown todo source: whatsapp', 'unknown todo status: Snoozed']);
  assert.match(r.note, /2 rows rejected \(todos 2\)/);
  const focus = fx('focus_today.json');
  focus.sessions[0].status = 'Paused'; focus.sessions[1].failReason = 'battery';
  const f = run({ focus: [focus] });
  assert.equal(f.counts.focus_sessions, focus.sessions.length - 2);
  assert.deepEqual(reasons(f, 'focus_sessions').sort(), ['unknown fail reason: battery', 'unknown focus status: Paused']);
  const goals = fx('annual_goals.json'); goals.data[0].category = 'Health';
  assert.deepEqual(reasons(run({ annual: [goals] }), 'roadmap_items'), ['unknown goal category: Health']);
});

test('a session that is still running is skipped, not rejected', () => {
  const focus = fx('focus_today.json'); focus.sessions[0].status = 'Running';
  const r = run({ focus: [focus] });
  assert.equal(r.status, 'ok'); assert.equal(r.skipped, 1); assert.equal(r.counts.focus_sessions, focus.sessions.length - 1);
});

test('duplicates in one payload are collapsed (the later copy wins) so the batch upsert cannot fail', () => {
  const todos = fx('todos.json').data;
  const r = run({ todos: [todos[0], { ...todos[0], status: 'pending' }, todos[1]] });
  assert.equal(r.counts.todos, 2); assert.equal(r.duplicates, 1);
  assert.equal(r.rows.todos.find((t) => t.todo_id === todos[0].id).status, 'pending');
  const syl = run({ syllabus: [{ success: true, data: [{ date: '2026-10-17', chaptersCompleted: 1, totalChapters: 37 }, { date: '2026-10-17', chaptersCompleted: 2, totalChapters: 37 }] }] });
  assert.equal(syl.counts.syllabus_daily, 1); assert.equal(syl.rows.syllabus_daily[0].chapters_completed, 2);
});

test('a failed source is a failed source, never an empty list, and the other sources still load', () => {
  const r = run({ todos: [{ error: 'request failed (details omitted)' }] });
  assert.equal(r.status, 'partial'); assert.equal(r.counts.todos, 0); assert.ok(r.counts.events > 0);
  assert.deepEqual(r.failedSources, [{ source: 'todos', error: 'request failed (details omitted)' }]);
  assert.match(r.note, /failed sources: todos/);
  const api = run({ sessions: [{ success: false, error: { code: 'NOT_FOUND', message: 'nope' } }] });
  assert.deepEqual(api.failedSources.map((f) => f.source), ['sessions']);
  assert.equal(run({ whoop: [{ error: { message: 'timeout' } }] }).counts.students, 0); // the student row waits for the wearable status
  assert.equal(run({ whoop: [{ error: 'x' }] }).status, 'partial');
});

test('single-object endpoints are accepted wrapped, bare, or as a one-element list', () => {
  const bare = fx('focus_today.json');
  const wrapped = { success: true, data: bare };
  assert.deepEqual(run({ focus: [bare] }).rows.focus_sessions, run({ focus: [wrapped] }).rows.focus_sessions);
  const me = fx('me.json').data;
  assert.deepEqual(run({ me: [me] }).rows.students, run({ me: [{ success: true, data: me }] }).rows.students);
  assert.equal(run({ me: [me] }).status, 'ok');
});

test('goals without a due date load with a NULL due date; they are never rejected for it', () => {
  const q = fx('quarterly_goals.json');
  const bare = q.data.find((g) => !g.dueDate);
  assert.ok(bare, 'the fixture has a goal without a due date (it is in the live data)');
  const r = run({ quarterly: [q] });
  assert.equal(r.status, 'ok');
  const row = r.rows.roadmap_items.find((x) => x.item_id === `quarterly:${bare.id}`);
  assert.equal(row.due_date, null);
  assert.ok(r.rows.roadmap_items.filter((x) => x.item_id.startsWith('monthly:') && x.due_date === null).length >= 1);
});

test('an empty answer is an empty list; a missing node output is a failure', () => {
  assert.deepEqual(unwrap([]), { data: [] });
  assert.deepEqual(unwrap([{}]), { data: [] });
  assert.equal(run({ todos: [] }).status, 'ok');
  assert.equal(run({ todos: undefined }).failedSources[0].source, 'todos');
});

test('a truncated page set is a failure: 100 of 120 is not "the sessions"', () => {
  const s = fx('sessions.json').data;
  const page = (rows, p) => ({ success: true, data: rows, meta: { page: p, limit: 100, total: 120 } });
  const lost = run({ sessions: [page(s.slice(0, 40), 1)] });
  assert.equal(lost.status, 'partial'); assert.match(lost.failedSources[0].error, /truncated: 40 of 120/);
  assert.equal(lost.counts.events, 0);
  const many = Array.from({ length: 120 }, (_, i) => ({ ...s[i % 40], id: `E${i}` }));
  const two = run({ sessions: [page(many.slice(0, 100), 1), page(many.slice(100), 2)] });
  assert.equal(two.status, 'ok'); assert.equal(two.counts.events, 120);
});

test('if the student cannot be identified the whole run fails and loads nothing', () => {
  const r = run({ me: [{ success: true, data: { name: 'x' } }] });
  assert.equal(r.status, 'failed'); assert.equal(r.rowsTotal, 0); assert.match(r.note, /cannot identify the student/);
  assert.equal(run({ me: [{ error: 'boom' }] }).status, 'failed');
});

test('the student row validates its required fields', () => {
  const me = (over) => [{ success: true, data: { ...fx('me.json').data, ...over } }];
  assert.match(reasons(run({ me: me({ advisorId: '' }) }), 'students')[0], /advisor_id/);
  assert.match(reasons(run({ me: me({ programStartDate: '2026-03-01' }) }), 'students')[0], /program_start_date/);
  const signin = fx('signin.json'); signin.data.user.grade = 14;
  assert.match(reasons(run({ signin: [signin] }), 'students')[0], /grade/);
  assert.equal(run({ me: me({ careerCounselor: { id: 'CC1', name: 'Demo Counsellor' } }) }).rows.staff.length, 2);
});

test('wearable state: connected stamps the date; not connected stamps the disconnect date; the database keeps the first one', () => {
  const on = run({ whoop: [{ isConnected: true, needsReconnect: false, lastSyncAt: '2026-10-17T20:00:00.000Z' }] }).rows.students[0];
  assert.deepEqual([on.wearable, on.wearable_connected_on, on.wearable_disconnected_on], ['whoop', '2026-10-18', null]);
  const off = run().rows.students[0];
  assert.deepEqual([off.wearable, off.wearable_connected_on, off.wearable_disconnected_on], ['none', null, '2026-10-18']);
});

test('goals: category and level map, Achieved stamps done_at, nothing else does, annual goals are due at year end', () => {
  const q = fx('quarterly_goals.json');
  q.data[0].status = 'Achieved'; q.data[0].monthlyGoals[0].status = 'Achieved'; q.data[1].status = 'InProgress';
  const r = run({ quarterly: [q] });
  const byId = Object.fromEntries(r.rows.roadmap_items.map((x) => [x.item_id, x]));
  assert.equal(byId[`quarterly:${q.data[0].id}`].done_at, '2026-10-18 02:00:00');
  assert.equal(byId[`monthly:${q.data[0].monthlyGoals[0].id}`].done_at, '2026-10-18 02:00:00');
  assert.equal(byId[`quarterly:${q.data[1].id}`].done_at, null);
  const annual = r.rows.roadmap_items.filter((x) => x.level === 'annual');
  assert.ok(annual.length > 0 && annual.every((x) => x.due_date === '2026-12-31'));
  assert.ok(r.rows.roadmap_items.every((x) => ['career', 'personal', 'academic', 'social_work', 'entrepreneurship'].includes(x.roadmap)));
  assert.ok(r.rows.roadmap_items.some((x) => x.roadmap === 'entrepreneurship') || q.data.every((g) => g.category.type !== 'Venture'));
});

test('replaying the same input gives the same rows: the mapping is deterministic', () => {
  assert.deepEqual(run().rows, run().rows);
  assert.deepEqual(run(), run());
});

test('the run time is the only clock: the same input at a different time changes only the time-dependent fields', () => {
  const a = normalise({ runAt: RUN_AT, sources: sources() });
  const b = normalise({ runAt: '2026-10-18T20:30:00.000Z', sources: sources() });
  assert.equal(a.rows.todos.length, b.rows.todos.length);
  assert.notEqual(a.today, b.today);
  assert.throws(() => normalise({ runAt: '2026-10-18 02:00', sources: sources() }), /runAt/);
});

test('summarise: ok, partial when a table failed, failed when all did, with the rejects in the note', () => {
  const run0 = run();
  const tables = [{ table: 'todos' }, { table: 'events' }];
  const base = { run: run0, tables, runId: 'n8n-42', finishedAt: '2026-10-17T20:31:00.000Z' };
  const ok = summarise({ ...base, tableResults: [{ upserted: 30 }, { upserted: 40 }] });
  assert.deepEqual(ok, { run_id: 'n8n-42', source: 'app_api', started_at: '2026-10-18 02:00:00', finished_at: '2026-10-18 02:01:00', status: 'ok', rows_upserted: 70, error: null });
  const part = summarise({ ...base, tableResults: [{ upserted: 30 }, { error: { message: 'relation "events" does not exist' } }] });
  assert.equal(part.status, 'partial'); assert.equal(part.rows_upserted, 30); assert.match(part.error, /database errors: events: database relation unavailable/);
  const all = summarise({ ...base, tableResults: [{ error: 'a' }, { error: 'b' }] });
  assert.equal(all.status, 'failed');
  const withRejects = summarise({ ...base, run: run({ todos: [{ ...fx('todos.json').data[0], status: 'Snoozed' }] }), tableResults: [{ upserted: 1 }, { upserted: 1 }] });
  assert.equal(withRejects.status, 'partial'); assert.match(withRejects.error, /unknown todo status: Snoozed/);
  assert.equal(summarise({ ...base, tableResults: [{ upserted: 1 }] }).status, 'partial'); // a table with no result counts as failed
});

test('summarise: a failed run stays failed even when the database writes nothing', () => {
  const failedRun = run({ me: [{ error: 'boom' }] });
  const s = summarise({ run: failedRun, tables: [{ table: 'none' }], tableResults: [{ upserted: 0 }], runId: 'n8n-7', finishedAt: '2026-10-17T20:31:00.000Z' });
  assert.equal(s.status, 'failed'); assert.match(s.error, /cannot identify the student/);
});

test('error text is safe to store: capped, no SQL, no whole objects', () => {
  const sql = 'Failed query: WITH up AS (\n  INSERT INTO todos (todo_id, title) SELECT ... $1::json';
  const s = summarise({ run: run(), tables: [{ table: 'todos' }], tableResults: [{ error: { name: 'NodeOperationError', description: sql, node: { credentials: { postgres: { id: 'x' } } } } }],
                        runId: 'n8n-1', finishedAt: '2026-10-17T20:31:00.000Z' });
  assert.match(s.error, /todos: the database rejected the write/);
  assert.doesNotMatch(s.error, /INSERT|WITH up|credentials|postgres/);
  assert.equal(summarise({ run: run(), tables: [{ table: 'todos' }], tableResults: [{ error: { level: 'warning', node: {} } }], runId: 'n8n-1', finishedAt: '2026-10-17T20:31:00.000Z' }).error.includes('unknown error'), true);
  const long = unwrap([{ error: 'x'.repeat(5000) }]);
  assert.equal(long.error, 'request failed (details omitted)');
  assert.match(unwrap([{ error: { message: '500 - "Injected failure"' } }]).error, /HTTP 500 request failed/);
});


test('malformed rows are rejected without discarding valid rows or other sources', () => {
  for (const [name, table, fixture] of [['syllabus', 'syllabus_daily', 'syllabus_history.json'], ['todos', 'todos', 'todos.json'], ['sessions', 'events', 'sessions.json']]) {
    const good = fx(fixture).data;
    const r = run({ [name]: [{ success: true, data: [null, ...good] }] });
    assert.equal(r.status, 'partial', name);
    assert.equal(r.counts[table], run().counts[table], name);
    assert.equal(r.rejects.filter(x => x.table === table).length, 1, name);
  }
});

test('a malformed focus response is partial, while a valid empty sessions list is ok', () => {
  for (const data of [{}, { sessions: null }, { sessions: {} }]) {
    const r = run({ focus: [{ success: true, data }] });
    assert.equal(r.status, 'partial');
    assert.ok(r.failedSources.some(x => x.source === 'focus'));
    assert.equal(r.counts.focus_sessions, 0);
    assert.ok(r.counts.todos > 0);
  }
  assert.equal(run({ focus: [{ sessions: [] }] }).status, 'ok');
});

test('impossible calendar dates and normalized clock values are rejected',()=>{
 for(const value of ['2026-02-30T12:00:00Z','2025-02-29T12:00:00Z','2026-10-01T24:00:00Z'])assert.equal(toIst(value),null);
 assert.equal(toIst('2024-02-29T12:00:00Z'),'2024-02-29 17:30:00');
 const r=run({syllabus:[{success:true,data:[{date:'2026-02-30',chaptersCompleted:1,totalChapters:2}]}]});
 assert.equal(r.counts.syllabus_daily,0);assert.equal(r.status,'partial');
});
test('duplicate pages and changing totals cannot prove complete history',()=>{
 const page={success:true,data:[{id:'A'},{id:'B'}],meta:{total:4}};
 assert.match(unwrap([page,structuredClone(page)]).error,/truncated|duplicate/);
 assert.match(unwrap([page,{...page,meta:{total:5}}]).error,/total|inconsistent/);
 assert.deepEqual(unwrap([{success:true,data:[{id:'A'}],meta:{total:1}}]).data,[{id:'A'}]);
});
test('untrusted API and database errors never retain arbitrary message contents',()=>{
 for(const message of ['Authorization Bearer AUDIT_SECRET','password=AUDIT_SECRET','opaque AUDIT_SECRET']){
  const r=unwrap([{error:{message}}]);assert.ok(!r.error.includes('AUDIT_SECRET'));assert.ok(r.error.length<=200);
 }
});

test('wellness: Whoop days load, sleep is only the sum of all three stages, manual days are skipped, bad values are rejected', () => {
  const r = run();
  assert.deepEqual(r.rows.wearable_daily.map((x) => [x.day, x.strain, x.recovery_pct, x.sleep_hours, x.data_source]),
    [['2026-10-15', 8, 32, 8, 'whoop'], ['2026-10-16', 16, 71, null, 'whoop']]);
  assert.equal(r.status, 'ok');
  const bad = (h) => run({ wellness: [{ success: true, data: { history: [{ date: '2026-10-15', dataSource: 'WHOOP', ...h }] } }] });
  assert.equal(bad({ dayStrain: 30 }).counts.wearable_daily, 0);
  assert.equal(bad({ dayStrain: 30 }).status, 'partial');
  assert.equal(bad({ dataSource: 'GARMIN', dayStrain: 5 }).status, 'partial');
  assert.equal(bad({ dayStrain: 5, sleepStageLightMs: '3600000', sleepStageDeepMs: null, sleepStageRemMs: '3600000' }).rows.wearable_daily[0].sleep_hours, null);
  assert.equal(bad({}).counts.wearable_daily, 0); // nothing measured: skipped, not rejected
  assert.equal(bad({}).status, 'ok');
});

test('wellness: a failed or malformed read is a failed source, never an empty history', () => {
  const failed = run({ wellness: [{ error: { message: 'timeout' } }] });
  assert.equal(failed.status, 'partial'); assert.equal(failed.failedSources[0].source, 'wellness'); assert.equal(failed.counts.wearable_daily, 0);
  assert.equal(run({ wellness: [{ success: true, data: { history: 'x' } }] }).failedSources[0].source, 'wellness');
});
