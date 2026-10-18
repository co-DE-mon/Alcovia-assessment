#!/usr/bin/env python3
"""Generates the inactive ClickUp advisor-inputs workflow and its SQL from code/clickup.js, the schema and student-tracker/config.yaml.
python3 n8n/build/clickup.py [--check] [--test OUTFILE BASE_URL]
The shareable export has no credential bindings and placeholder list ids. The ClickUp structure it reads is an ASSUMPTION: see the ClickUp assumptions in n8n/README.md.
"""
import argparse
import json
from pathlib import Path
import yaml
import build as shared

ROOT = Path(__file__).resolve().parents[2]
N8N = ROOT / 'n8n'
WORKFLOW_ID = 'clickupAdvisorInputs01'
EXAM_TYPES = ['formative', 'unit_test', 'mid_term']      # the exam_targets CHECK constraint


def statement():
    tables = shared.parse_tables(shared.SCHEMA.read_text())
    parts = []
    for table, alias in (('advisor_inputs', 'a'), ('exam_targets', 'e')):
        spec = tables[table]
        cols = ', '.join(spec['columns'])
        sets = ', '.join(f'{c} = EXCLUDED.{c}' for c in spec['columns'] if c not in spec['pk'])
        parts.append(f"{table}_write AS (\n  INSERT INTO {table} ({cols})\n  SELECT {', '.join(alias + '.' + c for c in spec['columns'])}\n"
                     f"  FROM json_populate_recordset(NULL::{table}, $1::json->'{table}') {alias}\n"
                     f"  WHERE EXISTS (SELECT 1 FROM students s WHERE s.student_id = {alias}.student_id)\n"
                     f"  ON CONFLICT ({', '.join(spec['pk'])}) DO UPDATE SET {sets}\n  RETURNING 1\n)")
    return 'WITH ' + ',\n'.join(parts) + '\nSELECT (SELECT count(*)::int FROM advisor_inputs_write) AS advisor_inputs, (SELECT count(*)::int FROM exam_targets_write) AS exam_targets'


GLUE_MAP = """// ---- n8n glue (Map ClickUp): collect the two paged reads, run mapClickUp(), hand one payload to the database step ----
const pick = (name) => {
  try { return $(name).all().map((i) => i.json); } catch (e) { return [{ error: `node ${name} did not run` }]; }
};
const s = $('Settings').first().json;
const config = { advisor_input_kinds: %(kinds)s, exam_types: %(types)s, score_max: Number(s.scoreMax) };
const result = mapClickUp({ advisor: pick('Fetch advisor tasks'), exams: pick('Fetch exam tasks') }, config, { toIst });
return [{ json: { result, payload: result.rows, startedAt: new Date().toISOString() } }];
"""
GLUE_SUMMARISE = """// ---- n8n glue (Summarise run): the ingest_log row, from what the mapper said and what the database reported ----
const mapped = $('Map ClickUp').first().json;
const saved = $('Upsert ClickUp rows').first().json;
const written = saved && saved.error ? { error: errorText(saved.error) } : saved;
const execId = $execution.id !== undefined && $execution.id !== null ? $execution.id : `manual-${toIst(mapped.startedAt).replace(/\\D/g, '')}`;
const log = clickupLog({ result: mapped.result, written, runId: `clickup-${execId}`, startedAt: mapped.startedAt, finishedAt: new Date().toISOString() }, { toIst });
return [{ json: { log } }];
"""


def generate(base_url='https://api.clickup.com/api/v2', advisor_list='REPLACE_WITH_ADVISOR_LIST_ID', exam_list='REPLACE_WITH_EXAM_LIST_ID', creds=None):
    config = yaml.safe_load((ROOT / 'student-tracker/config.yaml').read_text())
    kinds = config['advisor_input_kinds']
    sql = statement()
    code = '\n'.join((N8N / 'code' / name).read_text() for name in ('normalise.js', 'clickup.js'))
    pg = {'postgres': {'id': creds['postgres'], 'name': 'Student tracker Postgres'}} if creds else {}
    http = {'httpHeaderAuth': {'id': creds['http'], 'name': 'ClickUp API token'}} if creds else {}
    retry = {'retryOnFail': True, 'maxTries': 3, 'waitBetweenTries': 2000}

    def fetch(name, list_key, pos):
        params = {'method': 'GET', 'url': f"={{{{ $('Settings').first().json.baseUrl }}}}/list/{{{{ $('Settings').first().json.{list_key} }}}}/task",
                  'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth',
                  'sendQuery': True, 'queryParameters': {'parameters': [{'name': 'page', 'value': '0'}, {'name': 'include_closed', 'value': 'true'}]},
                  'options': {'timeout': 30000, 'pagination': {'pagination': {
                      'paginationMode': 'updateAParameterInEachRequest',
                      'parameters': {'parameters': [{'type': 'qs', 'name': 'page', 'value': '={{ $pageCount }}'}]},
                      'paginationCompleteWhen': 'other', 'completeExpression': '={{ $response.body.last_page === true }}',
                      'limitPagesFetched': True, 'maxRequests': 50}}}}
        # A failed read must not stop the run: the mapper reports it as a failed source and the run is logged partial.
        return shared.node(name, 'n8n-nodes-base.httpRequest', 4.2, params, pos, credentials=http, onError='continueRegularOutput', alwaysOutputData=True, executeOnce=True, **retry)

    nodes = [
        shared.node('Schedule (daily 03:00 IST)', 'n8n-nodes-base.scheduleTrigger', 1.2, {'rule': {'interval': [{'field': 'cronExpression', 'expression': '0 3 * * *'}]}}, (0, 0)),
        shared.node('Run now', 'n8n-nodes-base.manualTrigger', 1, {}, (0, 160)),
        shared.node('Settings', 'n8n-nodes-base.set', 3.4, {'assignments': {'assignments': [
            {'id': shared.uid('ck1'), 'name': 'baseUrl', 'value': base_url, 'type': 'string'},
            {'id': shared.uid('ck2'), 'name': 'advisorListId', 'value': advisor_list, 'type': 'string'},
            {'id': shared.uid('ck3'), 'name': 'examListId', 'value': exam_list, 'type': 'string'},
            {'id': shared.uid('ck4'), 'name': 'scoreMax', 'value': 100, 'type': 'number'}]}, 'includeOtherFields': False, 'options': {}}, (260, 80)),
        fetch('Fetch advisor tasks', 'advisorListId', (520, 80)),
        fetch('Fetch exam tasks', 'examListId', (780, 80)),
        shared.node('Map ClickUp', 'n8n-nodes-base.code', 2, {'mode': 'runOnceForAllItems', 'language': 'javaScript',
                    'jsCode': code + '\n' + GLUE_MAP % {'kinds': json.dumps(kinds), 'types': json.dumps(EXAM_TYPES)}}, (1040, 80)),
        shared.node('Upsert ClickUp rows', 'n8n-nodes-base.postgres', 2.6, {'operation': 'executeQuery', 'query': sql,
                    'options': {'queryReplacement': '={{ JSON.stringify($json.payload) }}'}}, (1300, 80), credentials=pg, onError='continueRegularOutput', retryOnFail=True, maxTries=2, waitBetweenTries=2000),
        shared.node('Summarise run', 'n8n-nodes-base.code', 2, {'mode': 'runOnceForAllItems', 'language': 'javaScript', 'jsCode': code + '\n' + GLUE_SUMMARISE}, (1560, 80)),
        shared.node('Log run', 'n8n-nodes-base.postgres', 2.6, {'operation': 'executeQuery', 'query': shared.LOG_SQL, 'options': {'queryReplacement': '={{ JSON.stringify($json.log) }}'}},
                    (1820, 80), credentials=pg, **retry),
        shared.node('About this workflow', 'n8n-nodes-base.stickyNote', 1, {'width': 900, 'height': 330, 'content':
            '## ClickUp advisor inputs and exam targets\n\nReads two ClickUp lists, maps the tasks to `advisor_inputs` and `exam_targets`, upserts them and logs the run (`ingest_log`, source `clickup`).\n\n'
            '**The ClickUp structure is an ASSUMPTION** (one task per student-month with a checkbox per advisor input; one task per student/subject/exam type). See the ClickUp assumptions in n8n/README.md.\n\n'
            '- Replace the two list ids in *Settings*; attach a Header Auth credential named *ClickUp API token* (name `Authorization`, value your personal token) to both fetch nodes.\n'
            '- A failed read is logged `partial` and never treated as an empty list. A task with an unknown value is rejected and named; the rest load.\n'
            '- Re-running changes nothing: `INSERT ... ON CONFLICT DO UPDATE` on the table keys. Students not in the database are skipped and counted.\n\nInactive until you switch it on.'}, (0, -380)),
    ]
    names = ['Settings', 'Fetch advisor tasks', 'Fetch exam tasks', 'Map ClickUp', 'Upsert ClickUp rows', 'Summarise run', 'Log run']
    conns = shared.chain(*names)
    for trigger in ('Schedule (daily 03:00 IST)', 'Run now'):
        conns[trigger] = {'main': [[{'node': 'Settings', 'type': 'main', 'index': 0}]]}
    wf = {'name': 'ClickUp advisor inputs and exam targets', 'id': WORKFLOW_ID, 'nodes': nodes, 'connections': conns, 'active': False, 'tags': [],
          'settings': {'executionOrder': 'v1', 'timezone': 'Asia/Kolkata', 'saveDataSuccessExecution': 'none', 'saveDataErrorExecution': 'none', 'saveManualExecutions': False, 'executionTimeout': 300, 'errorWorkflow': 'ingestErrorHandler01'},
          'meta': {'templateCredsSetupCompleted': False}}
    return wf, sql


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--test', nargs=2, metavar=('OUTFILE', 'BASE_URL'))
    args = ap.parse_args()
    wf, sql = generate()
    outputs = {N8N / 'clickup-advisor-inputs.json': json.dumps(wf, indent=2, ensure_ascii=False) + '\n',
               N8N / 'sql/clickup-upsert.sql': '-- GENERATED by n8n/build/clickup.py. $1 is {"advisor_inputs": [...], "exam_targets": [...]}.\n' + sql + ';\n'}
    for path, text in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                raise SystemExit('Stale generated ClickUp workflow: ' + str(path))
        else:
            path.write_text(text)
    if args.test:
        out, base = args.test
        Path(out).write_text(json.dumps(generate(base, 'ADVISOR1', 'EXAMS1', {'postgres': 'testPostgres01', 'http': 'testClickUpAuth01'})[0], indent=2) + '\n')
    print('ClickUp workflow matches sources.' if args.check else 'Generated ClickUp workflow and SQL.')


if __name__ == '__main__':
    main()
