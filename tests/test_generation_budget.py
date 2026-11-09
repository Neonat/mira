import pytest
from types import SimpleNamespace

from mira.llm import LLMError


def test_admission_keeps_downstream_headroom_and_refusals_cost_zero():
    from mira.generation import GenerationBudget
    b=GenerationBudget(100000,1000)
    with pytest.raises(LLMError) as e:b.start('model','regulatory_scout',80000)
    assert e.value.request_sent is False
    assert b.snapshot()['known_tokens']==b.snapshot()['unknown_reserved_tokens']==0
    item=b.start('model','writer',80000);b.finish(item,known=20)
    assert b.snapshot()['known_tokens']==20 and b.snapshot()['pending_tokens']==0


def test_unknown_failed_attempt_and_local_decline_are_different():
    from mira.generation import GenerationBudget
    b=GenerationBudget(100000,1000)
    sent=b.start('model','writer',20000);b.finish(sent,error=LLMError('timeout',request_sent=True,reserved_tokens=20000))
    local=b.start('model','writer',10000);b.finish(local,error=LLMError('local',request_sent=False))
    assert b.snapshot()['unknown_reserved_tokens']==20000
    assert b.snapshot()['pending_tokens']==0


def test_model_client_uses_requested_analysis_deadline_and_exact_formula():
    from mira.generation import GenerationBudget,GenerationClient
    from mira.contracts import LinkSelection
    from mira.llm import request_token_reservation
    seen=[]
    def complete(**kw):seen.append(kw);return SimpleNamespace(tokens_in=10,tokens_out=4,model='unchanged')
    b=GenerationBudget(600000,1500);client=GenerationClient(SimpleNamespace(structured_bounded=complete),b)
    r=client.structured_bounded(role='analyst',system='x',user='y',output_type=LinkSelection,prompt_version='test',timeout_seconds=120,max_output_tokens=8192)
    assert seen[0]['timeout_seconds']>119 and r.model=='unchanged'
    assert b.snapshot()['calls'][0]['reservation_tokens']==request_token_reservation(system='x',user='y',output_type=LinkSelection,max_output_tokens=8192)


def test_clock_and_pending_requests_share_one_hard_bound():
    from mira.generation import GenerationBudget
    now=[0.];b=GenerationBudget(100000,10,clock=lambda:now[0])
    a=b.start('model','writer',70000)
    with pytest.raises(LLMError):b.start('model','writer',40000)
    now[0]=11
    with pytest.raises(LLMError):b.start('model','writer',1)
    b.finish(a,known=100)
    assert b.snapshot()['known_tokens']==100


def test_nonwriter_calls_preserve_writer_time():
    from mira.generation import GenerationBudget
    now=[0.];b=GenerationBudget(600000,1500,clock=lambda:now[0]);now[0]=1400
    with pytest.raises(LLMError) as e:b.start('model','verifier',1000)
    assert e.value.request_sent is False
    call=b.start('model','writer',1000);b.finish(call,known=10)


def test_ordinary_client_is_rejected_locally_before_admission():
    from mira.generation import GenerationBudget,GenerationClient
    from mira.contracts import LinkSelection
    b=GenerationBudget(600000,1500);client=GenerationClient(SimpleNamespace(structured=lambda **k:None),b)
    with pytest.raises(LLMError) as e:client.structured(role='writer',system='x',user='y',output_type=LinkSelection,prompt_version='test')
    assert e.value.request_sent is False and b.snapshot()['allowance_used']==0


def test_embedding_refusal_is_zero_cost_and_timeout_preserves_reserve():
    from mira.generation import GenerationBudget,GenerationEmbedder
    from mira.hybrid import EmbeddingError,EmbeddingResult
    b=GenerationBudget(10,1000)
    with pytest.raises(EmbeddingError) as e:GenerationEmbedder(None,b).embed(['too much input'],timeout_seconds=10)
    assert e.value.tokens==0 and e.value.request_sent is False and b.snapshot()['allowance_used']==0
    now=[0.];b=GenerationBudget(600000,1500,clock=lambda:now[0]);now[0]=1100;calls=[]
    def embed(texts,**kw):calls.append(kw);return EmbeddingResult(((1.,),),1)
    GenerationEmbedder(SimpleNamespace(embed=embed),b).embed(['x'],timeout_seconds=200)
    assert calls[0]['timeout_seconds']<=40
