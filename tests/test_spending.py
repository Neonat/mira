from decimal import Decimal as D
import threading
import pytest


def book():
    from mira.pricing import PriceBook,TokenRate
    return PriceBook({'openai:fixture':TokenRate('openai','fixture',D('1'),D('2')),
        'openai:embed':TokenRate('openai','embed',D('1'),D(0))},D('.01'),D('.002'),'2026-11-10T00:00:00Z',('https://official.example/pricing',))


def test_model_reservation_settles_separate_measured_input_and_output_cost():
    from mira.spending import SpendingLedger
    ledger=SpendingLedger(D('1'),book())
    ticket=ledger.reserve_model('writer','openai','fixture',100000,10000)
    assert ledger.snapshot()['pending_usd']=='0.120000'
    ledger.settle(ticket,tokens_in=1000,tokens_out=2000)
    state=ledger.snapshot()
    assert state['known_estimated_usd']=='0.005000' and state['pending_usd']=='0.000000'
    assert 'input_per_million' not in str(state) and 'output_per_million' not in str(state)


def test_unknown_sent_usage_keeps_money_but_local_refusal_costs_zero():
    from mira.spending import SpendingLedger
    ledger=SpendingLedger(D('1'),book())
    unknown=ledger.reserve_model('writer','openai','fixture',100000,10000)
    ledger.settle(unknown,request_sent=True)
    local=ledger.reserve_model('writer','openai','fixture',100000,10000)
    ledger.settle(local,request_sent=False)
    assert ledger.snapshot()['unknown_reserved_usd']=='0.120000'
    assert ledger.snapshot()['allowance_used_usd']=='0.120000'


def test_embedding_and_search_reserve_from_the_same_money_allowance():
    from mira.spending import SpendingLedger,SpendingError
    ledger=SpendingLedger(D('.05'),book())
    search=ledger.reserve_search(15);ledger.settle(search,tokens_in=0,tokens_out=0)
    embed=ledger.reserve_embedding('openai','embed',20000)
    ledger.settle(embed,tokens_in=10000,tokens_out=0)
    assert ledger.snapshot()['known_estimated_usd']=='0.030000'
    with pytest.raises(SpendingError):ledger.reserve_model('writer','openai','fixture',30000,0)


def test_concurrent_requests_cannot_exceed_pending_money_limit():
    from mira.spending import SpendingLedger,SpendingError
    ledger=SpendingLedger(D('.10'),book());results=[]
    def reserve():
        try:results.append(ledger.reserve_model('writer','openai','fixture',20000,0))
        except SpendingError:results.append(None)
    threads=[threading.Thread(target=reserve) for _ in range(10)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert len([r for r in results if r is not None])==5
    assert ledger.snapshot()['pending_usd']=='0.100000'


def test_unpriced_model_fails_before_reserving_or_dispatching():
    from mira.spending import SpendingLedger,SpendingError
    ledger=SpendingLedger(D('1'),book())
    with pytest.raises(SpendingError):ledger.reserve_model('writer','openai','unpriced',100,100)
    assert ledger.snapshot()['allowance_used_usd']=='0.000000'


def test_restored_usage_and_pending_uncertainty_do_not_renew_allowance():
    from mira.spending import SpendingLedger,SpendingError
    ledger=SpendingLedger(D('1'),book(),known_usd=D('.5'),unknown_usd=D('.4'))
    with pytest.raises(SpendingError):ledger.reserve_model('writer','openai','fixture',200000,0)
    assert ledger.snapshot()['allowance_used_usd']=='0.900000'


def test_nonwriter_preserves_downstream_money_and_tickets_settle_once():
    from mira.spending import SpendingLedger,SpendingError
    ledger=SpendingLedger(D('1'),book())
    with pytest.raises(SpendingError):ledger.reserve_model('planner','openai','fixture',900000,0)
    ticket=ledger.reserve_model('writer','openai','fixture',900000,0)
    ledger.settle(ticket,request_sent=False)
    with pytest.raises(SpendingError):ledger.settle(ticket,request_sent=False)


@pytest.mark.parametrize('amount',['0','-1','NaN','Infinity','1001'])
def test_money_budget_rejects_invalid_allowances(amount):
    from mira.budget import RunBudget
    with pytest.raises(ValueError):RunBudget(max_cost_usd=amount)


def test_budget_pins_usd_without_persisting_any_provider_prices():
    from mira.budget import RunBudget
    assert RunBudget(max_cost_usd='5.00').as_source_limits()['max_cost_usd']=='5.00'
    assert 'max_cost_usd' not in RunBudget().as_source_limits()


def test_submicro_allowance_is_not_rounded_up():
    from mira.spending import SpendingLedger, SpendingError
    ledger = SpendingLedger(D('.0000001'), book())
    assert D(ledger.snapshot()['max_usd']) == D('.0000001')
    with pytest.raises(SpendingError):
        ledger.reserve_model('writer', 'openai', 'fixture', 1, 0)
