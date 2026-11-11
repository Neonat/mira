"""Fresh reports from immutable prepared evidence, with no acquisition/model call.

This path selects and organizes saved supported claims. It never invents factual
wording or transfers a historical model check to a different analysis run.
"""
from __future__ import annotations

from dataclasses import dataclass,field
from datetime import UTC,date,datetime
from dataclasses import asdict
from html import escape
import json,re,time
from uuid import UUID,uuid4

from mira.agents import writer
from mira.agents.temporal import check_claim_period
from mira.contracts import (Brief,ClaimCitation,ClaimDraft,CoverageRow,EvidenceInput,
    FrozenExpectedSource,FrozenVerification,KeyDateKind,ReportSection,ReportSentence,ReportSnapshot)
from mira.db import acting_as,require_role
from mira.evidence_snapshot import build_verification_input
from mira.pg_store import PostgresStore,load_run
from mira.report import ReportContext,render_html
from mira.store import ClaimEvidence,ExpectedSourceRecord,PassageRecord,StoredClaim


def build_prepared_payload(conn,run_id,source_ids):
    """Freeze exact current support from a completed preparation run."""
    ctx=load_run(conn,UUID(str(run_id)))
    row=conn.execute('select status,failure_summary from public.analysis_runs where workspace_id=%s and id=%s',
                     (ctx.workspace_id,ctx.analysis_run_id)).fetchone()
    if row['status'] not in ('draft','partial'):
        raise ValueError('Preparation has not completed successfully')
    with acting_as(conn,ctx.user_id):require_role(conn,ctx.workspace_id)
    findings=conn.execute('select id,is_inference from public.analysis_findings where workspace_id=%s and analysis_run_id=%s',
                         (ctx.workspace_id,ctx.analysis_run_id)).fetchall()
    valid={};verifications={}
    for f in findings:
        c=conn.execute('''select * from public.claim_checks where workspace_id=%s and analysis_run_id=%s
            and finding_id=%s order by checked_at desc,attempt desc,id desc limit 1''',
            (ctx.workspace_id,ctx.analysis_run_id,f['id'])).fetchone()
        if not c or c['verdict']!='supported' or c['method']!=('inference_check' if f['is_inference'] else 'llm'):
            continue
        current=conn.execute('select private.capture_evidence_input(%s,%s,%s,%s::uuid[]) as v',
            (ctx.workspace_id,ctx.analysis_run_id,ctx.analysis_revision_id,[f['id']])).fetchone()['v']
        if current!=c['input_snapshot'] or not c['input_fingerprint'] or not c['model']:
            continue
        if not all(str(p['source_id']) in set(map(str,source_ids)) for p in current['passages'].values()):
            continue
        valid[str(f['id'])]=current
        verifications[str(f['id'])]={**FrozenVerification(check_id=c['id'],method=c['method'],verdict=c['verdict'],
            reason=c['reason'],model=c['model'],prompt_version=c['prompt_version'],checked_at=c['checked_at'],
            input_fingerprint=c['input_fingerprint'],attempt=c['attempt'],agent_step_id=c['agent_step_id']).model_dump(mode='json'),
            'input_snapshot':current}
    # A supported inference cannot rescue an unchecked dependency.
    changed=True
    while changed:
        changed=False
        for fid,e in list(valid.items()):
            if any(d not in valid for d in e['findings'][fid]['depends_on']):
                del valid[fid];verifications.pop(fid,None);changed=True
    evidence=conn.execute('select private.capture_evidence_input(%s,%s,%s,%s::uuid[]) as v',
        (ctx.workspace_id,ctx.analysis_run_id,ctx.analysis_revision_id,[UUID(x) for x in valid])).fetchone()['v']
    coverage=conn.execute('''select distinct on(expected_source_id) * from public.coverage_results
        where workspace_id=%s and analysis_run_id=%s order by expected_source_id,gap_round desc''',
        (ctx.workspace_id,ctx.analysis_run_id)).fetchall()
    coverage_rows=[CoverageRow(expected_source_id=r['expected_source_id'],status=r['status'],
        document_version_id=r['document_version_id'],gap_round=r['gap_round'],note=r['note']).model_dump(mode='json') for r in coverage]
    summary=PostgresStore(conn).analysis_coverage(ctx)
    expected={str(e.id):{**asdict(e),'id':str(e.id),'source_id':str(e.source_id)} for e in
        PostgresStore(conn).list_expected_sources(ctx.workspace_id,ctx.brief.topic,ctx.brief.jurisdictions)
        if str(e.source_id) in set(map(str,source_ids))}
    return {'schema_version':1,'brief':ctx.brief.model_dump(mode='json'),'source_ids':list(map(str,source_ids)),
        'evidence_input':evidence,'verifications':verifications,'coverage':coverage_rows,
        'analysis_coverage':summary.model_dump(mode='json') if summary else None,'expected_sources':expected,
        'reasons':[row['failure_summary']] if row['failure_summary'] else [],
        'prepared_through':ctx.brief.as_of_date.isoformat(),'prepared_at':datetime.now(UTC).isoformat()}


@dataclass
class PreparedSelection:
    claims:list=field(default_factory=list)
    passages:dict=field(default_factory=dict)
    findings:dict=field(default_factory=dict)
    bindings:list=field(default_factory=list)
    snapshots:dict=field(default_factory=dict)
    corroboration:dict=field(default_factory=dict)
    omissions:dict=field(default_factory=dict)
    coverage:list=field(default_factory=list)
    expected:dict=field(default_factory=dict)


def _nested_evidence_allowed(value,allowed,pins,snapshot,as_of):
    if isinstance(value,list):
        return all(_nested_evidence_allowed(v,allowed,pins,snapshot,as_of) for v in value)
    if not isinstance(value,dict):return True
    if 'source_id' in value:
        source=str(value['source_id'])
        if source not in allowed or pins.get(source)!=snapshot:return False
        if value.get('published_at') and date.fromisoformat(str(value['published_at'])[:10])>as_of:return False
    return all(_nested_evidence_allowed(v,allowed,pins,snapshot,as_of) for v in value.values())


def select_prepared_facts(snapshots,brief,source_snapshots,allowed_source_ids,reviews,*,max_facts=100):
    selected=PreparedSelection()
    allowed=set(map(str,allowed_source_ids));pins={str(k):str(v) for k,v in source_snapshots.items()}
    candidates={};origins={};evidence_by_snapshot={}
    for row in snapshots:
        sid=str(row['id']);payload=row['payload'];e=EvidenceInput.model_validate(payload['evidence_input'])
        admitted=set(map(str,row.get('admitted_source_ids',[]))) if 'admitted_source_ids' in row else {s for s,p in pins.items() if p==sid}
        local_pins={s:sid for s in admitted if s in allowed}
        excluded=set(map(str,row.get('excluded_finding_ids',[])))
        evidence_by_snapshot[sid]=e
        selected.snapshots[sid]={'published_at':str(row['published_at']),'prepared_through':payload.get('prepared_through'),
            'brief':payload.get('brief'),'source_ids':payload['source_ids'],'coverage':payload.get('coverage',[]),
            'analysis_coverage':payload.get('analysis_coverage'),'reasons':payload.get('reasons',[]),
            'expected_sources':payload.get('expected_sources',{}),
            'evidence_input':payload['evidence_input'],'verifications':payload['verifications']}
        for eid,raw in payload.get('expected_sources',{}).items():
            item=FrozenExpectedSource.model_validate(raw)
            if str(item.source_id) in allowed and pins.get(str(item.source_id))==sid:
                selected.expected[item.id]=ExpectedSourceRecord(**item.model_dump())
        for raw in payload.get('coverage',[]):
            coverage=CoverageRow.model_validate(raw)
            item=payload.get('expected_sources',{}).get(str(coverage.expected_source_id))
            if item and (str(item['source_id']) not in allowed or pins.get(str(item['source_id']))!=sid):continue
            selected.coverage.append(coverage)
        for fid,f in e.findings.items():
            key=str(fid)
            try:
                original=payload['verifications'][key]
                if key in excluded:raise ValueError('superseded_prepared_evidence')
                check=FrozenVerification.model_validate({k:v for k,v in original.items() if k!='input_snapshot'})
                if check.verdict!='supported' or check.method!=('inference_check' if f.is_inference else 'llm'):
                    raise ValueError('unsupported')
                if reviews.get((sid,key)) in ('rejected','correction_requested'):
                    raise ValueError('human_rejected')
                if f.jurisdiction_code and f.jurisdiction_code not in brief.jurisdictions:
                    raise ValueError('market_scope')
                # Use the source closure actually seen by the original check.
                exact=original.get('input_snapshot')
                closure=EvidenceInput.model_validate(exact) if exact else e
                if not set(closure.findings)<=set(e.findings):raise ValueError('invalid_closure')
                scope={str(p.source_id) for p in closure.passages.values()}
                if not scope or not scope<=allowed or any(local_pins.get(s)!=sid for s in scope):
                    raise ValueError('snapshot_or_source_scope')
                if any(p.published_at and p.published_at>brief.as_of_date for p in closure.passages.values()):
                    raise ValueError('publication_after_as_of')
                cor={str(k):v for k,v in (e.corroboration or {}).items() if k in closure.findings}
                if not _nested_evidence_allowed(cor,allowed,local_pins,sid,brief.as_of_date):
                    raise ValueError('corroboration_source_or_date_scope')
                candidates[(sid,key)]=f;origins[(sid,key)]=closure
            except (ValueError,KeyError) as exc:
                selected.omissions[f'{sid}:{key}']=str(exc)
    def eligible(key,visiting=None):
        if key not in candidates:return False
        visiting=set(visiting or ())
        if key in visiting:return False
        visiting.add(key)
        return all(eligible((key[0],str(d)),visiting) for d in candidates[key].depends_on)
    keys=[k for k in candidates if eligible(k)]
    keys.sort(key=lambda k:(reviews.get(k)!='accepted',candidates[k].is_inference,
        {'high':0,'medium':1,'low':2}[candidates[k].priority],
        -(candidates[k].key_date.toordinal() if candidates[k].key_date else 0),k))
    picked=[]
    def add(key):
        if key in picked:return
        for dep in candidates[key].depends_on:add((key[0],str(dep)))
        picked.append(key)
    for key in keys:
        closure=[]
        def collect(k):
            if k in closure:return
            for dep in candidates[k].depends_on:collect((k[0],str(dep)))
            closure.append(k)
        collect(key)
        if len({fid for sid,fid in set(picked)|set(closure)})<=max_facts:add(key)
        else:selected.omissions[f'{key[0]}:{key[1]}']='report_fact_limit'
    labels={k:f'C{i}' for i,k in enumerate(picked,1)}
    for key in picked:
        sid,fid=key;f=candidates[key];e=evidence_by_snapshot[sid]
        raw=f.model_dump(mode='json');fields=f.model_dump(exclude={'finding_id','evidence','depends_on'})
        draft=ClaimDraft(**fields,claim_label=labels[key],depends_on=[labels[(sid,str(d))] for d in f.depends_on],
            citations=[ClaimCitation(passage_label=f'P{i}',supporting_quote=c.supporting_quote) for i,c in enumerate(f.evidence,1)])
        passages=[PassageRecord(**e.passages[c.passage_id].model_dump()) for c in f.evidence]
        try:check_claim_period(draft,brief,passages)
        except ValueError as exc:
            selected.omissions[f'{sid}:{fid}']=str(exc);continue
        if any(d not in {c.finding_id for c in selected.claims} for d in f.depends_on):
            selected.omissions[f'{sid}:{fid}']='ineligible_dependency';continue
        if fid in selected.findings:continue
        selected.claims.append(StoredClaim(f.finding_id,draft,tuple(ClaimEvidence(c.passage_id,c.supporting_quote) for c in f.evidence),tuple(f.depends_on)))
        selected.findings[fid]=raw
        selected.bindings.append({'snapshot_id':sid,'finding_id':fid})
        selected.passages.update({p.id:p for p in passages})
        if e.corroboration:
            selected.corroboration.update({fid:e.corroboration[fid] for fid in origins[key].findings if fid in e.corroboration})
    # A report capture retains only the exact inputs it used, not unrelated
    # facts or candidate quotes from other scopes in a larger prepared snapshot.
    for sid,snapshot in selected.snapshots.items():
        evidence=evidence_by_snapshot[sid];used={UUID(b['finding_id']) for b in selected.bindings if b['snapshot_id']==sid}
        pids={c.passage_id for fid in used for c in evidence.findings[fid].evidence}
        narrowed=evidence.model_copy(update={'findings':{fid:evidence.findings[fid] for fid in used},
            'passages':{pid:evidence.passages[pid] for pid in pids},
            'corroboration':{fid:envelope for fid,envelope in (evidence.corroboration or {}).items() if fid in used} or None})
        snapshot['evidence_input']=narrowed.model_dump(mode='json')
        snapshot['verifications']={str(fid):snapshot['verifications'][str(fid)] for fid in used}
    return selected


_OPERATIVE_DATES = {'effective', 'deadline', 'consultation_close'}
_EXPLICIT_DEADLINE = re.compile(
    r'\b(?:must (?!not\b)|requires? [^.;]+? to )'
    r'(?:(?!\b(?:if|unless|only|before|after)\b)[^.;])+?\s+(?:by|no later than)\s+'
    r'(\d{4}-\d{2}-\d{2}|\d{1,2} [A-Za-z]+ \d{4})(?=\s|[.,;)]|$)', re.I,
)


def _timeline_date(claim: StoredClaim) -> tuple[KeyDateKind, date] | None:
    draft = claim.draft
    if draft.is_inference:
        return None
    if draft.key_date_kind in _OPERATIVE_DATES and draft.key_date is not None:
        return draft.key_date_kind, draft.key_date
    # Older facts may record their publication date even when the checked
    # statement gives a deadline. Recover only one explicit date from a
    # sentence already quoted verbatim, without changing the frozen finding.
    content = ' '.join(draft.content.split())
    if not any(content in ' '.join(c.supporting_quote.split()) for c in claim.evidence):
        return None
    matches = _EXPLICIT_DEADLINE.findall(content)
    if len(matches) != 1:
        return None
    for fmt in ('%Y-%m-%d', '%d %B %Y', '%d %b %Y'):
        try:
            return 'deadline', datetime.strptime(matches[0], fmt).date()
        except ValueError:
            continue
    return None


def compose_prepared_report(request_id,brief,selected,*,manifest=None):
    request_id=UUID(str(request_id));now=datetime.now(UTC)
    sections=writer.claim_sections(selected.claims)
    summary=ReportSection(section='executive_summary',sentences=[ReportSentence(text=c.draft.content,
        finding_ids=[c.finding_id],structural=False) for c in selected.claims[:5]],no_verified_items=not selected.claims)
    timeline_dates = {}
    timeline_sentences = []
    for claim in selected.claims:
        when = _timeline_date(claim)
        if when:
            timeline_dates[claim.finding_id] = when
        if when or claim.draft.finding_type == 'deadline':
            timeline_sentences.append(ReportSentence(
                text=claim.draft.content, finding_ids=[claim.finding_id], structural=False,
            ))
    timeline = ReportSection(section='deadlines_timeline', sentences=timeline_sentences,
                             no_verified_items=not timeline_sentences)
    sections = [summary, *(timeline if s.section == 'deadlines_timeline' else s for s in sections[1:])]
    notes=['This fresh report uses completed prepared evidence; no source acquisition or new factual wording was generated for this request.',
           'Human evidence checking, machine support, publication coverage and final report approval are separate.']
    if selected.omissions:notes.append(f'{len(selected.omissions)} prepared items were omitted by source/date/review/dependency or report limits.')
    for sid,s in selected.snapshots.items():
        a=s.get('analysis_coverage')
        if a:notes.append(f"Snapshot {sid}: {a.get('analysed_passages',0)} of {a.get('candidate_passages',0)} candidate passages analysed; {a.get('deferred_passages',0)} deferred, {a.get('failed_passages',0)} failed.")
        notes.extend(str(reason) for reason in s.get('reasons',[]))
    sections.append(ReportSection(section='coverage_limitations',sentences=[ReportSentence(text=n,finding_ids=[],structural=True) for n in notes],no_verified_items=False))
    snap=ReportSnapshot(contract_version='prepared/1',analysis_run_id=request_id,analysis_revision_id=request_id,
        sections=sections,coverage=selected.coverage,unresolved_finding_ids=[])
    ctx=ReportContext(brief=brief,run_status='draft',claims={c.finding_id:c for c in selected.claims},
        passages=selected.passages,unresolved={},generated_at=now,corroboration=selected.corroboration,
        expected=selected.expected,timeline_dates=timeline_dates)
    html=render_html(snap,ctx)
    scopes=(manifest or {}).get('scopes',[])
    freshness=''.join('<li>'+escape(str(s.get('source_name') or s.get('scope_id')))+': '+escape(str(s.get('published_at') or 'unknown'))+'</li>' for s in scopes)
    banner='<aside role="status" style="border:2px solid #ae7029;background:#fff5e6;padding:1rem;margin:1rem 0"><strong>{{PREPARED_REVIEW_WARNING}}</strong><p>Evidence snapshot freshness by source:</p><ul>'+freshness+'</ul></aside>'
    html=html.replace('</h1>','</h1>'+banner,1)
    html=html.replace('</ol></nav>','<li><a href="#prepared-fact-reviews">Human evidence decisions</a></li></ol></nav>',1)
    html=html.replace('</body>','{{PREPARED_FACT_REVIEWS}}</body>',1)
    capture={'schema_version':1,'kind':'prepared_report','request_id':str(request_id),'brief':brief.model_dump(mode='json'),
        'generated_at':now.isoformat(),'selected_findings':selected.findings,'bindings':selected.bindings,
        'snapshots':selected.snapshots,'report_snapshot':snap.model_dump(mode='json'),'omissions':selected.omissions,
        'manifest':manifest or {},'generation_method':'deterministic assembly of immutable machine-supported claims',
        'timeline_dates':{str(fid): {'kind':kind,'date':day.isoformat()} for fid,(kind,day) in timeline_dates.items()}}
    return html,capture


def execute_prepared_request(conn,dsn,request_id=None,client=None,*,workspace_id=None):
    """Claim a ready request and compose it without holding network/model locks."""
    from mira.preparation_store import PreparationStore
    store=PreparationStore(conn);owner=uuid4();started=time.monotonic()
    if request_id is not None:
        row=conn.execute('select * from public.prepared_report_requests where id=%s',(request_id,)).fetchone()
        if row is None:raise ValueError('Unknown prepared request')
        if workspace_id is not None and row['workspace_id']!=workspace_id:raise ValueError('Request workspace mismatch')
        workspace_id=row['workspace_id']
    if workspace_id is None:raise ValueError('Workspace required')
    request=store.claim_report_request(workspace_id,owner,request_id=request_id)
    if request is None:return {'status':'waiting','report_id':None}
    try:
        with acting_as(conn,request['actor_id']):require_role(conn,workspace_id)
        brief=Brief.model_validate(request['brief'])
        sources={str(s.id):s for s in PostgresStore(conn).list_sources(workspace_id)}
        allowed={sid for sid in map(str,request['source_ids']) if sid in sources and
                 {'fetch','store_text','quote'}<=set(sources[sid].permitted_operations)}
        entries=conn.execute('''select e.*,s.name as source_name,p.published_at from public.prepared_report_request_scopes e
            join public.sources s on s.id=e.scope_id and s.workspace_id=e.workspace_id
            left join public.prepared_snapshots p on p.id=e.snapshot_id and p.workspace_id=e.workspace_id
            where e.request_id=%s and e.workspace_id=%s order by e.scope_id''',(request['id'],workspace_id)).fetchall()
        pins={str(e['scope_id']):str(e['snapshot_id']) for e in entries if e['snapshot_id']}
        snapshots=store.load_request_snapshots(request['id'])
        reviews=conn.execute('''select distinct on(snapshot_id,finding_id) snapshot_id,finding_id,decision
            from public.prepared_fact_reviews where workspace_id=%s and snapshot_id=any(%s::uuid[])
            order by snapshot_id,finding_id,sequence desc''',(workspace_id,[s['id'] for s in snapshots])).fetchall()
        latest={(str(r['snapshot_id']),str(r['finding_id'])):r['decision'] for r in reviews}
        selection=select_prepared_facts(snapshots,brief,pins,allowed,latest)
        if not selection.claims:raise ValueError('No eligible machine-supported evidence for this request; preparation or review is needed')
        manifest={'scopes':[{'scope_id':str(e['scope_id']),'snapshot_id':str(e['snapshot_id']),
            'source_name':e['source_name'],'published_at':str(e['published_at'])} for e in entries],
            'queued_at':str(request['created_at']),'generation_started_at':str(request['generation_started_at'])}
        html,capture=compose_prepared_report(request['id'],brief,selection,manifest=manifest)
        report=store.publish_report(request,capture,html,selection.bindings)
        return {'status':'ready','report_id':report['id'],'seconds':time.monotonic()-started,
            'facts':len(selection.claims),'review_state':report['review_state']}
    except (ValueError,PermissionError) as exc:
        try:store.fail_report_request(request,str(exc))
        except ValueError:pass  # cancellation/lost lease must not be overwritten
        return {'status':'failed','report_id':None,'reason':str(exc)}
