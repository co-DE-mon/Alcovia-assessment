
// ---- n8n glue (the error workflow): turn n8n's error report into a failed ingest_log row ----
const report = $input.first().json;
const exec = report.execution || {};
const reportedError = exec.error || (report.trigger && report.trigger.error);
const where = [exec.lastNodeExecuted, reportedError && errorText(reportedError)].filter(Boolean).join(': ');
const now = toIst(new Date().toISOString());
const failure = `workflow ${(report.workflow && report.workflow.name) || 'unknown'} stopped${where ? ` at ${where}` : ''}`.slice(0, 1000);
const log = { run_id: `n8n-${exec.id !== undefined ? exec.id : `manual-${now.replace(/\D/g, '')}`}`, source: report.workflow && report.workflow.id === 'clickupAdvisorInputs01' ? 'clickup' : 'app_api', started_at: now, finished_at: now,
              status: 'failed', rows_upserted: 0, error: failure };
return [{ json: { log } }];
