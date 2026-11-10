"""Validated first-party price quotes and cost calculations."""
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Mapping
from html.parser import HTMLParser
from datetime import datetime, timezone
import re
import urllib.request
import urllib.error
import subprocess
import sys
import os


class PricingError(ValueError):
    """A complete, unambiguous first-party price quote is unavailable."""


def _rate(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise PricingError('price must be a finite non-negative Decimal')


def _count(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PricingError('token or result count must be a non-negative integer')


@dataclass(frozen=True)
class TokenRate:
    provider: str
    model: str
    input_per_million: Decimal
    output_per_million: Decimal
    context_threshold: int | None = None
    high_input_multiplier: Decimal = Decimal(1)
    high_output_multiplier: Decimal = Decimal(1)

    def __post_init__(self) -> None:
        for value in (self.input_per_million, self.output_per_million,
                      self.high_input_multiplier, self.high_output_multiplier):
            _rate(value)
        if self.context_threshold is not None:
            _count(self.context_threshold)
            if self.context_threshold == 0:
                raise PricingError('context threshold must be positive')

    def cost(self, tokens_in: int, tokens_out: int) -> Decimal:
        _count(tokens_in)
        _count(tokens_out)
        high = self.context_threshold is not None and tokens_in >= self.context_threshold
        return (Decimal(tokens_in) * self.input_per_million * (self.high_input_multiplier if high else 1)
                + Decimal(tokens_out) * self.output_per_million * (self.high_output_multiplier if high else 1)) / Decimal(1000000)


@dataclass(frozen=True)
class PriceBook:
    rates: Mapping[str, TokenRate]
    exa_per_request: Decimal | None
    exa_additional_result: Decimal | None
    checked_at: str
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'rates', MappingProxyType(dict(self.rates)))
        for value in (self.exa_per_request, self.exa_additional_result):
            if value is not None:
                _rate(value)

    def token_rate(self, provider: str, model: str) -> TokenRate:
        try:
            return self.rates[f'{provider}:{model}']
        except KeyError as exc:
            raise PricingError('model has no validated quote') from exc

    def search_cost(self, result_limit: int) -> Decimal:
        _count(result_limit)
        if self.exa_per_request is None or self.exa_additional_result is None:
            raise PricingError('Exa search pricing is unavailable')
        return self.exa_per_request + max(0, result_limit - 10) * self.exa_additional_result

    def metadata(self) -> dict:
        return {'checked_at': self.checked_at, 'sources': self.sources}


EXA_URL = "https://exa.ai/pricing"


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.rows.append([])
        elif tag == 'tr':
            self.row = []
        elif tag in ('th', 'td') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('th', 'td') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def _money(value: str) -> Decimal:
    if not re.fullmatch(r'\$[0-9]+(?:\.[0-9]+)?', value):
        raise PricingError('invalid quoted price')
    result = Decimal(value[1:])
    _rate(result)
    return result


def _exa(text: str) -> tuple[Decimal, Decimal]:
    parser = _TableParser()
    parser.feed(text)
    matches = []
    for i, row in enumerate(parser.rows):
        if row.count('Auto Search') != 1 or 'Lite Search' not in row or 'Deep Search' not in row:
            continue
        col = row.index('Auto Search')
        candidates = []
        for candidate in parser.rows[i + 1:i + 4]:
            if not candidate:
                break
            candidates.append(candidate)
        base = [r for r in candidates if r and re.fullmatch(r'Base price, with up to 10 results ?\(per 1k requests\)', r[0])]
        extra = [r for r in candidates if r and re.fullmatch(r'Cost per additional result above 10 ?\(per 1k requests\)', r[0])]
        if len(base) == len(extra) == 1 and len(base[0]) > col and len(extra[0]) > col:
            matches.append((_money(base[0][col]) / 1000, _money(extra[0][col]) / 1000))
    if len(matches) != 1:
        raise PricingError('Exa Auto Search quote is missing or ambiguous')
    return matches[0]


OPENAI_URL = 'https://developers.openai.com/api/docs/pricing.md'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PricingError('pricing redirect rejected')


_FETCH_DEADLINE_SECONDS = 10.0
# Isolate network I/O so the total deadline can terminate even a slow DNS,
# header, or body stream. The parent enforces the only allowed destinations.
_FETCH_WORKER = r"""
import sys
import urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('pricing redirect rejected')

opener = urllib.request.build_opener(NoRedirect())
request = urllib.request.Request(sys.argv[1], headers={'User-Agent': 'Mira pricing quote'})
with opener.open(request, timeout=10) as response:
    body = response.read(2_000_001)
if len(body) > 2_000_000:
    raise ValueError('pricing response too large')
sys.stdout.buffer.write(body)
"""


def _fetch(url: str) -> str:
    if url not in (OPENAI_URL, EXA_URL):
        raise PricingError('unapproved pricing URL')
    try:
        result = subprocess.run(
            [sys.executable, '-I', '-c', _FETCH_WORKER, url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=_FETCH_DEADLINE_SECONDS, check=True,
            env={'PATH': os.environ.get('PATH', '')},
        )
        if len(result.stdout) > 2_000_000:
            raise PricingError('pricing response too large')
        return result.stdout.decode('utf-8')
    except PricingError:
        raise
    except (subprocess.SubprocessError, OSError, UnicodeError) as exc:
        raise PricingError('pricing page unavailable or deadline exceeded') from exc


def _rows(text: str) -> list[list[str]]:
    return [[c.strip() for c in line.strip().strip('|').split('|')]
            for line in text.splitlines() if line.strip().startswith('|')]


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = text.splitlines()
    tables = []
    i = 0
    def cells(line):
        return [c.strip() for c in line.strip().strip('|').split('|')]
    def separator(line):
        if not line.strip().startswith('|'):
            return False
        parts = cells(line)
        return bool(parts) and all(re.fullmatch(r':?-{3,}:?', part) for part in parts)
    while i + 1 < len(lines):
        if not lines[i].strip().startswith('|') or not separator(lines[i + 1]):
            i += 1
            continue
        header = cells(lines[i])
        i += 2
        rows = []
        while i < len(lines) and lines[i].strip().startswith('|'):
            if i + 1 < len(lines) and separator(lines[i + 1]):
                break
            rows.append(cells(lines[i]))
            i += 1
        tables.append((header, rows))
    return tables


def _openai(text: str, models: set[str]) -> dict[str, TokenRate]:
    if text.count('### Standard pricing data') != 1:
        raise PricingError('standard pricing section missing or ambiguous')
    before, rest = text.split('### Standard pricing data')
    if not re.search(r'Prices per 1M tokens\.\s+Standard\s*$', before):
        raise PricingError('standard token pricing units missing')
    standard = re.split(r'(?m)^\s*#{1,3}\s+', rest, maxsplit=1)[0]
    tables = _tables(standard)
    found = {}
    for model in models - {'text-embedding-3-small'}:
        if model == 'gpt-5.4':
            header = ['Model', 'Short context input', 'Short context output', 'Short context cached input', 'Short context 30m write', 'Short context 12h write', 'Long context input', 'Long context output', 'Long context cached input', 'Long context 30m write', 'Long context 12h write']
            candidates = [r for h, rows in tables if h == header for r in rows if r and r[0] == 'gpt-5.4 (<272K context length)']
            if len(candidates) != 1 or len(candidates[0]) != 11:
                raise PricingError('ambiguous GPT-5.4 context quote')
            row = candidates[0]
            low_in, low_out, high_in, high_out = map(_money, (row[1], row[2], row[6], row[7]))
            if not low_in or not low_out:
                raise PricingError('cannot derive context multipliers')
            found[model] = TokenRate('openai', model, low_in, low_out, 272000, high_in / low_in, high_out / low_out)
        elif model == 'gpt-5.4-mini':
            candidates = [r for h, rows in tables if h == ['Model', 'Input', 'Output', 'Cached input'] for r in rows if r and r[0] == model]
            if len(candidates) != 1 or len(candidates[0]) != 4:
                raise PricingError('ambiguous mini quote')
            found[model] = TokenRate('openai', model, _money(candidates[0][1]), _money(candidates[0][2]))
        else:
            raise PricingError('unknown model')
    if 'text-embedding-3-small' in models:
        header = '| Category | Model | Input | Output | Cached input | 30m write | 12h write |'
        sections = []
        for match in re.finditer(re.escape(header), text):
            prefix = text[max(0, match.start()-300):match.start()]
            if not re.search(r'Prices per 1M tokens\.\s+Standard\s+### Grouped Pricing Table data\s*$', prefix):
                continue
            section = re.split(r'(?m)^\s*#{1,3}\s+', text[match.start():], maxsplit=1)[0]
            tables = _tables(section)
            expected = ['Category', 'Model', 'Input', 'Output', 'Cached input', '30m write', '12h write']
            candidates = [r for h, rows in tables if h == expected for r in rows if len(r) == 7 and r[:2] == ['Embedding', 'text-embedding-3-small'] and r[3:] == ['-', '-', '-', '-']]
            sections.extend(candidates)
        if len(sections) != 1:
            raise PricingError('embedding quote missing or ambiguous')
        found['text-embedding-3-small'] = TokenRate('openai', 'text-embedding-3-small', _money(sections[0][2]), Decimal(0))
    return found


def load_price_book(models: Mapping[str, str], *, embedding_model: str | None = None,
                    exa_enabled: bool = False,
                    fetch_text: Callable[[str], str] | None = None) -> PriceBook:
    required = set()
    for value in models.values():
        if value not in ('openai:gpt-5.4', 'openai:gpt-5.4-mini'):
            raise PricingError('unknown provider or model')
        required.add(value.split(':', 1)[1])
    if embedding_model is not None:
        if embedding_model != 'text-embedding-3-small':
            raise PricingError('unknown embedding model')
        required.add(embedding_model)
    fetch = fetch_text or _fetch
    rates = {}
    sources = []
    try:
        if required:
            rates = {'openai:' + model: rate for model, rate in _openai(fetch(OPENAI_URL), required).items()}
            sources.append(OPENAI_URL)
        base = extra = None
        if exa_enabled:
            base, extra = _exa(fetch(EXA_URL))
            sources.append(EXA_URL)
    except PricingError:
        raise
    except Exception as exc:
        raise PricingError('pricing quote unavailable') from exc
    return PriceBook(rates, base, extra, datetime.now(timezone.utc).isoformat(), tuple(sources))
