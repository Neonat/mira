"""Strict read-only local-connection export for offline quality_preflight.measure.

No connection factory, environment access, runner, provider or live acquisition.
Caller supplies a trusted dict-row connection and the retained telemetry journal.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from uuid import UUID

try:
    from quality_preflight import MODELS, scope, budget, measure, safe_input
except ModuleNotFoundError:
    from eval.quality_preflight import MODELS, scope, budget, measure, safe_input


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError('Missing or invalid retained usage')
    return value


def model_matches(value, role):
    expected = MODELS.get(role)
    return bool(expected and value in (expected, expected.removeprefix('openai:')))


SCOUT_PROMPTS = frozenset({'scout/6'})  # mira.agents.scout.PROMPT_VERSION
CORROBORATION_PROMPTS = frozenset({'corroboration/2-bounded-excerpts', 'corroboration/3-single-candidate'})


def journal(telemetry, run_id, steps):
    """Reconcile events per persisted step; embedding usage is a disjoint channel."""
    if str(telemetry['run_id']) != str(run_id):
        raise ValueError('Foreign telemetry')
    events = telemetry['events']
    if any(e.get('run_id') != str(run_id) for e in events):
        raise ValueError('Missing or foreign event run identity')
    kinds = Counter(e['kind'] for e in events)
    if kinds['run_started'] != 1 or kinds['run_finished'] != 1 or kinds['run_resumed'] or events[0]['kind']!='run_started' or events[-1]['kind']!='run_finished':
        raise ValueError('Single uninterrupted execution proof required')
    starts = {e['id']: e for e in events if e['kind'] in ('model_started', 'embedding_started')}
    if len(starts) != kinds['model_started'] + kinds['embedding_started']:
        raise ValueError('Duplicate retained request identity')
    usage = {str(s['id']): [0, 0, 0, 0] for s in steps}
    terminal = set()
    cor = dict(requested=0, completed=0, errors=0, explicitly_reported_timeouts=0)
    for event in events:
        if event['kind'] not in ('model_completed', 'model_error', 'embedding_completed', 'embedding_error'):
            continue
        start = starts.get(event['id'])
        if not start or event['id'] in terminal or event['kind'].split('_')[0] != start['kind'].split('_')[0]:
            raise ValueError('Unbound or duplicate retained terminal event')
        terminal.add(event['id'])
        sid = start['step_id']
        if sid not in usage:
            raise ValueError('Foreign event step')
        if event['kind'].endswith('error') and type(event.get('usage_known')) is not bool:
            raise ValueError('Explicit failed-request usage provenance required')
        known = event['kind'].endswith('completed') or event['usage_known'] is True
        tokens = count(event['tokens_in']) + count(event['tokens_out']) if event['kind'].endswith('completed') else count(event['charged_or_reserved'])
        offset = 2 if start['kind'] == 'embedding_started' else 0
        usage[sid][offset + (0 if known else 1)] += tokens
        if start['kind'] == 'model_started':
            step = next(s for s in steps if str(s['id']) == sid)
            if not model_matches(start['model'], step['role']) or not model_matches(step['model'], step['role']):
                raise ValueError('Actual request/step role model mismatch')
            prompt, persisted = start.get('prompt_version'), step['prompt_version']
            if not persisted or prompt != persisted:
                raise ValueError('Request/persisted prompt version mismatch')
            if step['role'] in ('regulatory_scout','industry_scout') and prompt not in SCOUT_PROMPTS:
                raise ValueError('Unrecognized scout request prompt version')
            is_cor = step['role']=='verifier' and step['input_refs'].get('purpose')=='corroboration'
            if is_cor != (prompt in CORROBORATION_PROMPTS) or str(prompt).startswith('corroboration/') and not is_cor:
                raise ValueError('Corroboration purpose/prompt classification mismatch')
            if is_cor:
                cor['requested'] += 1
                cor['completed' if known and event['kind']=='model_completed' else 'errors'] += 1
                cor['explicitly_reported_timeouts'] += event.get('error_code') in ('timeout', 'timed_out', 'request_timeout')
    if set(starts) != terminal:
        raise ValueError('Incomplete retained request journal')
    for s in steps:
        sid, out = str(s['id']), s['output_refs']
        embedding = out.get('embedding_usage') or {}
        db = [count(s['tokens_in'] or 0) + count(s['tokens_out'] or 0), count(out.get('reserved_tokens', 0)),
              count(embedding.get('tokens', 0)), count(embedding.get('reserved_tokens', 0))]
        if usage[sid] != db:
            raise ValueError('Database/journal usage disagreement; missing accounting stage')
        if s['model'] and (not model_matches(s['model'], s['role']) or not any(e['step_id']==sid for e in starts.values())):
            raise ValueError('Missing request usage or unexpected persisted model')
    exa = [e for e in events if e['kind']=='exa_requested']
    if len({e['id'] for e in exa}) != len(exa):
        raise ValueError('Duplicate Exa request identity')
    return dict(actual_tokens=sum(u[0]+u[2] for u in usage.values()),
                reserved_tokens=sum(u[1]+u[3] for u in usage.values()), exa_searches=len(exa)), cor


def export_retained(conn, run_id, *, telemetry: Mapping) -> dict:
    """Export one disposable workspace run under a consistent read-only snapshot.

    Must be called outside an existing transaction. No caller commits or data
    mutations occur; the nested load_records helper sets transaction-local claims.
    Missing accounting/ledger/frozen settings refuse export rather than invent data.
    """
    run_id = UUID(str(run_id))
    safe_input(dict(telemetry))
    with conn.transaction():
        conn.execute('set transaction isolation level repeatable read read only')
        try:
            return _export(conn, run_id, telemetry)
        except (KeyError, TypeError) as exc:
            raise ValueError('Required retained export field missing or malformed') from exc


def report_records(conn, report, live, roots, ws, run_id, rev):
    """Use immutable reviewed input or prove draft input against checks as of generation."""
    try:
        from run_live import RunRecords, Finding, Evidence
    except ModuleNotFoundError:
        from eval.run_live import RunRecords, Finding, Evidence
    if report['review_status']=='reviewed':
        # Reuse the existing strict frozen renderer hydration, including amendments,
        # dependency closure, verification and frozen-quotation validation; no render/call.
        from mira.contracts import ReportSnapshot
        from mira.render import frozen_context
        snapshot = ReportSnapshot.model_validate(report['evidence_snapshot'])
        context = frozen_context(snapshot, report['generated_at'])
        scope(context.brief.model_dump(mode='json'))
        if context.decided_at != report['reviewed_at'] or (snapshot.evidence_bundle.workspace_id,snapshot.analysis_run_id,snapshot.analysis_revision_id)!=(ws,run_id,rev):
            raise ValueError('Frozen reviewed report metadata mismatch')
        findings = {str(fid):Finding(c.draft.title,c.draft.content,c.draft.is_inference) for fid,c in context.claims.items()}
        evidence = {str(fid):[Evidence(context.passages[e.passage_id].source_url,e.supporting_quote,context.passages[e.passage_id].content) for e in c.evidence] for fid,c in context.claims.items()}
        dependencies = {str(fid):[str(d) for d in c.depends_on] for fid,c in context.claims.items()}
        return RunRecords(findings,evidence,dependencies), dict(mode='frozen_reviewed_bundle',generated_at=report['generated_at'].isoformat(),reviewed_at=report['reviewed_at'].isoformat())
    needed, visiting = set(), set()
    def retain(fid):
        if fid in visiting or fid not in live.findings:
            raise ValueError('Draft cited finding closure incomplete or cyclic')
        if fid in needed:
            return
        visiting.add(fid)
        for dep in live.depends_on.get(fid, ()):
            retain(dep)
        visiting.remove(fid)
        needed.add(fid)
    for fid in roots:
        retain(fid)
    bindings = []
    for fid in sorted(needed):
        checked = conn.execute("""select *,input_snapshot=private.capture_evidence_input(%s,%s,%s,array[%s]::uuid[])
          and input_fingerprint=private.evidence_input_fingerprint(input_snapshot) bound
          from public.claim_checks where workspace_id=%s and analysis_run_id=%s and finding_id=%s and checked_at<=%s
          order by checked_at desc,attempt desc,id desc limit 1""",(ws,run_id,rev,fid,ws,run_id,fid,report['generated_at'])).fetchone()
        method = 'inference_check' if live.findings[fid].is_inference else 'llm'
        if not checked or not checked['bound'] or checked['verdict']!='supported' or checked['method']!=method or not model_matches(checked['model'],'verifier'):
            raise ValueError('Draft report cited evidence lacks matching verification as of generation')
        bindings.append(dict(finding_id=fid,check_id=str(checked['id']),checked_at=checked['checked_at'].isoformat(),input_fingerprint=checked['input_fingerprint']))
    return live, dict(mode='draft_checks_as_of_generation',generated_at=report['generated_at'].isoformat(),checks=bindings)


def _export(conn, run_id, telemetry):
    r = conn.execute('select * from public.analysis_runs where id=%s', (run_id,)).fetchone()
    if not r or r['status'] not in ('partial','failed','draft','reviewed','superseded') or not r['finished_at']:
        raise ValueError('Terminal run required')
    ws = r['workspace_id']
    if conn.execute('select count(*) n from public.analysis_runs where workspace_id=%s', (ws,)).fetchone()['n'] != 1 or r['previous_run_id']:
        raise ValueError('Exactly one disposable workspace run required')
    p = conn.execute('select * from public.project_revisions where id=%s and workspace_id=%s', (r['project_revision_id'],ws)).fetchone()
    frozen = scope(dict(topic=p['risk_topics'][0] if len(p['risk_topics'])==1 else None,
                        jurisdictions=[v.strip() for v in p['markets']],
                        period_start=p['reporting_period_start'].isoformat(), period_end=p['reporting_period_end'].isoformat(),
                        as_of_date=r['as_of_date'].isoformat()))
    # Read stored limits only: no from_env defaults or historical settings repair.
    limits = budget(dict(r['source_limits'], max_exa_searches=telemetry['max_exa_searches']))
    if r['model_settings'] != MODELS:
        raise ValueError('Frozen model settings unset or mismatched; no automatic configuration')
    revs = conn.execute('select id from public.analysis_revisions where analysis_run_id=%s order by revision_number', (run_id,)).fetchall()
    if len(revs) != 1:
        raise ValueError('One analysis revision required')
    rev = revs[0]['id']
    steps = conn.execute('select * from public.agent_steps where analysis_run_id=%s order by step_no', (run_id,)).fetchall()
    if any(s['status'] in ('queued','running') for s in steps):
        raise ValueError('Unfinished persisted steps')
    usage, calls = journal(telemetry, run_id, steps)
    for s in steps:
        out = s['output_refs']
        if 'fetch_attempts' in out and out['fetch_attempts'] != len(out.get('fetch_log', [])):
            raise ValueError('Machine fetch log incomplete')
    targeted = conn.execute("select result from public.corroboration_assessments where analysis_run_id=%s", (run_id,)).fetchall()
    cor_attempts = sum(count(a['result']['document_attempts']) for a in targeted)
    if count(telemetry.get('corroboration_document_attempts', 0)) != cor_attempts:
        raise ValueError('Corroboration acquisition counter/journal disagreement')
    cor_mas = count(telemetry['corroboration_mas_fetches']) if cor_attempts else 0
    logs = [log for s in steps for log in s['output_refs'].get('fetch_log', [])]
    if any(type(log.get('request_sent')) is not bool for log in logs):
        raise ValueError('Fetch log request accounting missing')
    scout_attempts = sum(log['request_sent'] and log['outcome'] not in ('refused','reused') for log in logs)
    usage['documents'] = scout_attempts + cor_attempts
    versions = conn.execute('select v.source_url,s.source_key from public.document_versions v join public.documents d on d.id=v.document_id join public.sources s on s.id=d.source_id where v.workspace_id=%s', (ws,)).fetchall()
    mas = conn.execute("select is_active from public.sources where workspace_id=%s and source_key='mas'", (ws,)).fetchall()
    if len(mas)!=1 or mas[0]['is_active'] is not False:
        raise ValueError('Explicit inactive MAS row required')
    mas_result = dict(active=False, fetches=cor_mas + sum('mas.gov.sg' in log.get('url','') for log in logs),
                      versions=sum(v['source_key']=='mas' or 'mas.gov.sg' in v['source_url'] for v in versions))
    coverage = conn.execute('select private.capture_analysis_coverage(%s,%s,%s) value', (ws,run_id,rev)).fetchone()['value']
    if coverage is None:
        raise ValueError('Frozen passage ledger policy missing')
    passages = conn.execute('select distinct on(passage_id) passage_id,status,batch_id,agent_step_id,sequence from public.analysis_passage_events where workspace_id=%s and analysis_run_id=%s and analysis_revision_id=%s order by passage_id,sequence desc', (ws,run_id,rev)).fetchall()
    if len(passages) != coverage['candidate_passages']:
        raise ValueError('Canonical coverage and latest passage events disagree')
    reports = conn.execute('select id,report_version,evidence_snapshot,generated_at,review_status,reviewed_at from public.reports where workspace_id=%s and analysis_revision_id=%s order by report_version desc limit 1', (ws,rev)).fetchone()
    snapshot = reports['evidence_snapshot'] if reports else None
    if snapshot and snapshot.get('analysis_coverage') != coverage:
        raise ValueError('Final report passage ledger mismatch')
    try:
        from run_live import load_records, report_finding_ids, cited_urls, claim_rows
    except ModuleNotFoundError:
        from eval.run_live import load_records, report_finding_ids, cited_urls, claim_rows
    records = load_records(conn, r['created_by'], run_id)
    cited = report_finding_ids(snapshot) if snapshot else []
    report_input, report_binding = report_records(conn,reports,records,cited,ws,run_id,rev) if reports else (records,None)
    findings = []
    for fid in records.findings:
        # A stale/unbound latest primary verdict remains not_checked.
        check = conn.execute('''select *, input_snapshot=private.capture_evidence_input(%s,%s,%s,array[%s]::uuid[])
          and input_fingerprint=private.evidence_input_fingerprint(input_snapshot) bound
          from public.claim_checks where workspace_id=%s and analysis_run_id=%s and finding_id=%s
          order by checked_at desc,attempt desc,id desc limit 1''', (ws,run_id,rev,fid,ws,run_id,fid)).fetchone()
        assessment = conn.execute('''select *,base_input=private.capture_base_evidence_input(%s,%s,%s,array[%s]::uuid[]) bound
          from public.corroboration_assessments where workspace_id=%s and analysis_run_id=%s and finding_id=%s
          order by sequence desc limit 1''', (ws,run_id,rev,fid,ws,run_id,fid)).fetchone()
        required_method = 'inference_check' if records.findings[fid].is_inference else 'llm'
        primary = check['verdict'] if check and check['bound'] and (check['verdict']!='supported' or check['method']==required_method and model_matches(check['model'],'verifier')) else 'not_checked'
        f = dict(id=fid, primary_verification=primary, corroboration='not_checked',
                 primary_check=None if not check else dict(id=str(check['id']),method=check['method'],model=check['model'],bound=bool(check['bound']),verdict=check['verdict']),
                 corroboration_assessment=None if not assessment else dict(id=str(assessment['id']),bound=bool(assessment['bound']),persisted_status=assessment['result']['status']))
        if assessment and assessment['bound']:
            a = assessment['result']
            f['corroboration'] = {'independently_corroborated':'independent_support', 'conflicting_evidence':'conflicting'}.get(a['status'], a['status'])
            if f['corroboration']=='independent_support':
                primary_ids = {p['id'] for p in a.get('primary', [])}
                frozen_passages = {p['id']:p['content'] for p in a.get('primary', [])}
                frozen_passages.update({c['passage']['id']:c['passage']['content'] for c in a.get('candidates', [])})
                origins = []
                for d in a['decisions']:
                    rows = d['origin_evidence']
                    ids = {o['passage_id'] for o in rows if o['kind']=='original_reporting'}
                    if d['origin_relation']=='independent' and d['relation']=='supports' and d['passage_id'] in ids and ids.intersection(primary_ids) and all(o['kind']=='original_reporting' and o['quote'] and o['quote'] in frozen_passages.get(o['passage_id'], '') for o in rows):
                        origins.extend(rows)
                if not origins:
                    raise ValueError('Independent status lacks retained origin evidence')
                f['independence_evidence_refs'] = [dict(assessment_id=str(assessment['id']),passage_id=o['passage_id'],quote=o['quote']) for o in origins]
        findings.append(f)
    batches = [s['input_refs']['batch_id'] for s in steps if s['role']=='analyst' and 'batch_id' in s['input_refs']]
    if len(batches)!=len(set(batches)):
        raise ValueError('Repeated analysis batch identity')
    batches = sorted(batches)
    result = dict(kind='live_retained', run_id=str(run_id), scope=frozen, models=dict(r['model_settings']), budget=limits,
                  status=r['status'], outcome_status=telemetry['outcome_status'], started_at=r['started_at'].isoformat(), finished_at=r['finished_at'].isoformat(),
                  usage=usage, mas=mas_result, acquired_urls=[v['source_url'] for v in versions], cited_urls=cited_urls(cited,report_input),
                  passages=[dict(id=str(p['passage_id']),status=p['status'],batch_id=p['batch_id'],agent_step_id=str(p['agent_step_id']) if p['agent_step_id'] else None,event_sequence=p['sequence']) for p in passages], findings=findings, corroboration_calls=calls,
                  report_exists=bool(snapshot), report=None if not reports else dict(id=str(reports['id']),version=reports['report_version']),
                  saved_versions=len(versions), acquisition_counters=dict(scout_machine_logs=scout_attempts,corroboration_assessments_all=cor_attempts,corroboration_per_url_logs_available=False),
                  telemetry_counts=dict(Counter(e['kind'] for e in telemetry['events'])), analysis_coverage=coverage, unique_batch_ids=batches,
                  actual_step_models=[dict(step_id=str(s['id']),role=s['role'],model=s['model']) for s in steps if s['model']],
                  clean=dict(unresumed=True,ledger_policies=1,run_started_events=1,run_finished_events=1),
                  report_binding=report_binding,
                  claims=[dict(claim=c.claim,cited_passage=c.cited_passage,supporting_quote=c.supporting_quote) for c in claim_rows('blind',cited,report_input)])
    measure(result)  # pending passage statuses and out-of-bounds accounting fail honestly
    return result
