// The three Code-node bodies run the way n8n runs them: the module text plus the glue, as one function body with n8n's globals stubbed.
// Catches what unit tests of the module alone cannot: a name clash between the glue and the module, a missing global, a wrong node name.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = (p) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');
const fx = (n) => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', n), 'utf8'));
const module_ = read('code/normalise.js');
const body = (glue, sql) => module_ + read(glue).replace('/*__SQL__*/ {}', JSON.stringify(sql || {}));
const run = (glue, globals, sql) => new Function('$', '$input', '$execution', body(glue, sql))(globals.$, globals.$input, globals.$execution);

const nodeOutputs = () => ({
  'Sign in': [fx('signin.json')], 'Fetch profile': [fx('me.json')], 'Fetch wearable status': [fx('whoop_status.json')], 'Fetch time budget': [fx('time_budget.json')],
  'Fetch focus today': [fx('focus_today.json')], 'Fetch todos': fx('todos.json').data, 'Fetch sessions': [fx('sessions.json')],
  'Fetch syllabus history': [fx('syllabus_history.json')], 'Fetch wellness history': [fx('wellness_history.json')], 'Fetch annual goals': [fx('annual_goals.json')], 'Fetch quarterly goals': [fx('quarterly_goals.json')],
});
const stub = (outputs) => (name) => {
  if (!(name in outputs)) throw new Error(`Node '${name}' hasn't been executed`);
  const items = outputs[name].map((json) => ({ json }));
  return { all: () => items, first: () => items[0] };
};

test('the poll glue reads every fetch node by name and emits one item per table with its SQL', () => {
  const sql = Object.fromEntries(['staff', 'students', 'study_hours', 'focus_sessions', 'todos', 'events', 'event_attendance', 'syllabus_daily', 'wearable_daily', 'roadmap_items'].map((t) => [t, `SQL ${t}`]));
  const out = run('code/poll-glue.js', { $: stub(nodeOutputs()) }, sql);
  assert.deepEqual(out.map((i) => i.json.table), ['staff', 'students', 'study_hours', 'focus_sessions', 'todos', 'events', 'event_attendance', 'syllabus_daily', 'wearable_daily', 'roadmap_items']);
  assert.ok(out.every((i) => i.json.sql === `SQL ${i.json.table}` && Array.isArray(i.json.rows) && i.json.rows.length > 0));
  assert.equal(out[0].json.run.status, 'ok');
  assert.equal(out[0].json.run.counts.todos, 30);
});

test('a node that did not run counts as a failed source, not a crash', () => {
  const outputs = nodeOutputs(); delete outputs['Fetch todos'];
  const out = run('code/poll-glue.js', { $: stub(outputs) }, {});
  assert.equal(out[0].json.run.status, 'partial');
  assert.match(out[0].json.run.note, /failed sources: todos \(node Fetch todos did not run\)/);
  assert.ok(!out.some((i) => i.json.table === 'todos'));
});

test('with nothing to write the glue still emits one harmless item so the run is logged', () => {
  const outputs = nodeOutputs(); outputs['Fetch profile'] = [{ error: 'boom' }];
  const out = run('code/poll-glue.js', { $: stub(outputs) }, {});
  assert.equal(out.length, 1);
  assert.equal(out[0].json.table, 'none'); assert.equal(out[0].json.run.status, 'failed');
  assert.match(out[0].json.sql, /SELECT 0/);
});

test('the summarise glue reads the run, the table list and the database results by node name', () => {
  const normalise = stub({ Normalise: [{ table: 'todos', run: { status: 'ok', rowsTotal: 2, note: null, runAtIst: '2026-10-18 02:00:00' } }, { table: 'events', run: {} }],
                           'Upsert table': [{ upserted: 30 }, { upserted: 40 }] });
  const out = run('code/summarise-glue.js', { $: (n) => (n === 'Upsert table' ? stub({ 'Upsert table': [{ upserted: 30 }, { upserted: 40 }] })(n) : normalise(n)), $execution: { id: '42' } });
  assert.deepEqual({ ...out[0].json.log, finished_at: 'x' }, { run_id: 'n8n-42', source: 'app_api', started_at: '2026-10-18 02:00:00', finished_at: 'x', status: 'ok', rows_upserted: 70, error: null });
  const manual = run('code/summarise-glue.js', { $: normalise, $execution: {} });
  assert.match(manual[0].json.log.run_id, /^n8n-manual-\d{14}$/);
});

test('the error glue builds a failed log row from an n8n error report, with or without an execution id', () => {
  const report = { execution: { id: '77', lastNodeExecuted: 'Sign in', error: { message: 'Authorization failed' } }, workflow: { id: 'w', name: 'Student app daily poll' } };
  const out = run('code/error-glue.js', { $input: { first: () => ({ json: report }) } });
  const log = out[0].json.log;
  assert.equal(log.run_id, 'n8n-77'); assert.equal(log.status, 'failed'); assert.equal(log.source, 'app_api'); assert.equal(log.rows_upserted, 0);
  assert.match(log.error, /^workflow Student app daily poll stopped at Sign in: Authorization failed$/);
  assert.match(log.started_at, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  const bare = run('code/error-glue.js', { $input: { first: () => ({ json: { workflow: { name: 'x' }, trigger: { error: { message: 'trigger failed' } } } }) } });
  assert.match(bare[0].json.log.run_id, /^n8n-manual-\d{14}$/); assert.equal(bare[0].json.log.status, 'failed');
});

test('no glue file declares a name the module already declares', () => {
  const declared = new Set([...module_.matchAll(/^(?:const|let|function|class)\s+([A-Za-z_$][\w$]*)/gm)].map((m) => m[1]));
  for (const f of ['code/poll-glue.js', 'code/summarise-glue.js', 'code/error-glue.js']) {
    const mine = [...read(f).matchAll(/^(?:const|let|function|class)\s+([A-Za-z_$][\w$]*)/gm)].map((m) => m[1]);
    assert.deepEqual(mine.filter((n) => declared.has(n)), [], f);
  }
});


test('the error handler sanitises SQL details and preserves trigger failures', () => {
  const report = { execution: { id: '88', lastNodeExecuted: 'Log run', error: { message: 'Failed query: INSERT INTO private VALUES (sensitive-row)' } }, workflow: { name: 'poll' } };
  const log = run('code/error-glue.js', { $input: { first: () => ({ json: report }) } })[0].json.log;
  assert.doesNotMatch(log.error, /INSERT|sensitive-row/);
  const trigger = { trigger: { error: { message: 'schedule activation failed' } }, workflow: { name: 'poll' } };
  assert.match(run('code/error-glue.js', { $input: { first: () => ({ json: trigger }) } })[0].json.log.error, /schedule activation failed/);
});

test('the actual error-handler glue omits arbitrary upstream credential text',()=>{
 const report={execution:{id:'audit',lastNodeExecuted:'Sign in',error:{message:'Authorization Bearer AUDIT_SECRET password=HIDDEN'}},workflow:{name:'Demo'}};
 const result=run('code/error-glue.js',{$input:{first:()=>({json:report})}});
 assert.doesNotMatch(JSON.stringify(result),/AUDIT_SECRET|HIDDEN/);
 assert.match(result[0].json.log.error,/Sign in/);
});

test('the error glue labels a ClickUp workflow failure as clickup, and any other workflow as app_api', () => {
  const log = id => run('code/error-glue.js', { $input: { first: () => ({ json: { execution: { id: '5', error: { message: 'x' } }, workflow: { id, name: 'w' } } }) } })[0].json.log;
  assert.equal(log('clickupAdvisorInputs01').source, 'clickup');
  assert.equal(log('studentAppDailyPoll01').source, 'app_api');
});
