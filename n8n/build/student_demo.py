#!/usr/bin/env python3
"""Build one inactive manual student-tracker demo from the shared cohort and existing mappers."""
import argparse,json,re
from pathlib import Path
import yaml
import build as shared
ROOT=Path(__file__).resolve().parents[2]
N8N=ROOT/'n8n'


def inputs():
    fixtures=N8N/'tests/fixtures'
    read=lambda name:json.loads((fixtures/name).read_text())
    cohort=read('demo/cohort.json')
    original=(read('me.json').get('data') or read('me.json'))['id']
    def synthetic(value):
        if isinstance(value,dict):return {k:synthetic(v) for k,v in value.items()}
        if isinstance(value,list):return [synthetic(v) for v in value]
        if value==original:return cohort['students'][0]['student_id']
        if isinstance(value,str) and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',value):return 'DEMO-'+value
        return value
    sources={name:[synthetic(read(file))] for name,file in dict(me='me.json',whoop='whoop_status.json',timeBudget='time_budget.json',focus='focus_today.json',todos='todos.json',sessions='sessions.json',syllabus='syllabus_history.json',annual='annual_goals.json',quarterly='quarterly_goals.json').items()}
    sources['wellness']=[{'success':True,'data':{'history':[]}}]  # the poll's wellness read is not used here: wearable_daily comes from the wellness demo mapper below
    signin=read('signin.json');sources['signin']=[{'success':True,'data':{'user':synthetic(signin['data']['user'])}}]
    return dict(demo=True,cohort=cohort,base=dict(runAt=cohort['asOf'],sources=sources),**{key:read('demo/'+name+'-input.json') for key,name in [('chapters','chapter'),('quizzes','quiz'),('wellness','wellness'),('feedback','feedback')]})


def generate(credential=None):
    cfg=yaml.safe_load((ROOT/'student-tracker/config.yaml').read_text())
    specs=shared.parse_tables(shared.SCHEMA.read_text())
    shared.KEEP['chapter_progress']={'updated_at':'CASE WHEN chapter_progress.stage_reached IS DISTINCT FROM EXCLUDED.stage_reached THEN EXCLUDED.updated_at ELSE chapter_progress.updated_at END'}
    shared.KEEP['wearable_daily']={field:f'CASE WHEN wearable_daily.data_source=EXCLUDED.data_source THEN COALESCE(EXCLUDED.{field},wearable_daily.{field}) ELSE EXCLUDED.{field} END' for field in ('strain','recovery_pct','sleep_hours')}
    shared.KEEP['quiz_attempts']={field:f'COALESCE(EXCLUDED.{field},quiz_attempts.{field})' for field in ('completed_at','score','total_questions')}
    if cfg['quiz_loader']['preserve_final_status']:
        shared.KEEP['events']={'status':"CASE WHEN events.kind='quiz' AND events.status IN ('held','cancelled') AND EXCLUDED.status='planned' THEN events.status ELSE EXCLUDED.status END"}
    writes=[]
    for table,spec in specs.items():
        if table=='ingest_log':continue
        statement=shared.upsert_sql(table,spec)
        guard=None
        if table=='chapter_progress':guard='EXCLUDED.updated_at >= chapter_progress.updated_at'
        if table=='quiz_attempts':guard='quiz_attempts.started_at=EXCLUDED.started_at AND (quiz_attempts.completed_at IS NULL OR (quiz_attempts.completed_at=EXCLUDED.completed_at AND quiz_attempts.score IS NOT DISTINCT FROM EXCLUDED.score))'
        if table=='feedback':
            guard=' AND '.join('feedback.'+c+' IS NOT DISTINCT FROM EXCLUDED.'+c for c in spec['columns'] if c!='feedback_id')
            statement=statement.replace('$1::json)\n',"$1::json) incoming\n  WHERE NOT EXISTS (SELECT 1 FROM feedback old WHERE old.feedback_id<>incoming.feedback_id AND old.student_id=incoming.student_id AND ((incoming.event_id IS NOT NULL AND old.event_id=incoming.event_id) OR (incoming.event_id IS NULL AND old.event_id IS NULL AND old.kind=incoming.kind AND date_trunc('month',old.submitted_at)=date_trunc('month',incoming.submitted_at))))\n")
        if table=='wearable_daily':
            priority=cfg['wellness_loader']['source_priority']
            if set(priority)!={'whoop','manual'} or len(priority)!=2:raise ValueError('invalid source priority')
            rank=lambda ref:'CASE '+ref+' '+ ' '.join("WHEN '"+value+"' THEN "+str(i) for i,value in enumerate(priority))+' ELSE 2 END'
            guard=rank('EXCLUDED.data_source')+' <= '+rank('wearable_daily.data_source')
        if guard:statement=statement.replace('\n  RETURNING 1','\n  WHERE '+guard+'\n  RETURNING 1')
        inner=statement.split('WITH up AS (',1)[1].split(')\nSELECT count(*)',1)[0]
        inner=inner.replace('$1::json',"($1::json->'tables'->'"+table+"')")
        writes.append(table+'_write AS ('+inner+')')
    sql='WITH '+',\n'.join(writes)+'\nSELECT '+', '.join('(SELECT count(*)::int FROM '+table+'_write) AS '+table for table in specs if table!='ingest_log')
    source='\n'.join((N8N/'code'/name).read_text() for name in ['normalise.js','chapters.js','quizzes.js','wellness.js','feedback.js','student-demo.js'])
    code=source+'\nconst mapped=mapStudentDemo($("Demo inputs").first().json.evidence,'+json.dumps(cfg)+',{normalise,mapChapters,mapQuizzes,mapWellness,mapFeedback,toIst,istDate});\nreturn [{json:{...mapped,sql:'+json.dumps(sql)+'}}];'
    creds={'postgres':{'id':credential,'name':'Student tracker DEMO Postgres'}} if credential else {}
    nodes=[shared.node('Run cohort demo','n8n-nodes-base.manualTrigger',1,{},(0,0)),
      shared.node('Demo inputs','n8n-nodes-base.set',3.4,{'assignments':{'assignments':[{'id':shared.uid('cohort-evidence'),'name':'evidence','value':inputs(),'type':'object'}]},'options':{}},(260,0)),
      shared.node('Map shared cohort','n8n-nodes-base.code',2,{'mode':'runOnceForAllItems','language':'javaScript','jsCode':code},(520,0)),
      shared.node('Write cohort atomically','n8n-nodes-base.postgres',2.6,{'operation':'executeQuery','query':'={{ $json.sql }}','options':{'queryReplacement':'={{ JSON.stringify({tables:$json.tables}) }}'}},(780,0),credentials=creds,retryOnFail=True,maxTries=3,waitBetweenTries=2000),
      shared.node('Demo summary','n8n-nodes-base.code',2,{'mode':'runOnceForAllItems','language':'javaScript','jsCode':'const saved=$input.first().json; const expected=$("Map shared cohort").first().json.counts; const skipped=Object.entries(saved).reduce((n,[key,value])=>n+expected[key]-Number(value),0); return [{json:{demo:true,status:skipped ? "partial" : "ok",skippedWrites:skipped,written:saved,notice:"Synthetic cohort; no live ingestion freshness claimed"}}];'},(1040,0)),
      shared.node('About the cohort demo','n8n-nodes-base.stickyNote',1,{'width':1000,'height':230,'content':'## Integrated student-tracker DEMO\n\nManual synthetic input only. Reuses the app, chapter, quiz, wellness and submitted-feedback mappers with one shared roster. Advisor duties and exam targets are explicit manual samples, not a ClickUp integration. All data tables write atomically; partial bundles stop. No live freshness success is created. Export a validated snapshot with student-tracker/snapshot.py, then refresh the dashboard. No Alcovia API or messages are sent.'},(0,-270))]
    workflow=dict(id='studentTrackerCohortDemo01',name='Student tracker integrated DEMO',active=False,nodes=nodes,connections=shared.chain('Run cohort demo','Demo inputs','Map shared cohort','Write cohort atomically','Demo summary'),settings=dict(executionOrder='v1',timezone='Asia/Kolkata',saveDataSuccessExecution='none',saveDataErrorExecution='none',saveManualExecutions=False,executionTimeout=120))
    return workflow,sql


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');parser.add_argument('--test',type=Path);args=parser.parse_args()
    workflow,sql=generate()
    for path,value in {N8N/'student-tracker-demo.json':json.dumps(workflow,indent=2)+'\n',N8N/'sql/student-demo-upsert.sql':'-- Generated synthetic cohort statement.\n'+sql+';\n'}.items():
        if args.check:
            if not path.exists() or path.read_text()!=value:raise SystemExit('Stale integrated demo: '+str(path))
        else:path.write_text(value)
    if args.test:args.test.write_text(json.dumps(generate('testPostgres01')[0],indent=2)+'\n')
    print('Integrated demo matches sources.' if args.check else 'Generated integrated student demo.')


if __name__=='__main__':main()
