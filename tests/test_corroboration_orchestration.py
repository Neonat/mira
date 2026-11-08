"""Corroboration enters actual verifier context before input is captured."""
from test_orchestrator import make, context, FakeVerifier


def test_assessment_precedes_checks_is_bound_and_tokens_are_not_double_charged():
    class Verifier(FakeVerifier):
        def check_fact(self, claim, passages, attempt, *, corroboration=None):
            assert corroboration and claim.finding_id in corroboration
            return super().check_fact(claim, passages, attempt)
        def check_inference(self, claim, facts, attempt, *, corroboration=None):
            assert corroboration
            return super().check_inference(claim, facts, attempt)
    orchestrator, store, _, _ = make(verifier=Verifier())
    called=[]
    def assess(ctx, claim, base, budget):
        assert 'corroboration' not in base
        budget.charge_tokens(7,3)
        called.append(claim.finding_id)
        return {'assessment_id':'fixture','sequence':len(called),'assessment':{
            'status':'primary_source_only','tokens_in':7,'tokens_out':3,'model':'fixture','prompt_version':'fixture/1'}}
    orchestrator.corroborator = assess
    result = orchestrator.run(context())
    assert result.status == 'draft', result.reasons
    assert called
    checks = [c for c in store.check_inputs if c]
    assert any('corroboration' in c for c in checks)


def test_failed_assessment_persistence_keeps_known_usage_in_failed_step():
    import pytest
    orchestrator,store,_,_=make()
    class PersistenceFailure(RuntimeError):
        assessment={'tokens_in':11,'tokens_out':5,'model':'fixture','prompt_version':'fixture/1','reserved_tokens':0}
    def fail(ctx,claim,base,budget):
        budget.charge_tokens(11,5)
        raise PersistenceFailure('failed to save assessment')
    orchestrator.corroborator=fail
    with pytest.raises(PersistenceFailure):
        orchestrator.run(context())
    step=next(s for s in store.steps.values() if s.input_refs.get('purpose')=='corroboration')
    assert step.status=='failed' and step.tokens_in==11 and step.tokens_out==5


def test_nonverbatim_primary_quote_is_left_to_verifier_without_crashing():
    from test_orchestrator import analyst_output,claim
    from mira.agents.verifier import LlmVerifier
    orchestrator,store,client,_=make(responses={'analyst':[analyst_output(
        claim('C1','external_fact','P3','penalty of S$7 million'))]})
    orchestrator.verifier=LlmVerifier(client)
    def must_not_assess(*a,**kw):raise ValueError('primary quote absent from base evidence')
    orchestrator.corroborator=must_not_assess
    result=orchestrator.run(context())
    assert result.status=='draft'
    assert len(result.snapshot.unresolved_finding_ids)==1
    assert not any(c.role=='verifier' for c in client.calls)
    step=next(s for s in store.steps.values() if s.input_refs.get('purpose')=='corroboration')
    assert step.output_refs['corroboration_status']=='not_checked'
    assert 'exact' in step.output_refs['reason']


def test_extraction_whitespace_quote_can_verify_without_claiming_corroboration():
    from test_orchestrator import analyst_output,claim
    from mira.agents.verifier import LlmVerifier
    orchestrator,store,client,_=make(responses={'analyst':[analyst_output(
        claim('C1','obligation_summary','P1','Banks must\nscreen customers',change_type='amended'))],
        'verifier':[{'verdict':'supported','reason':'Saved text supports the claim.'}]})
    orchestrator.verifier=LlmVerifier(client)
    def must_not_assess(*a,**kw):raise ValueError('primary quote absent from base evidence')
    orchestrator.corroborator=must_not_assess
    result=orchestrator.run(context())
    assert result.status=='draft' and not result.snapshot.unresolved_finding_ids
    assert not any('corroboration' in v for v in store.check_inputs)
    assert any(c.role=='verifier' for c in client.calls)


def test_skipped_rewritten_quote_removes_prior_claim_assessment_from_context():
    from dataclasses import replace
    from mira.orchestrator import _Run
    from test_evidence_snapshot import inputs
    ctx,claim,_,passage=inputs()
    orchestrator,_,_,_=make()
    orchestrator.corroborator=lambda *a: (_ for _ in ()).throw(AssertionError('should skip'))
    state=_Run(orchestrator,ctx)
    state.passages={passage.id:passage}
    changed=replace(claim,evidence=(replace(claim.evidence[0],supporting_quote='not verbatim'),))
    state.claims=[changed]
    state.corroboration[claim.finding_id]={'assessment_id':'old','assessment':{'status':'independently_corroborated'}}
    state._corroborate(changed)
    assert claim.finding_id not in state.corroboration
    assert state._corroboration_kwargs(changed)=={}
