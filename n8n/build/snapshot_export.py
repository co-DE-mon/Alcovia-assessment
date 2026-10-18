#!/usr/bin/env python3
"""Generate the scheduled dashboard-snapshot workflow: Postgres -> validated DuckDB snapshot via student-tracker/snapshot.py.
python3 -B n8n/build/snapshot_export.py [--check] [--test OUTFILE COMMAND_PREFIX]
The shareable export is inactive and credential-free. The Postgres password is never in the workflow: snapshot.py's psql reads PGPASSWORD or ~/.pgpass on the n8n host.
--test writes a copy whose command is COMMAND_PREFIX followed by the same arguments, so a harness can run the node without python, psql or duckdb.
"""
import argparse
import json
from pathlib import Path

import build as shared

ROOT = Path(__file__).resolve().parents[2]
N8N = ROOT / 'n8n'

# Every setting is interpolated into a shell command, so each must be a plain path/identifier. Checked before anything runs.
CHECK = r'''const s = $input.first().json;
const SAFE = /^[A-Za-z0-9_.\/:@-]+$/;
for (const key of ['python', 'script', 'database', 'user', 'output', 'asOf']) {
  if (typeof s[key] !== 'string' || !SAFE.test(s[key])) throw new Error('setting ' + key + ' is empty or has characters outside A-Z a-z 0-9 _ . / : @ -');
}
if (s.container !== '' && !SAFE.test(s.container)) throw new Error('setting container has unsafe characters');
if (!/^\d{4}-\d{2}-\d{2}$/.test(s.asOf)) throw new Error('asOf must be YYYY-MM-DD');
return [{ json: s }];'''

SUMMARY = '''const r = $input.first().json;
const out = String(r.stdout || '').trim();
if (r.exitCode !== 0 || !out.includes('Published validated synthetic student snapshot')) {
  throw new Error('snapshot export did not confirm publication (exit ' + r.exitCode + '); the previous snapshot is unchanged');
}
return [{ json: { status: 'ok', asOf: $('Check settings').first().json.asOf, output: $('Check settings').first().json.output } }];'''


def generate(command_prefix=None):
    command = ("={{ " + (json.dumps(command_prefix) + " + ' ' + " if command_prefix else "") + "$json.python + ' ' + $json.script"
               " + ($json.container ? ' --container ' + $json.container : '') + ' --database ' + $json.database + ' --user ' + $json.user"
               " + ' --output ' + $json.output + ' --as-of ' + $json.asOf }}")
    s = shared.node
    nodes = [
        s('Schedule (daily 00:30 IST)', 'n8n-nodes-base.scheduleTrigger', 1.2, {'rule': {'interval': [{'field': 'cronExpression', 'expression': '30 0 * * *'}]}}, (0, 0)),
        s('Run now', 'n8n-nodes-base.manualTrigger', 1, {}, (0, 160)),
        s('Settings', 'n8n-nodes-base.set', 3.4, {'assignments': {'assignments': [
            {'id': shared.uid('snap-python'), 'name': 'python', 'value': '/opt/alcovia/student-tracker/.venv/bin/python', 'type': 'string'},
            {'id': shared.uid('snap-script'), 'name': 'script', 'value': '/opt/alcovia/student-tracker/snapshot.py', 'type': 'string'},
            {'id': shared.uid('snap-db'), 'name': 'database', 'value': 'student', 'type': 'string'},
            {'id': shared.uid('snap-user'), 'name': 'user', 'value': 'postgres', 'type': 'string'},
            {'id': shared.uid('snap-out'), 'name': 'output', 'value': '/var/lib/alcovia/student.duckdb', 'type': 'string'},
            {'id': shared.uid('snap-container'), 'name': 'container', 'value': '', 'type': 'string'},
            {'id': shared.uid('snap-asof'), 'name': 'asOf', 'value': "={{ $now.setZone('Asia/Kolkata').minus({ days: 1 }).toFormat('yyyy-MM-dd') }}", 'type': 'string'}]}, 'includeOtherFields': False, 'options': {}}, (260, 80)),
        s('Check settings', 'n8n-nodes-base.code', 2, {'mode': 'runOnceForAllItems', 'language': 'javaScript', 'jsCode': CHECK}, (520, 80)),
        # Failure is loud on purpose: a non-zero exit fails this node, and error executions are kept (no credentials or tokens pass through here).
        s('Export snapshot', 'n8n-nodes-base.executeCommand', 1, {'command': command}, (780, 80)),
        s('Confirm published', 'n8n-nodes-base.code', 2, {'mode': 'runOnceForAllItems', 'language': 'javaScript', 'jsCode': SUMMARY}, (1040, 80)),
        s('About this workflow', 'n8n-nodes-base.stickyNote', 1, {'width': 760, 'height': 330, 'content':
            "## Dashboard snapshot export\n\nRuns after the 23:55 poll (00:30 IST) and replaces the dashboard's DuckDB snapshot, so nobody has to export it by hand. "
            "snapshot.py reads all tables in one repeatable-read transaction, validates the whole cohort and swaps the file atomically. On any failure the previous snapshot stays in place and this run fails.\n\n"
            "Needs on the n8n host: the repo, python with duckdb, psql, PGPASSWORD or ~/.pgpass for the database, and the Execute Command node enabled "
            "(n8n disables it by default; remove `n8n-nodes-base.executeCommand` from NODES_EXCLUDE). Change the paths in Settings. "
            "snapshot.py refuses any cohort that is not DEMO- synthetic data. Inactive until you switch it on."}, (0, -420)),
    ]
    wf = {'id': 'snapshotExport01', 'name': 'Dashboard snapshot export', 'active': False, 'nodes': nodes,
          'connections': {**shared.chain('Settings', 'Check settings', 'Export snapshot', 'Confirm published'),
                          'Schedule (daily 00:30 IST)': {'main': [[{'node': 'Settings', 'type': 'main', 'index': 0}]]},
                          'Run now': {'main': [[{'node': 'Settings', 'type': 'main', 'index': 0}]]}},
          'tags': [], 'settings': {'executionOrder': 'v1', 'timezone': 'Asia/Kolkata', 'saveDataSuccessExecution': 'none', 'saveDataErrorExecution': 'all', 'saveManualExecutions': False, 'executionTimeout': 300},
          'meta': {'templateCredsSetupCompleted': False}}
    return wf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--test', nargs=2, metavar=('OUTFILE', 'COMMAND_PREFIX'))
    args = parser.parse_args()
    path, text = N8N/'snapshot-export.json', json.dumps(generate(), indent=2)+'\n'
    if args.check:
        if not path.exists() or path.read_text() != text:
            raise SystemExit('Stale generated snapshot export: '+str(path))
    else:
        path.write_text(text)
    if args.test:
        Path(args.test[0]).write_text(json.dumps(generate(args.test[1]), indent=2)+'\n')
    print('Snapshot export matches sources.' if args.check else 'Generated snapshot export workflow.')


if __name__ == '__main__':
    main()
