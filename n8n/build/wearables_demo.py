#!/usr/bin/env python3
"""Generate an inactive manual Apple/Samsung/Garmin sleep demo from the explicit fixture and shared YAML.
python3 -B n8n/build/wearables_demo.py [--check] [--test OUTFILE]
PyYAML is already a student-tracker dependency. No network calls or credentials.
"""
import argparse
import json
from pathlib import Path

import yaml
import build as shared

ROOT = Path(__file__).resolve().parents[2]
N8N = ROOT / 'n8n'


def generate(credential=None):
    config = yaml.safe_load((ROOT/'student-tracker/config.yaml').read_text())
    rules = {k: config[k] for k in ('wearable_loader',)}
    pack = json.loads((N8N/'tests/fixtures/demo/wearables-input.json').read_text())
    tables = shared.parse_tables(shared.SCHEMA.read_text())
    fields = ('strain', 'recovery_pct', 'sleep_hours')
    shared.KEEP['wearable_daily'] = {field: f"CASE WHEN wearable_daily.data_source=EXCLUDED.data_source THEN COALESCE(EXCLUDED.{field}, wearable_daily.{field}) ELSE EXCLUDED.{field} END" for field in fields}
    # A vendor reading may replace manual sleep or its own earlier reading, never another device's row (a measured Whoop day stays Whoop).
    guard = "wearable_daily.data_source=EXCLUDED.data_source OR wearable_daily.data_source='manual'"
    columns = tables['wearable_daily']['columns']
    sql = shared.upsert_sql('wearable_daily', tables['wearable_daily']).replace('\n  RETURNING 1', '\n  WHERE '+guard+'\n  RETURNING 1')
    sql = sql.replace('SELECT '+', '.join(columns)+' FROM json_populate_recordset', 'SELECT '+', '.join('incoming.'+c for c in columns)+' FROM json_populate_recordset')
    sql = sql.replace('$1::json)\n', '$1::json) incoming\n  WHERE EXISTS (SELECT 1 FROM students s WHERE s.student_id=incoming.student_id)\n')
    source = (N8N/'code/normalise.js').read_text() + '\n' + (N8N/'code/wearables.js').read_text()
    mapper = source + '\nconst wearableResult = mapWearables($("Demo inputs").first().json.evidence, '+json.dumps(rules)+', {toIst, istDate});\nreturn [{json: {...wearableResult, sql: '+json.dumps(sql)+'}}];\n'
    creds = {'postgres': {'id': credential, 'name': 'Student tracker DEMO Postgres'}} if credential else {}
    summary = ('const mapped = $("Map wearables").first().json;\nconst saved=Number($input.first().json.upserted); const skipped=mapped.rows.length-saved;\n'
               'return [{json:{demo:true,status:skipped ? "partial" : mapped.status,upserted:saved,skippedWrites:skipped,rejected:mapped.rejects,'
               'notice:"Synthetic demonstration; vendor field names are assumed and unverified"}}];')
    nodes = [
        shared.node('Run demo', 'n8n-nodes-base.manualTrigger', 1, {}, (0, 0)),
        shared.node('Demo inputs', 'n8n-nodes-base.set', 3.4, {'assignments': {'assignments': [{'id': shared.uid('wearables-evidence'), 'name': 'evidence', 'value': pack, 'type': 'object'}]}, 'includeOtherFields': False, 'options': {}}, (260, 0)),
        shared.node('Map wearables', 'n8n-nodes-base.code', 2, {'mode': 'runOnceForAllItems', 'language': 'javaScript', 'jsCode': mapper}, (520, 0)),
        shared.node('Upsert demo wearables', 'n8n-nodes-base.postgres', 2.6, {'operation': 'executeQuery', 'query': '={{ $json.sql }}', 'options': {'queryReplacement': '={{ JSON.stringify($json.rows) }}'}}, (780, 0), credentials=creds, retryOnFail=True, maxTries=3, waitBetweenTries=2000),
        shared.node('Demo summary', 'n8n-nodes-base.code', 2, {'mode': 'runOnceForAllItems', 'language': 'javaScript', 'jsCode': summary}, (1040, 0)),
        shared.node('About the demo', 'n8n-nodes-base.stickyNote', 1, {'width': 900, 'height': 240, 'content': '## Apple, Samsung and Garmin sleep demonstration\n\nManual only. Demo inputs are synthetic daily sleep totals in each vendor\'s assumed field names and units. Only sleep_hours is filled: these vendors give no strain or recovery comparable to Whoop, so those stay unknown. One device per student-day; conflicting readings are skipped and named. A vendor reading never overwrites another device\'s row. Rules come from student-tracker/config.yaml; regenerate this export after changing them.\n\nAttach a credential for a disposable DEMO Postgres database with the student-tracker schema. No vendor API is called. This does not update live pipeline freshness.'}, (0, -300)),
    ]
    wf = {'id': 'wearablesDailyDemo01', 'name': 'Wearables sleep DEMO - Apple, Samsung, Garmin (synthetic inputs)', 'active': False, 'nodes': nodes,
          'connections': shared.chain('Run demo', 'Demo inputs', 'Map wearables', 'Upsert demo wearables', 'Demo summary'),
          'settings': {'executionOrder': 'v1', 'timezone': 'Asia/Kolkata', 'saveDataSuccessExecution': 'none', 'saveDataErrorExecution': 'none', 'saveManualExecutions': False, 'executionTimeout': 120}}
    return wf, sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--test', type=Path)
    args = parser.parse_args()
    workflow, sql = generate()
    outputs = {N8N/'wearables-daily-demo.json': json.dumps(workflow, indent=2)+'\n', N8N/'sql/wearables-demo-upsert.sql': '-- Generated by n8n/build/wearables_demo.py; explicit demonstration only.\n'+sql+';\n'}
    for path, text in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                raise SystemExit('Stale generated wearables demo: '+str(path))
        else:
            path.write_text(text)
    if args.test:
        args.test.write_text(json.dumps(generate('testPostgres01')[0], indent=2)+'\n')
    print('Wearables demo matches sources.' if args.check else 'Generated wearables demo workflow and SQL.')


if __name__ == '__main__':
    main()
