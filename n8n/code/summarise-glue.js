
// ---- n8n glue (the Summarise run node): final status from the normaliser's result and what the database said about each table ----
const run = $('Normalise').first().json.run;
const tables = $('Normalise').all().map((i) => ({ table: i.json.table }));
const tableResults = $('Upsert table').all().map((i) => i.json);
const execId = $execution.id !== undefined && $execution.id !== null ? $execution.id : `manual-${run.runAtIst.replace(/\D/g, '')}`;
const log = summarise({ run, tables, tableResults, runId: `n8n-${execId}`, finishedAt: new Date().toISOString() });
return [{ json: { log } }];
