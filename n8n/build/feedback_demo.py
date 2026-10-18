#!/usr/bin/env python3
"""Generate an inactive manual feedback demo from the explicit fixture and shared YAML.
python3 -B n8n/build/feedback_demo.py [--check] [--test OUTFILE]
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
    rules = {k: config[k] for k in ('feedback_loader',)}
    pack = json.loads((N8N/'tests/fixtures/demo/feedback-input.json').read_text())
    tables = shared.parse_tables(shared.SCHEMA.read_text())
    columns=tables['feedback']['columns']
    select_cols=', '.join('f.'+c for c in columns)
    updates=', '.join(c+'=EXCLUDED.'+c for c in columns if c!='feedback_id')
    same=' AND '.join('feedback.'+c+' IS NOT DISTINCT FROM EXCLUDED.'+c for c in columns if c!='feedback_id')
    sql=f"""WITH up AS (
      INSERT INTO feedback ({', '.join(columns)})
      SELECT {select_cols} FROM json_populate_recordset(NULL::feedback, $1::json->'rows') f
      WHERE EXISTS (SELECT 1 FROM students s WHERE s.student_id=f.student_id)
        AND ((f.event_id IS NULL AND f.kind IN (SELECT json_array_elements_text($1::json->'monthlyKinds')))
          OR EXISTS (SELECT 1 FROM events e WHERE e.event_id=f.event_id AND e.status='held'
             AND e.planned_for <= f.submitted_at
             AND e.kind IN (SELECT json_array_elements_text(($1::json->'kindEventMap')->f.kind))))
        AND NOT EXISTS (SELECT 1 FROM feedback old WHERE old.feedback_id<>f.feedback_id
          AND old.student_id=f.student_id
          AND ((f.event_id IS NOT NULL AND old.event_id=f.event_id)
            OR (f.event_id IS NULL AND old.event_id IS NULL AND old.kind=f.kind
              AND date_trunc('month', old.submitted_at)=date_trunc('month', f.submitted_at))))
      ON CONFLICT (feedback_id) DO UPDATE SET {updates}
      WHERE {same}
      RETURNING 1
    ) SELECT count(*)::int AS upserted FROM up"""
    source = (N8N/'code/normalise.js').read_text() + '\n' + (N8N/'code/feedback.js').read_text()
    mapper = source + '\nconst feedbackResult = mapFeedback($("Demo inputs").first().json.evidence, '+json.dumps(rules)+', {toIst, istDate});\nreturn [{json: {...feedbackResult, sql: '+json.dumps(sql)+'}}];\n'
    creds = {'postgres': {'id':credential,'name':'Student tracker DEMO Postgres'}} if credential else {}
    nodes = [
        shared.node('Run demo','n8n-nodes-base.manualTrigger',1,{},(0,0)),
        shared.node('Demo inputs','n8n-nodes-base.set',3.4,{'assignments':{'assignments':[{'id':shared.uid('feedback-evidence'),'name':'evidence','value':pack,'type':'object'}]},'includeOtherFields':False,'options':{}},(260,0)),
        shared.node('Map feedback','n8n-nodes-base.code',2,{'mode':'runOnceForAllItems','language':'javaScript','jsCode':mapper},(520,0)),
        shared.node('Upsert demo feedback','n8n-nodes-base.postgres',2.6,{'operation':'executeQuery','query':'={{ $json.sql }}','options':{'queryReplacement':'={{ JSON.stringify({rows:$json.rows,kindEventMap:'+json.dumps(rules['feedback_loader']['kind_event_map'])+',monthlyKinds:'+json.dumps(rules['feedback_loader']['monthly_kinds'])+'}) }}'}},(780,0),credentials=creds,retryOnFail=True,maxTries=3,waitBetweenTries=2000),
        shared.node('Demo summary','n8n-nodes-base.code',2,{'mode':'runOnceForAllItems','language':'javaScript','jsCode':'const mapped = $("Map feedback").first().json;\nconst saved=Number($input.first().json.upserted); const skipped=mapped.rows.length-saved;\nreturn [{json:{demo:true,status:skipped ? "partial" : mapped.status,upserted:saved,skippedWrites:skipped,rejected:mapped.rejects,notice:"Synthetic demonstration; live feedback mapping unverified"}}];'},(1040,0)),
        shared.node('About the demo','n8n-nodes-base.stickyNote',1,{'width':900,'height':240,'content':'## Submitted feedback demonstration\n\nManual only. Demo inputs are synthetic admin-shaped submitted pages and a PROPOSED feedback export. This does not read pending lists or submit new feedback. Raw comments are reduced to a boolean. Rules and thresholds come from student-tracker/config.yaml; regenerate this export after changing them.\n\nAttach a credential for a disposable DEMO Postgres database with the student-tracker schema. Database failures stop the visible manual run after retries. No Alcovia API is called. Unknown evidence is reported, not invented. Demo summary shows rejected rows. This does not update live pipeline freshness.'},(0,-300)),
    ]
    wf={'id':'submittedFeedbackDemo01','name':'Submitted feedback DEMO (synthetic inputs)','active':False,'nodes':nodes,
        'connections':shared.chain('Run demo','Demo inputs','Map feedback','Upsert demo feedback','Demo summary'),
        'settings':{'executionOrder':'v1','timezone':'Asia/Kolkata','saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False,'executionTimeout':120}}
    return wf,sql


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--test',type=Path)
    args=parser.parse_args()
    workflow,sql=generate()
    outputs={N8N/'submitted-feedback-demo.json':json.dumps(workflow,indent=2)+'\n', N8N/'sql/feedback-demo-upsert.sql':'-- Generated by n8n/build/feedback_demo.py; explicit demonstration only.\n'+sql+';\n'}
    for path,text in outputs.items():
        if args.check:
            if not path.exists() or path.read_text()!=text:
                raise SystemExit('Stale generated feedback demo: '+str(path))
        else:path.write_text(text)
    if args.test:
        args.test.write_text(json.dumps(generate('testPostgres01')[0],indent=2)+'\n')
    print('Feedback demo matches sources.' if args.check else 'Generated feedback demo workflow and SQL.')


if __name__=='__main__':main()
