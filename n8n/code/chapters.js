/* Pure mapper for the explicit chapter demonstration contract. No clock or I/O.
 * Config is supplied from student-tracker/config.yaml. Supplemental evidence is
 * synthetic demonstration input, not a claimed Alcovia API response.
 */
'use strict';
function mapChapters(input, config, helpers) {
  if (input?.demo !== true) throw new Error('chapter demo mode must be explicit');
  const policy = config?.chapter_loader;
  const syllabus = config?.syllabus;
  const stages = ['reading', 'recollection', 'practice', 'timed_paper', 'readiness'];
  if (!policy || !syllabus || !Array.isArray(policy.stage_order) ||
      policy.stage_order.length !== syllabus.stages_total || new Set(policy.stage_order).size !== stages.length ||
      !policy.stage_order.every(s => stages.includes(s)) ||
      ![syllabus.practice_accuracy_pct, syllabus.readiness_accuracy_pct, policy.score_tolerance_pct].every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0) ||
      syllabus.practice_accuracy_pct > 100 || syllabus.readiness_accuracy_pct > 100 ||
      !Array.isArray(policy.allowed_task_types) || !Array.isArray(policy.incomplete_statuses) || !Array.isArray(policy.unknown_statuses) ||
      !['reading','recollection','practice'].every(s => Array.isArray(policy.task_types?.[s]) && policy.task_types[s].length && policy.task_types[s].every(t => policy.allowed_task_types.includes(t))) ||
      !policy.done_status || !policy.score_types?.practice || !policy.score_types?.readiness) throw new Error('invalid chapter loader configuration');
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const record = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  const id = x => typeof x === 'string' && x.trim().length > 0;
  const number = x => {
    check(typeof x === 'number' || typeof x === 'string' && /^\d+(?:\.\d+)?$/.test(x.trim()), 'invalid numeric score');
    const n = Number(x); check(Number.isFinite(n), 'invalid numeric score'); return n;
  };
  const day = x => typeof x === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(x) && !Number.isNaN(Date.parse(x+'T00:00:00Z')) && new Date(x+'T00:00:00Z').toISOString().slice(0,10) === x;
  check(id(input.studentId) && Array.isArray(input.chapters), 'invalid demo student or chapters list');
  const rows = [], rejects = [], chapterCounts = new Map();
  for (const chapter of input.chapters) {
    if (record(chapter) && id(chapter.id)) chapterCounts.set(chapter.id, (chapterCounts.get(chapter.id) || 0) + 1);
  }
  const unique = (array, predicate, label) => {
    check(Array.isArray(array), 'missing '+label);
    const matches = array.filter(x => record(x) && predicate(x));
    check(matches.length === 1, 'missing or ambiguous '+label); return matches[0];
  };
  for (const chapter of input.chapters) {
    try {
      check(record(chapter) && id(chapter.id), 'invalid chapter row');
      check(chapterCounts.get(chapter.id) === 1, 'duplicate chapter id');
      const subject = unique(input.subjects, x => x.id === chapter.subjectId, 'subject');
      const quarter = unique(input.quarters, x => x.id === chapter.quarterId, 'quarter');
      check(id(subject.name) && id(quarter.label) && day(quarter.startDate) && day(quarter.endDate) && quarter.startDate <= quarter.endDate, 'invalid subject or quarter');
      const linked = x => x.studentId === input.studentId && x.chapterId === chapter.id;
      const plan = unique(input.plans, linked, 'monthly plan');
      const extra = unique(input.supplement, linked, 'supplemental evidence');
      check(day(plan.plannedMonth) && plan.plannedMonth.endsWith('-01') && plan.plannedMonth >= quarter.startDate && plan.plannedMonth <= quarter.endDate, 'planned month outside quarter or not a month start');
      check(helpers.toIst(extra.stageChangedAt), 'missing or invalid actual stage-change timestamp');
      check(Array.isArray(chapter.tasks) && Array.isArray(chapter.scores), 'missing tasks or scores evidence');
      const tasks = new Map(), taskIds = new Set();
      for (const task of chapter.tasks) {
        check(record(task) && id(task.id) && !taskIds.has(task.id) && !tasks.has(task.taskType), 'invalid or duplicate task');
        check(policy.allowed_task_types.includes(task.taskType), 'unsupported task type');
        check([policy.done_status,...policy.incomplete_statuses,...policy.unknown_statuses].includes(task.taskStatus), 'unsupported task status');
        check(!task.chapterId || task.chapterId === chapter.id, 'task chapter mismatch');
        taskIds.add(task.id); tasks.set(task.taskType, task.taskStatus);
      }
      const taskDone = type => {
        const statuses = policy.task_types[type].map(key => tasks.get(key));
        if (statuses.includes(policy.done_status)) return true;
        if (statuses.every(s => policy.incomplete_statuses.includes(s))) return false;
        return null;
      };
      const scores = [], scoreIds = new Set();
      for (const score of chapter.scores) {
        check(record(score) && id(score.id) && !scoreIds.has(score.id), 'invalid or duplicate score'); scoreIds.add(score.id);
        check(!score.chapterId || score.chapterId === chapter.id, 'score chapter mismatch');
        check(Object.values(policy.score_types).includes(score.scoreType), 'unsupported score type');
        const marks = number(score.marksObtained), max = number(score.maxMarks), accuracy = number(score.accuracyPercentage);
        check(max > 0 && marks >= 0 && marks <= max && accuracy >= 0 && accuracy <= 100, 'score out of range');
        check(Math.abs(accuracy - 100*marks/max) <= policy.score_tolerance_pct, 'conflicting marks and percentage');
        check(helpers.toIst(score.recordedOn) && Number.isInteger(score.attemptNo) && score.attemptNo > 0, 'invalid score time or attempt');
        scores.push({...score, accuracy, time: Date.parse(score.recordedOn)});
      }
      const passed = (type, threshold) => {
        const ordered = scores.filter(s => s.scoreType === policy.score_types[type]).sort((a,b) => b.time-a.time || b.attemptNo-a.attemptNo);
        if (!ordered.length) return false;
        const latest = ordered[0];
        check(!ordered.some(s => s.time === latest.time && s.attemptNo === latest.attemptNo && s.accuracy !== latest.accuracy), 'conflicting latest score attempts');
        return latest.accuracy > threshold;
      };
      const practiceDone = taskDone('practice');
      const paper = extra.timedPaper;
      if (paper !== undefined) check(record(paper) && typeof paper.completed === 'boolean' && typeof paper.withinTime === 'boolean', 'invalid timed-paper evidence');
      const proofs = {
        reading: taskDone('reading'), recollection: taskDone('recollection'),
        practice: practiceDone === null ? null : practiceDone && passed('practice', syllabus.practice_accuracy_pct),
        timed_paper: paper ? paper.completed && paper.withinTime : null,
        readiness: passed('readiness', syllabus.readiness_accuracy_pct),
      };
      let stage = 0;
      for (const name of policy.stage_order) {
        check(proofs[name] !== null, 'unknown evidence for '+name);
        if (!proofs[name]) break;
        stage += 1;
      }
      rows.push({student_id: input.studentId, chapter_id: chapter.id, subject: subject.name.trim(), quarter: quarter.label,
                 planned_month: plan.plannedMonth, stage_reached: stage, updated_at: helpers.toIst(extra.stageChangedAt)});
    } catch (e) { rejects.push({chapter_id: chapter?.id ?? null, reason: e.message}); }
  }
  return {demo: true, status: rejects.length ? 'partial' : 'ok', rows, rejects};
}
if (typeof module !== 'undefined' && module.exports) module.exports = {mapChapters};
