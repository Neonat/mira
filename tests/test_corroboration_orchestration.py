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
