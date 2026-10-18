
// ---- n8n glue (the Normalise node): collect the HTTP nodes' outputs, run normalise(), emit one item per table with the SQL to run ----
const SQL = /*__SQL__*/ {};
const pick = (name) => {
  try { return $(name).all().map((i) => i.json); } catch (e) { return [{ error: `node ${name} did not run` }]; }
};
const result = normalise({
  runAt: new Date().toISOString(),
  sources: {
    signin: pick('Sign in'), me: pick('Fetch profile'), whoop: pick('Fetch wearable status'), timeBudget: pick('Fetch time budget'),
    focus: pick('Fetch focus today'), todos: pick('Fetch todos'), sessions: pick('Fetch sessions'), syllabus: pick('Fetch syllabus history'),
    wellness: pick('Fetch wellness history'),
    annual: pick('Fetch annual goals'), quarterly: pick('Fetch quarterly goals'),
  },
});
const run = { status: result.status, rowsTotal: result.rowsTotal, note: result.note, runAtIst: result.runAtIst, counts: result.counts };
const items = TABLE_ORDER.filter((t) => result.rows[t].length).map((t) => ({ table: t, rows: result.rows[t], sql: SQL[t], run }));
// Nothing to write still has to reach the log step, so a harmless statement stands in for the table batch.
if (!items.length) items.push({ table: 'none', rows: [], sql: 'SELECT 0::int AS upserted', run });
return items.map((json) => ({ json }));
