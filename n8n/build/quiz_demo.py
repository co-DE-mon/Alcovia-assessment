#!/usr/bin/env python3
"""Generate an inactive manual quiz demo from the explicit fixture and shared YAML.
python3 -B n8n/build/quiz_demo.py [--check] [--test OUTFILE]
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
    rules = {k: config[k] for k in ('quiz_loader','quiz')}
    pack = json.loads((N8N/'tests/fixtures/demo/quiz-input.json').read_text())
    tables = shared.parse_tables(shared.SCHEMA.read_text())
    event_cols = tables['events']['columns']
    attempt_cols = tables['quiz_attempts']['columns']
    final = "CASE WHEN events.status IN ('held','cancelled') AND EXCLUDED.status='planned' THEN events.status ELSE EXCLUDED.status END" if rules['quiz_loader']['preserve_final_status'] else 'EXCLUDED.status'
    event_updates = ', '.join(f"{c} = {final if c == 'status' else 'EXCLUDED.'+c}" for c in event_cols if c != 'event_id')
    attempt_updates = ', '.join(f"{c} = COALESCE(EXCLUDED.{c}, quiz_attempts.{c})" for c in attempt_cols if c not in ('event_id','student_id','started_at'))
    sql = f"""WITH saved_events AS (
      INSERT INTO events ({', '.join(event_cols)})
      SELECT {', '.join(event_cols)} FROM json_populate_recordset(NULL::events, $1::json->'events')
      ON CONFLICT (event_id) DO UPDATE SET {event_updates}
      WHERE events.kind='quiz'
      RETURNING event_id
    ), saved_attempts AS (
      INSERT INTO quiz_attempts ({', '.join(attempt_cols)})
      SELECT {', '.join('a.'+c for c in attempt_cols)}
      FROM json_populate_recordset(NULL::quiz_attempts, $1::json->'attempts') a
      JOIN saved_events e ON e.event_id=a.event_id
      WHERE EXISTS (SELECT 1 FROM students s WHERE s.student_id=a.student_id)
      ON CONFLICT (event_id,student_id) DO UPDATE SET {attempt_updates}
      WHERE quiz_attempts.started_at=EXCLUDED.started_at
        AND (quiz_attempts.completed_at IS NULL OR (EXCLUDED.completed_at = quiz_attempts.completed_at
             AND EXCLUDED.score IS NOT DISTINCT FROM quiz_attempts.score
             AND EXCLUDED.total_questions IS NOT DISTINCT FROM quiz_attempts.total_questions))
      RETURNING 1
    ) SELECT (SELECT count(*)::int FROM saved_events) AS events_upserted,
             (SELECT count(*)::int FROM saved_attempts) AS attempts_upserted"""
    source = (N8N/'code/normalise.js').read_text() + '\n' + (N8N/'code/quizzes.js').read_text()
    mapper = source + '\nconst quizResult = mapQuizzes($("Demo inputs").first().json.evidence, '+json.dumps(rules)+', {toIst, istDate});\nreturn [{json: {...quizResult, sql: '+json.dumps(sql)+'}}];\n'
    creds = {'postgres': {'id':credential,'name':'Student tracker DEMO Postgres'}} if credential else {}
    nodes = [
        shared.node('Run demo','n8n-nodes-base.manualTrigger',1,{},(0,0)),
        shared.node('Demo inputs','n8n-nodes-base.set',3.4,{'assignments':{'assignments':[{'id':shared.uid('quiz-evidence'),'name':'evidence','value':pack,'type':'object'}]},'includeOtherFields':False,'options':{}},(260,0)),
        shared.node('Map quizzes','n8n-nodes-base.code',2,{'mode':'runOnceForAllItems','language':'javaScript','jsCode':mapper},(520,0)),
        shared.node('Upsert demo quizzes','n8n-nodes-base.postgres',2.6,{'operation':'executeQuery','query':'={{ $json.sql }}','options':{'queryReplacement':'={{ JSON.stringify({events:$json.events,attempts:$json.attempts}) }}'}},(780,0),credentials=creds,retryOnFail=True,maxTries=3,waitBetweenTries=2000),
        shared.node('Demo summary','n8n-nodes-base.code',2,{'mode':'runOnceForAllItems','language':'javaScript','jsCode':'const mapped = $("Map quizzes").first().json;\nconst saved=$input.first().json; const skipped=mapped.events.length-Number(saved.events_upserted)+mapped.attempts.length-Number(saved.attempts_upserted);\nreturn [{json:{demo:true,status:skipped ? "partial" : mapped.status,skippedWrites:skipped,eventsUpserted:Number($input.first().json.events_upserted),attemptsUpserted:Number($input.first().json.attempts_upserted),rejected:mapped.rejects,notice:"Synthetic demonstration; live quiz mapping unverified"}}];'},(1040,0)),
        shared.node('About the demo','n8n-nodes-base.stickyNote',1,{'width':900,'height':240,'content':'## Quiz progress demonstration\n\nManual only. Demo inputs are synthetic and include separate delivery evidence and student attempts. Rules and thresholds come from student-tracker/config.yaml; regenerate this export after changing them.\n\nAttach a credential for a disposable DEMO Postgres database with the student-tracker schema. No Alcovia API is called. Unknown evidence is reported. Delivery and attempts are stored atomically; database errors fail the manual run visibly. Demo summary shows rejected rows. This does not update live pipeline freshness.'},(0,-300)),
    ]
    wf={'id':'quizProgressDemo01','name':'Quiz progress DEMO (synthetic inputs)','active':False,'nodes':nodes,
        'connections':shared.chain('Run demo','Demo inputs','Map quizzes','Upsert demo quizzes','Demo summary'),
        'settings':{'executionOrder':'v1','timezone':'Asia/Kolkata','saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False,'executionTimeout':120}}
    return wf,sql


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--test',type=Path)
    args=parser.parse_args()
    workflow,sql=generate()
    outputs={N8N/'quiz-progress-demo.json':json.dumps(workflow,indent=2)+'\n', N8N/'sql/quiz-demo-upsert.sql':'-- Generated by n8n/build/quiz_demo.py; explicit demonstration only.\n'+sql+';\n'}
    for path,text in outputs.items():
        if args.check:
            if not path.exists() or path.read_text()!=text:
                raise SystemExit('Stale generated quiz demo: '+str(path))
        else:path.write_text(text)
    if args.test:
        args.test.write_text(json.dumps(generate('testPostgres01')[0],indent=2)+'\n')
    print('Quiz demo matches sources.' if args.check else 'Generated quiz demo workflow and SQL.')


if __name__=='__main__':main()
