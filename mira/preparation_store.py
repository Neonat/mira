"""Trusted-worker storage for atomic scheduled evidence and immutable reports.

Public clients use the five authenticated SQL RPCs, never this connection.
"""
from __future__ import annotations
import hashlib
from html import escape
from urllib.parse import urlsplit
import json
from uuid import UUID
from psycopg.types.json import Jsonb
from mira.contracts import Brief
from mira.db import acting_as, require_role, NotAuthorisedError


def _json(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return json.loads(json.dumps(value, default=str))


class PreparationStore:
    def __init__(self, conn):
        self.conn = conn

    def _sources(self, ws, sources):
        ids = sorted(set(UUID(str(x)) for x in sources), key=str)
        if not self.conn.execute('select private.prepared_sources_allowed(%s,%s::uuid[]) as ok', (ws, ids)).fetchone()['ok']:
            raise ValueError('source scope is not permitted')
        return ids

    def _scopes(self, ws, ids):
        for sid in sorted(ids, key=str):
            self.conn.execute('insert into public.preparation_scopes(id,workspace_id,source_id) values(%s,%s,%s) on conflict do nothing', (sid,ws,sid))
        return self.conn.execute('select * from public.preparation_scopes where workspace_id=%s and id=any(%s::uuid[]) order by id for update', (ws,ids)).fetchall()

    def enqueue_job(self, ws, actor, source_ids, brief, budget, models, settings, idempotency_key):
        with acting_as(self.conn,actor):
            require_role(self.conn,ws)
            ids=self._sources(ws,source_ids)
            scopes=self._scopes(ws,ids)
            job=self.conn.execute('''insert into public.preparation_jobs(workspace_id,actor_id,source_ids,brief,budget,models,settings,idempotency_key)
                values(%s,%s,%s,%s,%s,%s,%s,%s) on conflict(workspace_id,idempotency_key) do nothing returning *''',
                (ws,actor,ids,Jsonb(_json(brief)),Jsonb(_json(budget)),Jsonb(_json(models)),Jsonb(_json(settings)),idempotency_key)).fetchone()
            if job is None:
                return self.conn.execute('select * from public.preparation_jobs where workspace_id=%s and idempotency_key=%s',(ws,idempotency_key)).fetchone()
            # Registration is visible to requests before the worker starts.
            if all(s['active_job_id'] is None for s in scopes):
                self.conn.execute('update public.preparation_scopes set active_job_id=%s where workspace_id=%s and id=any(%s)',(job['id'],ws,ids))
            return job

    def _admission_error(self, ws, source_ids):
        allowed=self.conn.execute("select private.has_workspace_role(%s,array['admin','analyst']) as ok",(ws,)).fetchone()['ok']
        if not allowed:
            return 'Preparation authorization revoked: actor lacks workspace run role'
        if not self.conn.execute('select private.prepared_sources_allowed(%s,%s::uuid[]) as ok',(ws,source_ids)).fetchone()['ok']:
            return 'Preparation authorization revoked: source scope is not permitted'
        return None

    def claim_job(self, ws, owner, lease_seconds=120):
        if lease_seconds<=0: raise ValueError('positive lease required')
        with self.conn.transaction():
            self.conn.execute('select 1 from public.preparation_scopes where workspace_id=%s order by id for update',(ws,)).fetchall()
            # Scope locks always precede job locks. Scan candidates without locking;
            # re-read their status after scopes serialize competitors.
            candidates=self.conn.execute("select * from public.preparation_jobs where workspace_id=%s and (status='queued' or (status='preparing' and lease_until<=clock_timestamp())) order by created_at,id",(ws,)).fetchall()
            for candidate in candidates:
                scopes=self._scopes(ws,candidate['source_ids'])
                if any(s['active_job_id'] not in (None,candidate['id']) for s in scopes): continue
                with acting_as(self.conn,candidate['actor_id']):
                    error=self._admission_error(ws,candidate['source_ids'])
                    if error:
                        failed=self.conn.execute("update public.preparation_jobs set status='failed',phase='failed',reason=%s,finished_at=clock_timestamp(),lease_until=null where id=%s and (status='queued' or (status='preparing' and lease_until<=clock_timestamp())) returning id",(error,candidate['id'])).fetchone()
                        if failed:
                            self.conn.execute('update public.preparation_scopes set latest_failed_job_id=%s where workspace_id=%s and id=any(%s)',(candidate['id'],ws,candidate['source_ids']))
                            self._advance(ws,candidate['source_ids'])
                        continue
                    row=self.conn.execute("""update public.preparation_jobs set status='preparing',owner=%s,generation=generation+1,lease_until=clock_timestamp()+%s*interval '1 second',phase='starting'
                      where id=%s and (status='queued' or (status='preparing' and lease_until<=clock_timestamp())) returning *""",(owner,lease_seconds,candidate['id'])).fetchone()
                    if row:
                        self.conn.execute('update public.preparation_scopes set active_job_id=%s where workspace_id=%s and id=any(%s)',(row['id'],ws,row['source_ids']))
                        return row
        return None

    def _fence(self, job):
        row=self.conn.execute("""select * from public.preparation_jobs where id=%s and workspace_id=%s and owner=%s and generation=%s and status='preparing' and lease_until>clock_timestamp() for update""",(job['id'],job['workspace_id'],job['owner'],job['generation'])).fetchone()
        if not row: raise ValueError('preparation lease lost')
        return row

    def heartbeat_job(self, job, phase):
        with acting_as(self.conn,job['actor_id']):
            self._fence(job)
            return self.conn.execute("update public.preparation_jobs set phase=coalesce(%s,phase),lease_until=clock_timestamp()+interval '120 seconds' where id=%s returning *",(phase,job['id'])).fetchone()

    def set_job_run(self, job, run_id):
        with acting_as(self.conn,job['actor_id']):
            self._fence(job)
            if not self.conn.execute('select 1 from public.analysis_runs where id=%s and workspace_id=%s',(run_id,job['workspace_id'])).fetchone(): raise ValueError('run scope mismatch')
            return self.conn.execute('update public.preparation_jobs set analysis_run_id=%s where id=%s returning *',(run_id,job['id'])).fetchone()

    def _advance(self, ws, source_ids):
        self.conn.execute('update public.preparation_scopes set active_job_id=null where workspace_id=%s and id=any(%s)',(ws,source_ids))
        # Promote only whole jobs. Lock all scopes in workspace first at callers
        # where overlaps may include scopes outside the finishing job.
        queued=self.conn.execute("select * from public.preparation_jobs where workspace_id=%s and status='queued' order by created_at,id",(ws,)).fetchall()
        for q in queued:
            scopes=self._scopes(ws,q['source_ids'])
            if all(s['active_job_id'] is None for s in scopes):
                self.conn.execute('update public.preparation_scopes set active_job_id=%s where workspace_id=%s and id=any(%s)',(q['id'],ws,q['source_ids']))

    def _publication_scopes(self, job):
        # Short publication lock only; no network/model operation holds this.
        self.conn.execute('select 1 from public.preparation_scopes where workspace_id=%s order by id for update',(job['workspace_id'],)).fetchall()

    def _validate_payload(self, job, payload):
        p=_json(payload)
        if p.get('schema_version')!=1: raise ValueError('unsupported prepared snapshot schema')
        if set(map(str,p.get('source_ids',[])))!=set(map(str,job['source_ids'])): raise ValueError('snapshot source scope mismatch')
        e=p['evidence_input']
        if str(e['workspace_id'])!=str(job['workspace_id']) or str(e['analysis_run_id'])!=str(job['analysis_run_id']): raise ValueError('snapshot run scope mismatch')
        ids=[UUID(x) for x in e['findings']]
        actual=self.conn.execute('select private.capture_evidence_input(%s,%s,%s,%s::uuid[]) as input',(job['workspace_id'],job['analysis_run_id'],UUID(e['analysis_revision_id']),ids)).fetchone()['input']
        if actual!=e: raise ValueError('snapshot evidence differs from original input')
        self._sources(job['workspace_id'],job['source_ids'])
        if any(str(v['source_id']) not in set(map(str,job['source_ids'])) for v in e['passages'].values()): raise ValueError('passage outside snapshot sources')
        for fid,fact in e['findings'].items():
            if any(str(d) not in e['findings'] for d in fact['depends_on']): raise ValueError('missing dependency')
            subset=self.conn.execute('select private.evidence_input_subset(%s,%s::uuid[]) as input',(Jsonb(e),[UUID(fid)])).fetchone()['input']
            check=self.conn.execute('select * from public.claim_checks where workspace_id=%s and analysis_run_id=%s and finding_id=%s order by checked_at desc,attempt desc,id desc limit 1',(job['workspace_id'],job['analysis_run_id'],UUID(fid))).fetchone()
            frozen=p['verifications'].get(fid)
            if not check or check['verdict']!='supported' or check['input_snapshot']!=subset or not check['model'] or check['method']!=('inference_check' if fact['is_inference'] else 'llm'):
                raise ValueError('fact lacks current original machine support')
            if not frozen or str(frozen['check_id'])!=str(check['id']) or frozen['input_fingerprint']!=check['input_fingerprint']:
                raise ValueError('verification provenance mismatch')
            if frozen.get('input_snapshot',subset)!=subset: raise ValueError('verification input mismatch')
            canonical={k:_json(check[k]) for k in ('method','verdict','reason','model','prompt_version','checked_at','attempt','agent_step_id')}
            canonical['check_id']=str(check['id']); canonical['input_fingerprint']=check['input_fingerprint']; canonical['input_snapshot']=subset
            for key,value in canonical.items():
                if key in frozen and frozen[key]!=value:
                    if key=='checked_at':
                        from datetime import datetime
                        if datetime.fromisoformat(frozen[key].replace('Z','+00:00'))==check[key]: continue
                    raise ValueError('verification metadata mismatch')
            p['verifications'][fid]=canonical
        return p

    def publish_job(self, job, payload):
        with acting_as(self.conn,job['actor_id']):
            self._publication_scopes(job)
            existing=self.conn.execute('select * from public.prepared_snapshots where job_id=%s',(job['id'],)).fetchone()
            if existing:
                retry=_json(payload)
                for fid,v in retry['verifications'].items():
                    for key,value in existing['payload']['verifications'].get(fid,{}).items():
                        if key not in v: v[key]=value
                        elif key=='checked_at':
                            from datetime import datetime
                            if datetime.fromisoformat(v[key].replace('Z','+00:00'))==datetime.fromisoformat(value.replace('Z','+00:00')): v[key]=value
                if existing['generation']!=job['generation'] or existing['payload']!=retry: raise ValueError('publication identity mismatch')
                return existing
            current=self._fence(job)
            p=self._validate_payload(current,payload)
            self._fence(job)
            row=self.conn.execute('''insert into public.prepared_snapshots(workspace_id,job_id,generation,source_ids,payload,input_fingerprint,known_version_ids)
                values(%s,%s,%s,%s,%s,private.evidence_input_fingerprint(%s),
                  array(select v.id from public.document_versions v join public.documents d on d.id=v.document_id and d.workspace_id=v.workspace_id
                    where v.workspace_id=%s and d.source_id=any(%s) order by v.id)) returning *''',
                (job['workspace_id'],job['id'],job['generation'],job['source_ids'],Jsonb(p),Jsonb(p),job['workspace_id'],job['source_ids'])).fetchone()
            self.conn.execute('''insert into public.prepared_snapshot_parents(snapshot_id,parent_snapshot_id,workspace_id,source_ids)
                select %s,latest_snapshot_id,workspace_id,array_agg(source_id order by source_id)
                from public.preparation_scopes where workspace_id=%s and id=any(%s) and latest_snapshot_id is not null
                group by latest_snapshot_id,workspace_id''',(row['id'],job['workspace_id'],job['source_ids']))
            for fid,fact in p['evidence_input']['findings'].items():
                self.conn.execute('insert into public.prepared_facts(workspace_id,snapshot_id,finding_id,fact,input_fingerprint) values(%s,%s,%s,%s,%s)',(job['workspace_id'],row['id'],UUID(fid),Jsonb(fact),p['verifications'][fid]['input_fingerprint']))
            self.conn.execute('update public.preparation_scopes set latest_snapshot_id=%s,latest_failed_job_id=null where workspace_id=%s and id=any(%s)',(row['id'],job['workspace_id'],job['source_ids']))
            self.conn.execute("update public.preparation_jobs set status='succeeded',phase='ready',finished_at=clock_timestamp(),lease_until=null where id=%s",(job['id'],))
            self._advance(job['workspace_id'],job['source_ids'])
            return row

    def fail_job(self, job, reason):
        with acting_as(self.conn,job['actor_id']):
            self._publication_scopes(job)
            self._fence(job)
            self.conn.execute("update public.preparation_jobs set status='failed',phase='failed',reason=%s,finished_at=clock_timestamp(),lease_until=null where id=%s",(reason,job['id']))
            self.conn.execute('update public.preparation_scopes set latest_failed_job_id=%s where workspace_id=%s and id=any(%s)',(job['id'],job['workspace_id'],job['source_ids']))
            self._advance(job['workspace_id'],job['source_ids'])

    def request_report(self, ws, actor, brief, source_ids, key):
        with acting_as(self.conn,actor):
            rid=self.conn.execute('select public.request_prepared_report(%s,%s,%s::uuid[],%s) as id',(ws,Jsonb(_json(brief)),source_ids,key)).fetchone()['id']
            return self.conn.execute('select * from public.prepared_report_requests where id=%s',(rid,)).fetchone()

    def resolve_request(self, request_id):
        with self.conn.transaction():
            r=self.conn.execute('select * from public.prepared_report_requests where id=%s for update',(request_id,)).fetchone()
            if not r or r['status'] not in ('queued','waiting','evidence_failed'): return r
            entries=self.conn.execute('select * from public.prepared_report_request_scopes where request_id=%s order by scope_id',(request_id,)).fetchall()
            state='queued'
            for e in entries:
                if e['snapshot_id']: continue
                if not e['job_id']:
                    state='evidence_failed'; continue
                j=self.conn.execute('select status from public.preparation_jobs where id=%s',(e['job_id'],)).fetchone()
                if j['status']=='succeeded':
                    snap=self.conn.execute('select id from public.prepared_snapshots where job_id=%s',(e['job_id'],)).fetchone()
                    if not snap: raise ValueError('completed preparation lacks snapshot')
                    self.conn.execute('update public.prepared_report_request_scopes set snapshot_id=%s where request_id=%s and scope_id=%s',(snap['id'],request_id,e['scope_id']))
                elif j['status'] in ('failed','cancelled'): state='evidence_failed'
                elif state!='evidence_failed': state='waiting'
            return self.conn.execute('update public.prepared_report_requests set status=%s where id=%s returning *',(state,request_id)).fetchone()

    def claim_report_request(self, ws, owner, lease_seconds=120, request_id=None):
        for r in self.conn.execute("select id from public.prepared_report_requests where workspace_id=%s and status in ('queued','waiting','evidence_failed') order by created_at",(ws,)).fetchall(): self.resolve_request(r['id'])
        with self.conn.transaction():
            r=self.conn.execute("select * from public.prepared_report_requests where workspace_id=%s and (%s::uuid is null or id=%s::uuid) and (status='queued' or (status='generating' and lease_until<=clock_timestamp())) order by created_at for update skip locked limit 1",(ws,request_id,request_id)).fetchone()
            if not r: return None
            return self.conn.execute("update public.prepared_report_requests set status='generating',owner=%s,generation=generation+1,lease_until=clock_timestamp()+%s*interval '1 second',generation_started_at=coalesce(generation_started_at,clock_timestamp()) where id=%s returning *",(owner,lease_seconds,r['id'])).fetchone()

    def load_request_snapshots(self, request_id):
        """Load only fixed manifest lineage; later cycles never enter these roots.

        Admission follows individual source edges. Supersession is evaluated at
        each root's publication cutoff, never against a future latest version.
        More than 4096 source/root/snapshot routes fails closed, not truncated.
        """
        request=self.conn.execute('select * from public.prepared_report_requests where id=%s',(request_id,)).fetchone()
        if not request: return []
        rows=self.conn.execute("""with recursive lineage(root_id,snapshot_id,source_id) as (
          select snapshot_id,snapshot_id,scope_id from public.prepared_report_request_scopes
          where request_id=%s and snapshot_id is not null
          union
          select l.root_id,p.parent_snapshot_id,l.source_id from lineage l
          join public.prepared_snapshot_parents p on p.snapshot_id=l.snapshot_id
          and p.workspace_id=%s and l.source_id=any(p.source_ids)
        ) select s.*,l.root_id,l.source_id as admitted_source_id,r.published_at as root_cutoff,r.known_version_ids as root_known_version_ids
          from lineage l join public.prepared_snapshots s on s.id=l.snapshot_id and s.workspace_id=%s
          join public.prepared_snapshots r on r.id=l.root_id
          order by s.id,l.root_id,l.source_id limit 4097""",(request_id,request['workspace_id'],request['workspace_id'])).fetchall()
        if len(rows)>4096: raise ValueError('prepared lineage exceeds 4096 routes; no partial evidence loaded')
        snapshots={}; routes={}
        for row in rows:
            sid=row['id']; root=row.pop('root_id'); source=row.pop('admitted_source_id'); cutoff=row.pop('root_cutoff'); known_versions=row.pop('root_known_version_ids')
            if sid not in snapshots:
                snapshots[sid]={**row,'admitted_source_ids':[],'root_snapshot_ids':[],
                    'publication_cutoffs':{},'excluded_finding_ids':[]}
                routes[sid]={}
            target=snapshots[sid]
            if source not in target['admitted_source_ids']: target['admitted_source_ids'].append(source)
            if root not in target['root_snapshot_ids']: target['root_snapshot_ids'].append(root)
            target['publication_cutoffs'][str(root)]=cutoff.isoformat()
            routes[sid].setdefault(str(source),[]).append((cutoff,known_versions))
        asof=request['brief'].get('as_of_date')
        for sid,snapshot in snapshots.items():
            for fid,verification in snapshot['payload']['verifications'].items():
                if not self.conn.execute('select private.prepared_fact_supported(%s,%s) as ok',(sid,UUID(fid))).fetchone()['ok']:
                    snapshot['excluded_finding_ids'].append(UUID(fid)); continue
                evidence=verification['input_snapshot']
                for passage in evidence['passages'].values():
                    cutoffs=routes[sid].get(str(passage['source_id']),[])
                    # Any admitted root for this source may retain this exact
                    # version; multiple scopes legitimately have different dates.
                    valid=False
                    for cutoff,known_versions in cutoffs:
                        result=self.conn.execute("""select not exists(
                          select 1 from public.document_versions newer
                          where newer.workspace_id=old.workspace_id and newer.document_id=old.document_id
                          and newer.version_number>old.version_number and newer.retrieved_at<=%s and newer.id=any(%s::uuid[])
                          and (newer.published_at is null or newer.published_at::date<=%s::date)) as current
                          from public.document_versions old where old.id=%s and old.workspace_id=%s and old.id=any(%s::uuid[])""",
                          (cutoff,known_versions,asof,UUID(passage['document_version_id']),request['workspace_id'],known_versions)).fetchone()
                        if result and result['current']: valid=True; break
                    if not valid:
                        snapshot['excluded_finding_ids'].append(UUID(fid)); break
        return sorted(snapshots.values(),key=lambda row:(row['published_at'],str(row['id'])),reverse=True)

    @staticmethod
    def _dependency_binding_matches(snapshots, keys, referring_snapshot, dependency_id):
        """An alias must preserve both frozen fact bytes and its checked closure."""
        expected=snapshots[referring_snapshot]['payload']
        fid=str(dependency_id)
        for sid,candidate_id in keys:
            if candidate_id!=dependency_id or sid not in snapshots: continue
            actual=snapshots[sid]['payload']
            if (actual['evidence_input']['findings'].get(fid)==expected['evidence_input']['findings'].get(fid)
                and actual['verifications'].get(fid,{}).get('input_fingerprint') is not None
                and actual['verifications'][fid]['input_fingerprint']==expected['verifications'].get(fid,{}).get('input_fingerprint')):
                return True
        return False

    def _report_fence(self, request):
        r=self.conn.execute("select * from public.prepared_report_requests where id=%s and workspace_id=%s and owner=%s and generation=%s and status='generating' and lease_until>clock_timestamp() for update",(request['id'],request['workspace_id'],request['owner'],request['generation'])).fetchone()
        if not r: raise ValueError('report request lease lost')
        return r

    def publish_report(self, request, capture, html, bindings):
        with acting_as(self.conn,request['actor_id']):
            r=self._report_fence(request)
            require_role(self.conn,r['workspace_id'])
            self._sources(r['workspace_id'],r['source_ids'])
            pinned={s['id']:s for s in self.load_request_snapshots(r['id'])}
            keys=sorted(set((UUID(str(b['snapshot_id'])),UUID(str(b['finding_id']))) for b in bindings),key=lambda x:(str(x[0]),str(x[1])))
            reviews=[]
            c=_json(capture)
            captured_keys={(str(b['snapshot_id']),str(b['finding_id'])) for b in c.get('bindings',[])}
            if captured_keys!={(str(s),str(f)) for s,f in keys}: raise ValueError('capture bindings mismatch')
            if set(c.get('selected_findings',{}))!={str(f) for _,f in keys}: raise ValueError('capture selected findings mismatch')
            for sid,fid in keys:
                if sid not in pinned: raise ValueError('report binding is not pinned')
                if fid in pinned[sid]['excluded_finding_ids']: raise ValueError('prepared fact superseded, outside admitted source lineage, or lacks current machine support')
                f=self.conn.execute('select * from public.prepared_facts where snapshot_id=%s and finding_id=%s and workspace_id=%s for update',(sid,fid,r['workspace_id'])).fetchone()
                if not f: raise ValueError('missing prepared fact')
                if c['selected_findings'][str(fid)]!=f['fact']: raise ValueError('capture fact differs from frozen evidence')
                if not self.conn.execute('select private.prepared_fact_supported(%s,%s) as ok',(sid,fid)).fetchone()['ok']: raise ValueError('prepared fact lacks current machine support')
                if any(not self._dependency_binding_matches(pinned,keys,sid,UUID(str(d))) for d in f['fact']['depends_on']): raise ValueError('missing report dependency with identical frozen fact and verification input')
                v=self.conn.execute('select * from public.prepared_fact_reviews where snapshot_id=%s and finding_id=%s order by sequence desc limit 1',(sid,fid)).fetchone()
                if v and v['decision']!='accepted': raise ValueError('prepared fact rejected or correction requested')
                reviews.append({'snapshot_id':str(sid),'finding_id':str(fid),'review_id':str(v['id']) if v else None,'review_sequence':v['sequence'] if v else None,'decision':v['decision'] if v else None})
            state='human_checked' if keys and all(v['decision']=='accepted' for v in reviews) else 'human_review_pending'
            c['evidence_review_state']=state; c['prepared_bindings']=reviews
            warning='Human evidence checked. Final report approval is separate.' if state=='human_checked' else 'Draft — human evidence review pending. This report is not signed off.'
            if '{{PREPARED_REVIEW_WARNING}}' not in html: raise ValueError('report review warning placeholder required')
            html=html.replace('{{PREPARED_REVIEW_WARNING}}',warning,1)
            c['prepared_review_counts']={'accepted':sum(v['decision']=='accepted' for v in reviews),'pending':sum(v['decision'] is None for v in reviews)}
            c['preparation_dispositions']=[{'snapshot_id':str(sid),'analysis_coverage':snap['payload'].get('analysis_coverage'),'reasons':snap['payload'].get('reasons',[])} for sid,snap in pinned.items()]
            html=html.replace('{{PREPARED_FACT_REVIEWS}}',self._fact_review_html(reviews,pinned),1)
            if warning not in html: raise ValueError('report review warning placeholder required')
            sha=hashlib.sha256(html.encode()).hexdigest()
            row=self.conn.execute('insert into public.prepared_reports(workspace_id,request_id,capture,html,content_sha256,review_state) values(%s,%s,%s,%s,%s,%s) returning *',(r['workspace_id'],r['id'],Jsonb(c),html,sha,state)).fetchone()
            for v in reviews:
                self.conn.execute('insert into public.prepared_report_bindings(report_id,workspace_id,snapshot_id,finding_id,review_id,review_sequence,decision) values(%s,%s,%s,%s,%s,%s,%s)',(row['id'],r['workspace_id'],UUID(v['snapshot_id']),UUID(v['finding_id']),UUID(v['review_id']) if v['review_id'] else None,v['review_sequence'],v['decision']))
            self.conn.execute("update public.prepared_report_requests set status='ready',finished_at=clock_timestamp(),lease_until=null where id=%s",(r['id'],))
            return row

    @staticmethod
    def _fact_review_html(reviews, snapshots):
        rows=[]
        for review in reviews:
            sid=UUID(review['snapshot_id']); fid=review['finding_id']
            evidence=snapshots[sid]['payload']['evidence_input']
            fact=evidence['findings'][fid]
            citations=[]
            for citation in fact.get('evidence',[]):
                passage=evidence['passages'][str(citation['passage_id'])]
                url=passage.get('source_url','')
                title=escape(passage.get('title') or passage.get('source_name') or url)
                if urlsplit(url).scheme.lower() in ('http','https'):
                    title=f'<a href="{escape(url,quote=True)}">{title}</a>'
                quote=escape(citation.get('supporting_quote') or '')
                citations.append(f'<div>{title}<blockquote>{quote}</blockquote></div>')
            state='Accepted' if review['decision']=='accepted' else 'Pending'
            rows.append(f'<tr role="row"><td role="cell" data-label="Snapshot">{escape(str(sid))}</td>'
                        f'<td role="cell">{escape(fact["title"])}</td>'
                        f'<td role="cell" data-label="Human decision">{state}</td>'
                        f'<td role="cell">{"".join(citations)}</td></tr>')
        return ('<section id="prepared-fact-reviews" class="prepared-fact-reviews"><h2>Captured human evidence decisions</h2>'
                '<p>Decisions apply to the included facts and their dependencies. They do not certify publication coverage, '
                'analysis of every retained passage, or final report approval.</p>'
                '<table role="table"><thead><tr><th scope="col">Snapshot</th><th scope="col">Fact</th>'
                '<th scope="col">Human decision</th><th scope="col">Citations and exact quotations</th></tr></thead>'
                '<tbody role="rowgroup">'+''.join(rows)+'</tbody></table>'
                '<p class="back"><a href="#contents">Back to contents</a></p></section>')

    def fail_report_request(self, request, reason):
        with acting_as(self.conn,request['actor_id']):
            self._report_fence(request)
            self.conn.execute("update public.prepared_report_requests set status='failed',reason=%s,finished_at=clock_timestamp() where id=%s",(reason,request['id']))

    def configure_schedule(self, ws, actor, source_ids, brief, budget, models, settings, frequency_seconds, next_due, enabled=False):
        brief = Brief.model_validate(brief)
        if brief.plan_requires_approval:
            raise ValueError('Scheduled preparation requires a pre-approved research plan scope')
        with acting_as(self.conn,actor):
            require_role(self.conn,ws,('admin',))
            ids=self._sources(ws,source_ids)
            return self.conn.execute('insert into public.preparation_schedules(workspace_id,actor_id,source_ids,brief,budget,models,settings,frequency_seconds,next_due,enabled) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id',(ws,actor,ids,Jsonb(_json(brief)),Jsonb(_json(budget)),Jsonb(_json(models)),Jsonb(_json(settings)),frequency_seconds,next_due,enabled)).fetchone()['id']

    def tick_schedules(self, ws):
        n=0
        with self.conn.transaction():
            today = self.conn.execute("select (clock_timestamp() at time zone 'UTC')::date as today").fetchone()['today']
            for s in self.conn.execute('select * from public.preparation_schedules where workspace_id=%s and enabled and next_due<=clock_timestamp() order by id for update skip locked',(ws,)).fetchall():
                with acting_as(self.conn,s['actor_id']):
                    error=self._admission_error(ws,s['source_ids'])
                if error:
                    self.conn.execute('update public.preparation_schedules set enabled=false,error=%s where id=%s',(error,s['id']))
                    continue
                try:
                    template = Brief.model_validate(s['brief'])
                    if template.as_of_date > today:
                        raise ValueError('Scheduled brief as-of date is after the current UTC date')
                    brief = template.model_copy(update={
                        'as_of_date': today,
                        'period_end': template.period_end + (today - template.as_of_date),
                    })
                    self.enqueue_job(ws,s['actor_id'],s['source_ids'],brief,s['budget'],s['models'],s['settings'],f"schedule:{s['id']}:{s['next_due'].isoformat()}")
                except (NotAuthorisedError, ValueError) as exc:
                    # Admission can change between the initial check and enqueue.
                    # Its nested transaction rolls back this job, not other due work.
                    self.conn.execute('update public.preparation_schedules set enabled=false,error=%s where id=%s',(str(exc),s['id']))
                    continue
                # Coalesce missed ticks without shifting the configured cadence.
                self.conn.execute("""update public.preparation_schedules set next_due=next_due
                    +(floor(extract(epoch from clock_timestamp()-next_due)/frequency_seconds)+1)
                    *frequency_seconds*interval '1 second' where id=%s""", (s['id'],))
                n+=1
        return n

    def put_frontier(self, job, source_id, entries):
        with acting_as(self.conn,job['actor_id']):
            self._fence(job)
            if str(source_id) not in set(map(str,job['source_ids'])): raise ValueError('frontier source outside job')
            for entry in entries:
                self.conn.execute('insert into public.preparation_frontier(workspace_id,source_id,url,entry,job_id,generation) values(%s,%s,%s,%s,%s,%s) on conflict do nothing',(job['workspace_id'],source_id,entry['url'],Jsonb(_json(entry)),job['id'],job['generation']))
        return True

    def pending_frontier(self, job, source_ids, limit, start_date=None, as_of_date=None):
        with acting_as(self.conn,job['actor_id']):
            self._fence(job)
            if not set(map(str,source_ids))<=set(map(str,job['source_ids'])): raise ValueError('frontier source outside job')
            rows=self.conn.execute("select * from public.preparation_frontier where workspace_id=%s and source_id=any(%s::uuid[]) and status in ('pending','deferred','failed') and (%s::date is null or nullif(entry->>'published','') is null or (entry->>'published')::date>=%s::date) and (%s::date is null or nullif(entry->>'published','') is null or (entry->>'published')::date<=%s::date) order by (status='pending') desc,discovered_at,url limit %s",(job['workspace_id'],source_ids,start_date,start_date,as_of_date,as_of_date,limit)).fetchall()
            return [{**r['entry'],**{k:v for k,v in r.items() if k!='entry'}} for r in rows]

    def finish_frontier(self, job, source_id, url, status, error=None):
        if status not in ('acquired','failed','deferred'): raise ValueError('invalid frontier disposition')
        with acting_as(self.conn,job['actor_id']):
            self._fence(job)
            if str(source_id) not in set(map(str,job['source_ids'])): raise ValueError('frontier source outside job')
            return self.conn.execute('update public.preparation_frontier set status=%s,error=%s,attempts=attempts+1,job_id=%s,generation=%s,updated_at=clock_timestamp() where workspace_id=%s and source_id=%s and url=%s returning *',(status,error,job['id'],job['generation'],job['workspace_id'],source_id,url)).fetchone()
