"""The live path narrows retrieval before projection, without weakening assessment rules."""
from types import SimpleNamespace
from test_corroboration import fixture, Assessor
import mira.corroboration_runtime as runtime
from mira.corroboration import validate_frozen_assessment, CorroborationAssessment


def test_runtime_uses_same_small_passage_bound_for_retrieval_and_frozen_limits(monkeypatch):
    args,batch,_=fixture()
    seen=[]
    class Ledger:
        evidence=SimpleNamespace(list_sources=lambda ws:args['sources'])
        def candidates(self,ctx,claim,**limits):
            seen.append(limits)
            return args['saved_candidates']
        def save(self,ctx,claim,base,result):
            validate_frozen_assessment(CorroborationAssessment.model_validate(result))
            return {'assessment_id':'test','sequence':1,'assessment':result}
    monkeypatch.setattr(runtime,'CorroborationStore',lambda conn:Ledger())
    monkeypatch.setattr(runtime,'LlmAssessor',lambda client:Assessor(batch))
    envelope=runtime.ClaimCorroborator(None,object())(args['ctx'],args['claim'],args['base_evidence_input'],args['budget'])
    assert seen==[{'max_passages':1}]
    assert envelope['assessment']['limits']['max_passages']==1
    assert envelope['assessment']['limits']['max_seconds']==90
    assert envelope['assessment']['status']=='independently_corroborated'


def test_saved_assessment_is_pure_until_coordinator_persists(monkeypatch):
    from threading import get_ident
    from concurrent.futures import ThreadPoolExecutor
    args,batch,_=fixture()
    owner=get_ident()
    writes=[]
    class Ledger:
        evidence=SimpleNamespace(list_sources=lambda ws:args['sources'])
        def candidates(self,*a,**kw):
            assert get_ident()==owner
            return args['saved_candidates']
        def save(self,ctx,claim,base,result):
            assert get_ident()==owner
            writes.append(result)
            return {'assessment_id':'test','sequence':1,'assessment':result}
    monkeypatch.setattr(runtime,'CorroborationStore',lambda conn:Ledger())
    monkeypatch.setattr(runtime,'LlmAssessor',lambda client:Assessor(batch))
    corroborator=runtime.ClaimCorroborator(None,object())
    prepared=corroborator.prepare_saved(args['ctx'],args['claim'],args['base_evidence_input'])
    assert prepared is not None
    with ThreadPoolExecutor(max_workers=1) as pool:
        result=pool.submit(prepared.evaluate,args['budget']).result(timeout=2)
    assert writes==[]
    envelope=prepared.persist(result)
    validate_frozen_assessment(CorroborationAssessment.model_validate(envelope['assessment']))
    assert len(writes)==1


def test_prepared_assessment_retains_live_followup_for_ineligible_saved_candidate(monkeypatch):
    args,batch,_=fixture()
    invalid=args['saved_candidates'][0].model_copy(update={'passage':
        args['saved_candidates'][0].passage.model_copy(update={'jurisdiction_code':'AE'})})
    class Ledger:
        evidence=SimpleNamespace(list_sources=lambda ws:args['sources'])
        def candidates(self,*a,**kw):return [invalid]
    monkeypatch.setattr(runtime,'CorroborationStore',lambda conn:Ledger())
    corroborator=runtime.ClaimCorroborator(None,object(),discovery=object())
    assert corroborator.prepare_saved(args['ctx'],args['claim'],args['base_evidence_input']) is None


def test_prepared_assessment_does_not_claim_enabled_discovery_is_disabled(monkeypatch):
    args,batch,_=fixture()
    class Ledger:
        evidence=SimpleNamespace(list_sources=lambda ws:args['sources'])
        def candidates(self,*a,**kw):return args['saved_candidates']
    monkeypatch.setattr(runtime,'CorroborationStore',lambda conn:Ledger())
    monkeypatch.setattr(runtime,'LlmAssessor',lambda client:Assessor(batch))
    corroborator=runtime.ClaimCorroborator(None,object(),discovery=object())
    prepared=corroborator.prepare_saved(args['ctx'],args['claim'],args['base_evidence_input'])
    result=prepared.evaluate(args['budget'])
    assert 'discovery_disabled' not in result['stop_reasons']
    assert 'assessment_attempt_limit' in result['stop_reasons']
