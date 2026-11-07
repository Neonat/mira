"""One disposable local workspace/run. Never runs a general worker or live provider.
setup creates workspace membership and seeds ONLY that new workspace;
plan/finish are bounded to the metadata run created through the actual brief UI.
"""
import sys,json,uuid,importlib.util,time
from pathlib import Path
from psycopg.types.json import Jsonb
sys.path.insert(0,str(Path.cwd()))
from mira.db import connect
from mira.seed import seed
from mira.pg_store import load_run,PostgresStore
from mira.llm import ScriptedClient
from mira.fetch import Fetcher,AllowList
from mira.agents.verifier import LlmVerifier
from mira.orchestrator import Orchestrator
OUT=Path('reports/demo-output/launch');META=OUT/'fixture.json';DSN='postgres://postgres:postgres@127.0.0.1:55432/postgres'
spec=importlib.util.spec_from_file_location('fixture_helpers','tests/test_pipeline_db.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
mode=sys.argv[1]
with connect(DSN) as conn:
 if mode=='setup':
  assert not META.exists(),'Existing metadata: do not create another workspace'
  old=json.loads(Path('reports/demo-output/authenticated/fixture.json').read_text());uid=uuid.UUID(old['user_id'])
  slug='launch-'+uuid.uuid4().hex[:10]
  ws=conn.execute("insert into public.workspaces(slug,name) values(%s,%s) returning id",(slug,'Synthetic launch workflow')).fetchone()['id']
  conn.execute("insert into public.workspace_members(workspace_id,user_id,role) values(%s,%s,'admin')",(ws,uid));seed(conn,ws)
  data={'workspace_id':str(ws),'workspace_slug':slug,'user_id':str(uid),'provider':'ScriptedClient/FakeWeb only; local synthetic content'};META.write_text(json.dumps(data,indent=2));print(json.dumps({'workspace_slug':slug,'status':'new workspace only'}));sys.exit()
 data=json.loads(META.read_text());ws=uuid.UUID(data['workspace_id'])
 runs=conn.execute('select id,status from public.analysis_runs where workspace_id=%s',(ws,)).fetchall()
 assert len(runs)==1,'Exactly one UI-created fixture run required'
 rid=runs[0]['id'];assert str(rid)==data.get('run_id',str(rid));data['run_id']=str(rid);META.write_text(json.dumps(data,indent=2))
 if mode=='plan':
  assert runs[0]['status']=='queued'
  conn.execute("update public.analysis_runs set retrieval_settings=retrieval_settings || %s where id=%s and workspace_id=%s",(Jsonb({'plan_requires_approval':True}),rid,ws))
  conn.commit()
 ctx=load_run(conn,rid)
 if mode=='finish':assert ctx.plan_approved,'Real UI must approve latest plan first'
 def delayed(fn):
  def inner(prompt):time.sleep(1);return fn(prompt)
  return inner
 client=ScriptedClient({'planner':[h.planner_for('HK')],'regulatory_scout':[delayed(h.scout),delayed(h.scout)],'industry_scout':[delayed(h.scout),delayed(h.scout)],'analyst':[delayed(h.analyst)],'verifier':[{'verdict':'supported','reason':'Synthetic fixture passage supports the example.'},{'introduces_new_fact':False,'new_facts':[],'is_supported_assessment':True,'reason':'Synthetic grounded assessment.'}],'writer':[h.writer]})
 store=PostgresStore(conn,reports_dir=Path('reports'))
 fetch=Fetcher(AllowList(store.list_sources(ws)),transport=h.FakeWeb(),resolver=lambda host:['93.184.216.34'],sleep=lambda s:None)
 result=Orchestrator(store,client,{'regulatory_scout':h.WebScout(DSN,client,fetch),'industry_scout':h.WebScout(DSN,client,fetch)},LlmVerifier(client)).run(ctx)
 data['status']=result.status;META.write_text(json.dumps(data,indent=2));print(json.dumps({'run_id':str(rid),'status':result.status,'provider':data['provider']}))
