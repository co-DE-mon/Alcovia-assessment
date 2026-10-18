// A stand-in for the student app API, for the integration test only. Serves tests/fixtures, and misbehaves on request through /__control.
// Not part of the product: it exists so the workflow can be run end to end without touching Alcovia's real service or any real credential.
'use strict';
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const FX = process.env.FIXTURES || path.join(__dirname, 'fixtures');
const TOKEN = 'TEST-ONLY-ACCESS-TOKEN';
const CREDS = { email: 'student@example.test', password: 'test-only-password' };
const fx = (name) => JSON.parse(fs.readFileSync(path.join(FX, name), 'utf8'));
const json = (res, code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };

// state: clickupPatch {list: {taskIndex: {field: value}}} (ClickUp stand-in), signinFail, whoop, sessionsTotal, quarterlyTotal, truncateSessions, fail {path: n} (n requests fail, -1 = always),
//        todoPatch {index: fields}, todoExtra [todo], focusPatch {index: fields}, goalStatus {index: status}
const defaults = () => ({ clickupPatch: {}, signinFail: false, whoop: false, sessionsTotal: 40, quarterlyTotal: 12, truncateSessions: false,
                          fail: {}, todoPatch: {}, todoExtra: [], focusPatch: {}, goalStatus: {}, sessionExtra: [] });
let state = defaults();
let log = [];

function grow(rows, total) {
  const base = rows.filter((r) => !r.cancelledAt);
  const out = rows.slice();
  for (let i = 0; out.length < total; i += 1) out.push({ ...base[i % base.length], id: `${base[i % base.length].id}-x${i}` });
  return out.slice(0, Math.max(total, 0));
}
function page(rows, q, total, truncate) {
  const limit = Number(q.get('limit') || 100);
  const p = Number(q.get('page') || 1);
  const data = truncate && p > 1 ? [] : rows.slice((p - 1) * limit, p * limit);
  return { success: true, data, meta: { page: p, limit, total } };
}
function patch(rows, patches) { return rows.map((r, i) => (patches[i] ? { ...r, ...patches[i] } : r)); }

const routes = {
  '/api/v1/users/me': () => fx('me.json'),
  '/api/v1/whoop/status': () => ({ success: true, data: { isConnected: state.whoop, needsReconnect: false, expiryDate: null, lastSyncAt: null, reauthErrorAt: null } }),
  '/api/v1/academics/time-budget': () => fx('time_budget.json'),
  '/api/v1/schedule/focus/score/today': () => { const f = fx('focus_today.json'); return { ...f, sessions: patch(f.sessions, state.focusPatch) }; },
  '/api/v1/student/todos': () => ({ success: true, data: [...patch(fx('todos.json').data, state.todoPatch), ...state.todoExtra] }),
  '/api/v1/schedule/sessions': (q) => page([...grow(fx('sessions.json').data, state.sessionsTotal), ...state.sessionExtra], q, state.sessionsTotal + state.sessionExtra.length, state.truncateSessions),
  '/api/v1/academics/my-syllabus-history': () => fx('syllabus_history.json'),
  '/api/v1/wellness/history': () => fx('wellness_history.json'),
  '/api/v1/goals/annual': () => fx('annual_goals.json'),
  '/api/v1/goals/quarterly': (q) => {
    const rows = patch(fx('quarterly_goals.json').data, Object.fromEntries(Object.entries(state.goalStatus).map(([i, s]) => [i, { status: s }])));
    return page(grow(rows, state.quarterlyTotal), q, state.quarterlyTotal, false);
  },
};

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  let body = '';
  req.on('data', (c) => { body += c; });
  req.on('end', () => {
    if (url.pathname === '/__control' && req.method === 'POST') { state = { ...defaults(), ...JSON.parse(body || '{}') }; log = []; return json(res, 200, { ok: true }); }
    if (url.pathname === '/__log') return json(res, 200, log);
    if (url.pathname.startsWith('/api/v2/list/')) {       // ClickUp stand-in: raw token in Authorization, two-page advisor list
      const m = url.pathname.match(/^\/api\/v2\/list\/(ADVISOR1|EXAMS1)\/task$/);
      const entry2 = { method: req.method, path: url.pathname, query: Object.fromEntries(url.searchParams), authorised: req.headers.authorization === 'TEST-CLICKUP-TOKEN' };
      log.push(entry2);
      if (!m || req.method !== 'GET') return json(res, 404, { err: 'Not found', ECODE: 'NOT_FOUND' });
      if (!entry2.authorised) return json(res, 401, { err: 'Token invalid', ECODE: 'OAUTH_019' });
      const rule = state.fail[entry2.path];
      if (rule !== undefined && rule !== 0) { if (rule > 0) state.fail[entry2.path] -= 1; entry2.failed = true; return json(res, 500, { err: 'Injected failure', ECODE: 'INTERNAL' }); }
      const pages = fx(m[1] === 'ADVISOR1' ? 'clickup_advisor.json' : 'clickup_exams.json');
      const patches = (state.clickupPatch || {})[m[1]] || {};
      let n = 0;
      const patched = pages.map((pg) => ({ ...pg, tasks: pg.tasks.map((t) => { const p = patches[n]; n += 1; return p ? { ...t, custom_fields: t.custom_fields.map((f) => (f.name in p ? { ...f, value: p[f.name] } : f)) } : t; }) }));
      return json(res, 200, patched[Number(url.searchParams.get('page') || 0)] || { tasks: [], last_page: true });
    }
    const entry = { method: req.method, path: url.pathname.replace('/api/v1', ''), query: Object.fromEntries(url.searchParams), authorised: req.headers.authorization === `Bearer ${TOKEN}` };
    log.push(entry);
    if (url.pathname === '/api/v1/auth/signin' && req.method === 'POST') {
      let sent = {};
      try { sent = JSON.parse(body || '{}'); } catch (e) { /* not json */ }
      entry.bodyKeys = Object.keys(sent).sort();
      entry.contentType = req.headers['content-type'] || null;
      if (state.signinFail || sent.email !== CREDS.email || sent.password !== CREDS.password) return json(res, 401, { success: false, error: { code: 'UNAUTHORIZED', message: 'Invalid credentials' } });
      return json(res, 200, fx('signin.json'));
    }
    const route = routes[url.pathname];
    if (!route || req.method !== 'GET') return json(res, 404, { success: false, error: { code: 'NOT_FOUND', message: 'No such route' } });
    if (!entry.authorised) return json(res, 401, { success: false, error: { code: 'UNAUTHORIZED', message: 'Missing or invalid token' } });
    const rule = state.fail[entry.path];
    if (rule !== undefined && rule !== 0) {
      if (rule > 0) state.fail[entry.path] -= 1;
      entry.failed = true;
      return json(res, 500, { success: false, error: { code: 'INTERNAL', message: 'Injected failure' } });
    }
    return json(res, 200, route(url.searchParams));
  });
}).listen(Number(process.env.PORT || 8080), '0.0.0.0', () => console.log('mock api up'));
