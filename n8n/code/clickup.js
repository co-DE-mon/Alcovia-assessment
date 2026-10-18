/* Pure ClickUp mapper for the advisor-inputs workflow. No network, clock or credentials.
 *
 * ASSUMED ClickUp model (Alcovia's workspace was never seen; see the ClickUp assumptions in n8n/README.md). Two lists:
 *   advisor list: one task per student per month. Custom fields: student_id (text), month (text, YYYY-MM or YYYY-MM-01), and one checkbox per
 *                 advisor input kind, named exactly like the kind (targets_aligned, guardrails_set, ...).
 *   exam list:    one task per student, subject and exam type. Custom fields: student_id, subject, exam_type, target_score, actual_score.
 * A student-month with no task produces no rows: unknown is not "not done". An unchecked box on an existing task is "not done".
 */
'use strict';
function mapClickUp(input, config, helpers) {
  const record = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
  const rejects = [], failedSources = [];
  let duplicates = 0;
  const reject = (table, id, reason) => rejects.push({ table, id: id === undefined || id === null ? null : String(id), reason });
  const kinds = config && config.advisor_input_kinds, examTypes = config && config.exam_types, max = config && config.score_max;
  if (!Array.isArray(kinds) || !kinds.length || !Array.isArray(examTypes) || !examTypes.length || !Number.isFinite(max) || max <= 0) throw new Error('invalid ClickUp mapper configuration');

  // The HTTP node hands over one item per page. A failed read, an empty object or a last page that is not marked last is a failed source, never "no tasks".
  const tasksOf = (name, items) => {
    if (!Array.isArray(items) || !items.length) { failedSources.push({ source: name, error: 'no response' }); return null; }
    const bad = items.find((i) => !record(i) || i.error || !Array.isArray(i.tasks));
    if (bad) { failedSources.push({ source: name, error: String((record(bad) && bad.error && (bad.error.message || bad.error)) || 'malformed response: tasks must be an array').slice(0, 200) }); return null; }
    if (items[items.length - 1].last_page !== true) { failedSources.push({ source: name, error: 'truncated: the last page received was not the last page' }); return null; }
    return [].concat(...items.map((i) => i.tasks));
  };
  const fieldsOf = (task) => {
    if (!record(task) || typeof task.id !== 'string' || !task.id || !Array.isArray(task.custom_fields)) throw new Error('task has no id or custom_fields');
    const out = new Map();
    for (const f of task.custom_fields) {
      if (!record(f) || typeof f.name !== 'string') throw new Error('malformed custom field');
      const key = f.name.trim().toLowerCase();
      if (out.has(key)) throw new Error(`custom field "${key}" appears twice`);
      out.set(key, f.value);
    }
    return out;
  };
  const textField = (fields, key) => {
    const v = fields.get(key);
    if (typeof v !== 'string' || !v.trim()) throw new Error(`${key} missing or empty`);
    return v.trim();
  };
  const numberOrNull = (fields, key) => {
    const v = fields.get(key);
    if (v === undefined || v === null || v === '') return null;
    const n = typeof v === 'number' ? v : typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v.trim()) ? Number(v) : NaN;
    if (!Number.isFinite(n) || n < 0 || n > max) throw new Error(`${key} is not a number between 0 and ${max}: ${v}`);
    return n;
  };
  const month = (value) => {
    const m = typeof value === 'string' ? value.trim().match(/^(\d{4})-(\d{2})(?:-01)?$/) : null;
    if (!m || Number(m[2]) < 1 || Number(m[2]) > 12) throw new Error(`month is not YYYY-MM or YYYY-MM-01: ${value}`);
    return `${m[1]}-${m[2]}-01`;
  };
  const stamp = (task) => (typeof task.date_updated === 'string' && /^\d+$/.test(task.date_updated) ? Number(task.date_updated) : 0);
  // The newest edit of a task wins when two tasks claim the same key; on a tie the later one in the response does.
  const keep = (map, key, row, task) => {
    const old = map.get(key);
    if (old) duplicates += 1;
    if (!old || stamp(task) >= old.stamp) map.set(key, { row, stamp: stamp(task) });
  };

  const advisor = new Map(), exams = new Map();
  const advisorTasks = tasksOf('advisor_list', input.advisor);
  for (const task of advisorTasks || []) {
    try {
      const fields = fieldsOf(task);
      const student = textField(fields, 'student_id'), m = month(fields.get('month'));
      const pending = [];
      for (const kind of kinds) {
        if (!fields.has(kind)) continue;
        const v = fields.get(kind);
        if (!(v === undefined || v === null || typeof v === 'boolean' || v === 'true' || v === 'false')) throw new Error(`${kind} is not a checkbox value: ${v}`);
        pending.push([`${student}|${m}|${kind}`, { student_id: student, month: m, input_kind: kind, done: v === true || v === 'true', source: 'clickup' }]);
      }
      if (!pending.length) throw new Error('no advisor input checkbox fields on the task');
      pending.forEach(([key, row]) => keep(advisor, key, row, task)); // only a fully valid task contributes rows
    } catch (e) { reject('advisor_inputs', task && task.id, e.message); }
  }
  const examTasks = tasksOf('exam_list', input.exams);
  for (const task of examTasks || []) {
    try {
      const fields = fieldsOf(task);
      const student = textField(fields, 'student_id'), subject = textField(fields, 'subject');
      const type = textField(fields, 'exam_type').toLowerCase().replace(/[\s-]+/g, '_');
      if (!examTypes.includes(type)) throw new Error(`unknown exam_type: ${fields.get('exam_type')}`);
      const target = numberOrNull(fields, 'target_score');
      if (target === null) throw new Error('target_score missing');
      keep(exams, `${student}|${subject}|${type}`, { student_id: student, subject, exam_type: type, target_score: target, actual_score: numberOrNull(fields, 'actual_score') }, task);
    } catch (e) { reject('exam_targets', task && task.id, e.message); }
  }
  const rows = { advisor_inputs: [...advisor.values()].map((x) => x.row), exam_targets: [...exams.values()].map((x) => x.row) };
  const counts = { advisor_inputs: rows.advisor_inputs.length, exam_targets: rows.exam_targets.length };
  const status = failedSources.length === 2 ? 'failed' : failedSources.length || rejects.length ? 'partial' : 'ok';
  const parts = [];
  if (failedSources.length) parts.push(`failed sources: ${failedSources.map((f) => `${f.source} (${f.error})`).join('; ')}`);
  if (rejects.length) parts.push(`${rejects.length} tasks rejected, for example ${rejects.slice(0, 3).map((r) => `${r.table} ${r.id}: ${r.reason}`).join('; ')}${rejects.length > 3 ? '; ...' : ''}`);
  return { status, rows, counts, rejects, failedSources, duplicates, note: parts.join(' | ').slice(0, 900) || null };
}

// The ingest_log row: written is how many rows the database reported, suppressed rows (a student not in the database) make the run partial.
function clickupLog({ result, written, runId, startedAt, finishedAt }, helpers) {
  const mapped = result.counts.advisor_inputs + result.counts.exam_targets;
  const total = Number(written.advisor_inputs) + Number(written.exam_targets);
  const suppressed = Number.isFinite(total) ? mapped - total : mapped;
  let status = result.status;
  if (status === 'ok' && suppressed > 0) status = 'partial';
  const note = [result.note, suppressed > 0 ? `${suppressed} rows skipped: student not in the database` : null, written.error ? `database error: ${String(written.error).slice(0, 200)}` : null]
    .filter(Boolean).join(' | ').slice(0, 1000) || null;
  if (written.error && status !== 'failed') status = mapped ? 'failed' : status;
  return { run_id: runId, source: 'clickup', started_at: helpers.toIst(startedAt), finished_at: helpers.toIst(finishedAt), status, rows_upserted: Number.isFinite(total) ? total : 0, error: status === 'ok' ? null : note };
}
if (typeof module !== 'undefined' && module.exports) module.exports = { mapClickUp, clickupLog };
