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
    assert seen==[{'max_passages':2}]
    assert envelope['assessment']['limits']['max_passages']==2
    assert envelope['assessment']['status']=='independently_corroborated'
