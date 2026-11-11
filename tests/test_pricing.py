from decimal import Decimal

import pytest

from mira.pricing import PricingError, TokenRate, load_price_book


OPENAI = '''# Pricing
Prices per 1M tokens.
Standard
### Standard pricing data
| Model | Short context input | Short context output | Short context cached input | Short context 30m write | Short context 12h write | Long context input | Long context output | Long context cached input | Long context 30m write | Long context 12h write |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.4 (<272K context length) | $2.00 | $10.00 | $0.20 | - | - | $4.00 | $15.00 | - | - | - |
| Model | Input | Output | Cached input |
| --- | --- | --- | --- |
| gpt-5.4-mini | $0.50 | $3.00 | $0.05 |

Prices per 1M tokens.
Standard
### Grouped Pricing Table data
| Category | Model | Input | Output | Cached input | 30m write | 12h write |
| --- | --- | --- | --- | --- | --- | --- |
| Embedding | text-embedding-3-small | $0.03 | - | - | - | - |
## Batch
| Model | Input | Output |
| --- | --- | --- |
| gpt-5.4-mini | $0.25 | $1.50 |
'''


def test_standard_input_output_tier_embedding_and_metadata():
    book = load_price_book({'a': 'openai:gpt-5.4', 'b': 'openai:gpt-5.4-mini'}, embedding_model='text-embedding-3-small', fetch_text=lambda _: OPENAI)
    rate = book.token_rate('openai', 'gpt-5.4')
    assert rate.cost(100, 50) == Decimal('0.0007')
    assert rate.cost(272001, 100) == (Decimal(272001)*4 + Decimal(100)*15)/1000000
    assert book.token_rate('openai', 'text-embedding-3-small').cost(1000000, 0) == Decimal('0.03')
    assert set(book.metadata()) == {'checked_at', 'sources'}
    assert '2.00' not in str(book.metadata())


def test_unknown_model_rejected():
    with pytest.raises(PricingError):
        load_price_book({'a': 'openai:gpt-5.4-made-up'}, fetch_text=lambda _: OPENAI)


@pytest.mark.parametrize('bad', ['NaN', '-1', 'Infinity'])
def test_invalid_rate_rejected(bad):
    with pytest.raises(PricingError):
        TokenRate('x', 'y', Decimal(bad), Decimal(1))


def test_missing_units_rejected():
    with pytest.raises(PricingError):
        load_price_book({'a': 'openai:gpt-5.4-mini'}, fetch_text=lambda _: OPENAI.replace('Prices per 1M tokens.', 'Prices'))


def test_exa_missing_or_ambiguous_prices_rejected():
    with pytest.raises(PricingError):
        load_price_book({}, exa_enabled=True, fetch_text=lambda _: 'Search $5')


def test_negative_token_counts_rejected():
    with pytest.raises(PricingError):
        TokenRate('x', 'y', Decimal(1), Decimal(2)).cost(-1, 1)


def test_exa_auto_search_extra_results():
    from mira.pricing import PriceBook
    book = PriceBook({}, Decimal('0.007'), Decimal('0.001'), 'now', ())
    assert book.search_cost(10) == Decimal('0.007')
    assert book.search_cost(13) == Decimal('0.010')


def test_exa_quote_uses_auto_column_and_thousand_request_units():
    exa = '''<h2>Endpoint pricing</h2><table><tr><th>Endpoint</th><th>Lite Search</th><th>Auto Search</th><th>Deep Search</th></tr><tr><td>Base price, with up to 10 results (per 1k requests)</td><td>$2</td><td>$6</td><td>$9</td></tr><tr><td>Cost per additional result above 10 (per 1k requests)</td><td>$1</td><td>$2</td><td>$3</td></tr></table>'''
    book = load_price_book({}, exa_enabled=True, fetch_text=lambda _: exa)
    assert book.search_cost(12) == Decimal('0.010')


def test_long_context_boundary_and_separate_rates():
    book = load_price_book({'a': 'openai:gpt-5.4'}, fetch_text=lambda _: OPENAI)
    rate = book.token_rate('openai', 'gpt-5.4')
    assert rate.cost(272000, 1) == (Decimal(272000) * 4 + 15) / 1000000
    assert rate.cost(271999, 1) == (Decimal(271999) * 2 + 10) / 1000000


@pytest.mark.parametrize('replacement', ['-', '$-1', '$NaN', '$Infinity'])
def test_malformed_source_price_fails_closed(replacement):
    with pytest.raises(PricingError):
        load_price_book({'a': 'openai:gpt-5.4-mini'}, fetch_text=lambda _: OPENAI.replace('$0.50', replacement))


def test_duplicate_standard_rows_fail_closed():
    line = '| gpt-5.4-mini | $0.50 | $3.00 | $0.05 |'
    with pytest.raises(PricingError):
        load_price_book({'a': 'openai:gpt-5.4-mini'}, fetch_text=lambda _: OPENAI.replace(line, line + '\n' + line))


def test_transport_rejects_arbitrary_urls_and_redirects():
    from mira.pricing import _fetch, _NoRedirect
    with pytest.raises(PricingError):
        _fetch('http://127.0.0.1/')
    with pytest.raises(PricingError):
        _NoRedirect().redirect_request(None, None, None, None, None, 'https://example.com')


def test_standard_model_cannot_be_taken_from_batch_section():
    line = '| gpt-5.4-mini | $0.50 | $3.00 | $0.05 |'
    text = OPENAI.split('Prices per 1M tokens.\nStandard\n### Grouped')[0].replace(line, '') + '\n## Batch\n' + line + '\n'
    with pytest.raises(PricingError):
        load_price_book({'a': 'openai:gpt-5.4-mini'}, fetch_text=lambda _: text)


def test_model_row_must_belong_to_matching_header_table():
    line = '| gpt-5.4-mini | $0.50 | $3.00 | $0.05 |'
    text = OPENAI.replace(line, '| Model | Other | Output | Cached input |\n| --- | --- | --- | --- |\n' + line)
    with pytest.raises(PricingError):
        load_price_book({'a': 'openai:gpt-5.4-mini'}, fetch_text=lambda _: text)


def test_fetch_slow_drip_has_total_deadline(monkeypatch):
    import time
    import mira.pricing as pricing

    # A child which emits bytes forever exercises the real timeout and kill path
    # without opening a network connection.
    monkeypatch.setattr(pricing, '_FETCH_WORKER',
                        "import sys,time\nwhile True:\n sys.stdout.write('x'); sys.stdout.flush(); time.sleep(.01)", raising=False)
    monkeypatch.setattr(pricing, '_FETCH_DEADLINE_SECONDS', 0.1, raising=False)
    started = time.monotonic()
    with pytest.raises(PricingError):
        pricing._fetch(pricing.OPENAI_URL)
    assert time.monotonic() - started < 1


def test_exa_rows_cannot_cross_html_tables():
    exa = '''<table><tr><th>Endpoint</th><th>Lite Search</th><th>Auto Search</th><th>Deep Search</th></tr><tr><td>Base price, with up to 10 results (per 1k requests)</td><td>$2</td><td>$6</td><td>$9</td></tr></table><table><tr><td>Cost per additional result above 10 (per 1k requests)</td><td>$1</td><td>$2</td><td>$3</td></tr></table>'''
    with pytest.raises(PricingError):
        load_price_book({}, exa_enabled=True, fetch_text=lambda _: exa)


def test_fetch_worker_receives_no_secret_environment(monkeypatch):
    import subprocess
    import mira.pricing as pricing
    seen = {}
    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, b'ok')
    monkeypatch.setenv('MIRA_TEST_SECRET', 'do-not-pass')
    monkeypatch.setattr(pricing.subprocess, 'run', fake_run)
    assert pricing._fetch(pricing.EXA_URL) == 'ok'
    assert set(seen['env']) <= {'PATH'}
    assert seen['timeout'] == pricing._FETCH_DEADLINE_SECONDS
