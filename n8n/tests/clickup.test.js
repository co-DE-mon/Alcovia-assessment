'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { toIst } = require('../code/normalise.js');
const { mapClickUp, clickupLog } = require('../code/clickup.js');

const fx = (n) => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', n), 'utf8'));
const KINDS = ['targets_aligned', 'guardrails_set', 'inputs_at_cadence', 'deadline_messages_sent', 'tutor_input_set', 'sprint_made', 'syllabus_review', 'rigour_check', 'career_roadmap_reviewed', 'personal_milestones_set'];
const CONFIG = { advisor_input_kinds: KINDS, exam_types: ['formative', 'unit_test', 'mid_term'], score_max: 100 };
const run = (over = {}) => mapClickUp({ advisor: fx('clickup_advisor.json'), exams: fx('clickup_exams.json'), ...over }, CONFIG, { toIst });
const task = (over) => structuredClone({ ...fx('clickup_exams.json')[0].tasks[0], ...over });
const withField = (t, name, value) => { t.custom_fields.find((f) => f.name === name).value = value; return t; };
const examPage = (...tasks) => [{ tasks, last_page: true }];

test('valid fixtures map to the expected rows', () => {
  const r = run();
  assert.equal(r.status, 'ok');
  assert.deepEqual(r.counts, { advisor_inputs: 30, exam_targets: 3 });
  const s2 = r.rows.advisor_inputs.filter((x) => x.student_id === 'DEMO-STUDENT-2');
  assert.equal(s2.length, 10); assert.equal(s2.filter((x) => x.done).length, 3);
  assert.ok(r.rows.advisor_inputs.every((x) => x.source === 'clickup' && /^\d{4}-\d{2}-01$/.test(x.month)));
  assert.ok(r.rows.advisor_inputs.some((x) => x.month === '2026-09-01' && x.student_id === 'DEMO-STUDENT-1' && x.input_kind === 'targets_aligned' && x.done));
  assert.deepEqual(r.rows.exam_targets.find((x) => x.subject === 'Physics'), { student_id: 'DEMO-STUDENT-1', subject: 'Physics', exam_type: 'unit_test', target_score: 70, actual_score: null });
  assert.equal(r.rows.exam_targets.find((x) => x.student_id === 'DEMO-STUDENT-2').exam_type, 'mid_term'); // "Mid Term" is normalised
});

test('an unchecked checkbox is "not done"; a student-month with no task has no rows at all', () => {
  const r = run();
  assert.equal(r.rows.advisor_inputs.filter((x) => x.student_id === 'DEMO-STUDENT-2' && x.month === '2026-09-01').length, 0);
  assert.equal(r.rows.advisor_inputs.find((x) => x.student_id === 'DEMO-STUDENT-2' && x.input_kind === 'rigour_check').done, false);
});

test('invalid tasks are rejected and named; the rest still load', () => {
  const adv = fx('clickup_advisor.json');
  withField(adv[0].tasks[0], 'month', '2026-13');
  withField(adv[0].tasks[1], 'sprint_made', 'maybe');
  const exams = examPage(withField(task({ id: 'b1' }), 'exam_type', 'quiz'), withField(task({ id: 'b2' }), 'target_score', '150'), withField(task({ id: 'b3' }), 'actual_score', 'n/a'),
    withField(task({ id: 'b4' }), 'target_score', null), withField(task({ id: 'b5' }), 'student_id', ''), task({ id: 'ok1' }));
  const r = run({ advisor: adv, exams });
  assert.equal(r.status, 'partial');
  assert.deepEqual(r.rejects.map((x) => x.id).sort(), ['b1', 'b2', 'b3', 'b4', 'b5', 't1', 't2']);
  assert.equal(r.counts.exam_targets, 1); assert.equal(r.counts.advisor_inputs, 10); // only t3 survives; the rejected tasks leave no partial rows
  assert.match(r.note, /7 tasks rejected/);
});

test('a task with a field repeated, or with no checkbox fields at all, is rejected', () => {
  const adv = fx('clickup_advisor.json');
  adv[0].tasks[0].custom_fields.push({ name: 'Month', value: '2026-10' });
  adv[0].tasks[1].custom_fields = adv[0].tasks[1].custom_fields.filter((f) => !KINDS.includes(f.name));
  const r = run({ advisor: adv });
  assert.deepEqual(r.rejects.map((x) => x.id).sort(), ['t1', 't2']);
});

test('duplicates: the most recently edited task wins, and is counted', () => {
  const older = withField(task({ id: 'd1', date_updated: '1000' }), 'target_score', '50');
  const newer = withField(task({ id: 'd2', date_updated: '2000' }), 'target_score', '60');
  for (const order of [[older, newer], [newer, older]]) {
    const r = run({ exams: examPage(...order) });
    assert.equal(r.counts.exam_targets, 1); assert.equal(r.rows.exam_targets[0].target_score, 60); assert.equal(r.duplicates, 1);
  }
});

test('a failed, empty or truncated read is a failed source, never "no tasks"', () => {
  for (const bad of [[{ error: { message: 'timeout' } }], [{}], [], [{ tasks: [], last_page: false }], [{ tasks: 'x', last_page: true }]]) {
    const r = run({ exams: bad });
    assert.equal(r.status, 'partial'); assert.equal(r.failedSources[0].source, 'exam_list'); assert.equal(r.counts.exam_targets, 0); assert.equal(r.counts.advisor_inputs, 30);
  }
  const both = run({ advisor: [{}], exams: [{}] });
  assert.equal(both.status, 'failed');
  assert.equal(run({ exams: [{ tasks: [], last_page: true }] }).status, 'ok'); // a valid empty list is fine
});

test('the mapper refuses a bad configuration', () => {
  assert.throws(() => mapClickUp({ advisor: [], exams: [] }, { ...CONFIG, score_max: 0 }, { toIst }), /configuration/);
});

test('the log row: counts what the database reported and flags suppressed rows', () => {
  const r = run();
  const base = { result: r, runId: 'clickup-1', startedAt: '2026-10-17T20:30:00Z', finishedAt: '2026-10-17T20:31:00Z' };
  const ok = clickupLog({ ...base, written: { advisor_inputs: 30, exam_targets: 3 } }, { toIst });
  assert.deepEqual(ok, { run_id: 'clickup-1', source: 'clickup', started_at: '2026-10-18 02:00:00', finished_at: '2026-10-18 02:01:00', status: 'ok', rows_upserted: 33, error: null });
  const skipped = clickupLog({ ...base, written: { advisor_inputs: 20, exam_targets: 3 } }, { toIst });
  assert.equal(skipped.status, 'partial'); assert.match(skipped.error, /10 rows skipped/);
  assert.equal(clickupLog({ ...base, written: { error: 'connection refused' } }, { toIst }).status, 'failed');
});
