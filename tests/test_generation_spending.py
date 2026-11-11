from decimal import Decimal as D
from types import SimpleNamespace
import pytest
from mira.contracts import LinkSelection
from mira.llm import LLMError
from test_spending import book


def budget(amount='1',**kw):
    from mira.generation import GenerationBudget
    from mira.spending import SpendingLedger
    return GenerationBudget(600000,1500,spending=SpendingLedger(D(amount),book()),models={'writer':'openai:fixture'},**kw)


def invoke(client):
    return client.structured_bounded(role='writer',system='s',user='u',output_type=LinkSelection,
        prompt_version='fixture',timeout_seconds=10,max_output_tokens=100)


def test_cost_refusal_never_dispatches_a_model_request():
    from mira.generation import GenerationClient
    called=[];b=budget('.000001')
    client=GenerationClient(SimpleNamespace(structured_bounded=lambda **kw:called.append(kw)),b)
    with pytest.raises(LLMError) as error:invoke(client)
    assert called==[] and error.value.request_sent is False
    assert b.snapshot()['spending']['allowance_used_usd']=='0.000000'


def test_measured_model_usage_settles_both_ledgers_and_safe_journal():
    from mira.generation import GenerationClient
    seen=[];b=budget(on_change=seen.append)
    base=SimpleNamespace(structured_bounded=lambda **kw:SimpleNamespace(tokens_in=100,tokens_out=50,model='fixture'))
    invoke(GenerationClient(base,b))
    assert b.snapshot()['known_tokens']==150
    assert seen[-1]['spending']['known_estimated_usd']=='0.000200'
    assert seen[-1]['spending']['pending_usd']=='0.000000'
    assert 'input_per_million' not in str(seen[-1])


@pytest.mark.parametrize('sent,known',[ (True,False),(False,False),(True,True) ])
def test_failed_model_request_keeps_cost_uncertainty_or_known_usage(sent,known):
    from mira.generation import GenerationClient
    b=budget()
    def fail(**kw):raise LLMError('fixture',3 if known else 0,4 if known else 0,request_sent=sent)
    with pytest.raises(LLMError):invoke(GenerationClient(SimpleNamespace(structured_bounded=fail),b))
    state=b.snapshot()['spending']
    assert state['pending_usd']=='0.000000'
    if known:assert state['known_estimated_usd']=='0.000011'
    elif sent:assert D(state['unknown_reserved_usd'])>0
    else:assert state['allowance_used_usd']=='0.000000'


def test_token_rejection_releases_money_reservation():
    from mira.generation import GenerationBudget,GenerationClient
    from mira.spending import SpendingLedger
    b=GenerationBudget(10,1500,spending=SpendingLedger(D('1'),book()),models={'writer':'openai:fixture'})
    with pytest.raises(LLMError):invoke(GenerationClient(SimpleNamespace(structured_bounded=lambda **kw:None),b))
    assert b.snapshot()['spending']['pending_usd']=='0.000000'


def test_embedding_and_exa_are_included_in_the_same_cost_journal():
    from mira.generation import GenerationEmbedder,GenerationSearch
    from mira.hybrid import EmbeddingIdentity,EmbeddingResult
    b=budget()
    embed=SimpleNamespace(identity=EmbeddingIdentity('embed','fixture',1),embed=lambda *a,**kw:EmbeddingResult(((1.,),),100))
    GenerationEmbedder(embed,b).embed(['saved public passage'],timeout_seconds=2)
    result=GenerationSearch(lambda *a:[{'url':'https://example.test/public'}],b)('fixture query',10,2)
    assert len(result)==1
    assert b.snapshot()['spending']['known_estimated_usd']=='0.010100'
    assert b.snapshot()['spending']['pending_usd']=='0.000000'


def test_unavailable_usage_journal_stops_before_provider_dispatch():
    from mira.generation import GenerationClient
    calls=[]
    def unavailable(_):raise RuntimeError('database unavailable')
    b=budget(on_change=unavailable)
    client=GenerationClient(SimpleNamespace(structured_bounded=lambda **kw:calls.append(kw)),b)
    with pytest.raises(LLMError) as error:invoke(client)
    assert error.value.request_sent is False and calls==[]
    assert b.snapshot()['spending']['allowance_used_usd']=='0.000000'


def test_unexpected_usage_overrun_keeps_both_measured_ledgers_and_stops_next_call():
    from mira.generation import GenerationClient
    calls=[];b=budget()
    def complete(**kw):calls.append(kw);return SimpleNamespace(tokens_in=2000000,tokens_out=10,model='fixture')
    client=GenerationClient(SimpleNamespace(structured_bounded=complete),b)
    with pytest.raises(LLMError) as error:invoke(client)
    assert (error.value.tokens_in,error.value.tokens_out)==(2000000,10)
    assert b.snapshot()['known_tokens']==2000010
    assert b.snapshot()['spending']['known_estimated_usd']=='2.000020'
    with pytest.raises(LLMError):invoke(client)
    assert len(calls)==1


def test_restored_pricing_mismatch_refuses_new_dispatch():
    from mira.generation import GenerationClient
    calls=[]
    b=budget(initial_usage={'pricing_mismatch':True})
    with pytest.raises(LLMError):
        invoke(GenerationClient(SimpleNamespace(structured_bounded=lambda **kw:calls.append(kw)),b))
    assert not calls and b.snapshot()['pricing_mismatch'] is True


@pytest.mark.parametrize('field,value', [
    ('known_tokens', -1), ('known_tokens', 1.5), ('known_tokens', float('nan')),
    ('unknown_reserved_tokens', -1), ('pending_tokens', -1),
    ('elapsed_seconds', -1), ('elapsed_seconds', float('nan')), ('elapsed_seconds', float('inf')),
])
def test_invalid_restored_counters_fail_closed(field,value):
    from mira.generation import GenerationBudget
    with pytest.raises(ValueError):
        GenerationBudget(600000,1500,initial_usage={field:value})


def test_restored_pending_call_becomes_unknown_and_failed_journal_blocks_continuation():
    from mira.generation import GenerationBudget
    old={'known_tokens':2,'unknown_reserved_tokens':3,'pending_tokens':10,'journal_available':False,
         'calls':[{'status':'pending','request_sent':None,'reservation_tokens':10,
                   'known_tokens':0,'unknown_reserved_tokens':0}]}
    b=GenerationBudget(600000,1500,initial_usage=old,on_change=lambda _:None)
    state=b.snapshot()
    assert state['unknown_reserved_tokens']==13 and state['pending_tokens']==0
    assert state['calls'][0]['status']=='failed' and state['calls'][0]['unknown_reserved_tokens']==10
    assert state['calls'][0]['request_sent'] is None
    with pytest.raises(LLMError):
        b.start('model','writer',1)


@pytest.mark.parametrize('kind', ['model','search','embedding'])
def test_journal_delay_refuses_dispatch_and_releases_reservations(kind):
    from mira.generation import GenerationClient, GenerationSearch, GenerationEmbedder
    from mira.hybrid import EmbeddingError
    now=[0.0]; calls=[]
    b=budget(clock=lambda:now[0],on_change=lambda _:now.__setitem__(0,1500.0 if kind=='model' else 1140.0))
    with pytest.raises((LLMError,EmbeddingError)):
        if kind=='model':
            invoke(GenerationClient(SimpleNamespace(structured_bounded=lambda **kw:calls.append(kw)),b))
        elif kind=='search':
            GenerationSearch(lambda *args:calls.append(args),b)('query',10,20)
        else:
            base=SimpleNamespace(identity=SimpleNamespace(model='embed'),embed=lambda *a,**kw:calls.append(kw))
            GenerationEmbedder(base,b).embed(['text'],timeout_seconds=20)
    state=b.snapshot()
    assert not calls and state['pending_tokens']==0
    assert state['spending']['pending_usd']=='0.000000'
    assert state['spending']['allowance_used_usd']=='0.000000'
    assert state['calls'][-1]['status']=='not_sent'


@pytest.mark.parametrize('kind', ['model','search'])
def test_dispatch_timeout_accounts_for_journal_delay(kind):
    from mira.generation import GenerationClient, GenerationSearch
    now=[0.0]; timeouts=[]
    b=budget(clock=lambda:now[0],on_change=lambda _:now.__setitem__(0,1495.0 if kind=='model' else 1135.0))
    if kind=='model':
        def run(**kw):
            timeouts.append(kw['timeout_seconds'])
            return SimpleNamespace(tokens_in=1,tokens_out=1,model='fixture')
        invoke(GenerationClient(SimpleNamespace(structured_bounded=run),b))
    else:
        def run(query,limit,timeout):
            timeouts.append(timeout); return []
        GenerationSearch(run,b)('query',10,20)
    assert timeouts==[5.0]
