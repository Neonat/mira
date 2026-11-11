"""Conservative, local guards on new evidence; never infer dates from containers.

The vocabulary check is deliberately an abstention gate, not an entailment test.
Semantic verification still decides whether an eligible assessment follows.
"""
from __future__ import annotations

from datetime import date
import re

from mira.contracts import Contract, InferenceCheckDraft, InferencePremise


class Premise(Contract):
    claim_label: str
    passage_label: str
    supporting_quote: str


class GroundedInferenceDraft(InferenceCheckDraft):
    premises: list[Premise]
    preserves_qualifications: bool
    is_substantive: bool


# Exact generic category titles only. A specific circular/guideline title is not
# an index merely because it contains one of these words. Both category orders
# are accepted; no publisher, URL, finding ID or benchmark answer is involved.
_LEGACY_CATEGORY_TITLES = frozenset({
    'circulars and guidance papers', 'guidance papers and circulars',
    'ordinances and statutory guidelines', 'statutory guidelines and ordinances',
    'publications index', 'index of publications',
    'circulars and guidelines', 'guidelines and circulars',
})


def grounding(passage) -> dict:
    value = passage.acquisition_provenance.get('claim_grounding')
    if isinstance(value, dict) and value:
        return value
    # Derive a prompt/check precondition from immutable saved text only. Do not
    # retrofit metadata or add this result to historical frozen JSON.
    title = re.sub(r'\s*\(archive\)\s*$', '', passage.title.strip(), flags=re.I)
    title = ' '.join(re.sub(r'[&/]', ' and ', title.lower()).split()).strip(' .:')
    if title in _LEGACY_CATEGORY_TITLES:
        return {'role': 'listing', 'date_scope': 'container',
                'date_basis': 'derived from saved generic category title; not an item publication date'}
    return {}


def substantive_evidence(passages) -> bool:
    return bool(passages) and any(grounding(p).get('role') not in ('listing', 'maintenance') for p in passages)


def date_in_text(value: date, text: str) -> bool:
    variants = {value.isoformat(), value.strftime('%d %B %Y'), value.strftime('%d %b %Y'),
                f'{value.day} {value:%B %Y}', f'{value.day} {value:%b %Y}',
                f'{value:%B} {value.day}, {value.year}', f'{value:%b} {value.day}, {value.year}'}
    clean = ' '.join(text.lower().split())
    return any(re.search(r'(?<!\w)' + re.escape(v.lower()) + r'(?!\w)', clean) for v in variants)


def operative_date_in_text(value: date, kind: str | None, text: str) -> bool:
    cues = {
        'effective': r'\b(effective|effect|force|commenc(?:e|es|ement))\b',
        'deadline': r'\b(deadline|by|before|due|no later than)\b',
        'consultation_close': r'\b(close|closes|closing|deadline|by|before)\b',
    }
    if kind not in cues:
        return date_in_text(value, text)
    # Require the date and kind cue in the same local source statement.
    return any(date_in_text(value, part) and re.search(cues[kind],part,re.I)
               for part in re.split(r'[.\n;]', text))


def check_date_grounding(claim, brief, passages) -> None:
    """New captures opt in; historical inputs keep their existing interpretation."""
    if claim.is_inference or not any(grounding(p) for p in passages):
        return
    eligible = [p for p in passages if grounding(p).get('role') not in ('listing', 'maintenance')]
    if not eligible:
        raise ValueError('listing/container evidence cannot establish a substantive development')
    text = f'{claim.title} {claim.content}'
    recent = claim.change_type in ('new', 'amended') or bool(re.search(
        r'\b(newly|recent|recently)\b|during the (?:research )?period|within the period', text, re.I))
    operative = [p for p in eligible if grounding(p).get('date_scope') == 'publication']
    if claim.key_date is not None:
        # Effective/event/deadline dates must actually occur in the retained source.
        bound = any(operative_date_in_text(claim.key_date, claim.key_date_kind, p.content) for p in eligible)
        if claim.key_date_kind == 'published':
            bound = bound or any(p.published_at == claim.key_date for p in operative)
        if not bound:
            raise ValueError('date_basis_missing: claimed date is not bound to operative evidence')
    if recent:
        # Finding-date evidence must establish recency, not merely contain a date.
        # In particular, a historical effective/deadline date cannot become current
        # because an unrelated companion publication has a newer metadata date.
        if claim.key_date is not None and not brief.period_start <= claim.key_date <= brief.period_end:
            raise ValueError('operative_date_out_of_period: date does not establish recency')
        explicit = claim.key_date is not None and any(
            operative_date_in_text(claim.key_date, claim.key_date_kind, p.content) for p in eligible
        )
        # Without an explicit operative binding, mixed old/unknown/current source
        # dates are ambiguous. Require narrowing or a source-bound current date.
        dated = bool(eligible) and all(
            grounding(p).get('date_scope') == 'publication'
            and p.published_at is not None
            and brief.period_start <= p.published_at <= brief.period_end
            for p in eligible
        )
        if not dated and not explicit:
            raise ValueError('date_basis_missing: unknown/container or mixed dates do not establish recency')


# These words express assessment/grammar, not external descriptive premises.
# Unsupported domain vocabulary causes abstention rather than a guessed expansion.
_ASSESSMENT = frozenset('''a an the and or of in on to for from by with without as at that this these those
it its their they is are was were be been being have has had do does can could may might would
suggest suggests suggestive indicate indicates imply implies implication implications assessment
risk risks opportunity opportunities potentially potential increase increases increased increasing
reduce reduces reduced reducing higher lower greater heightened possible possibility uncertainty
attention exposure relevant relevance operational supervisory interpretation interpretations
relying reliance stale outdated interpretation expectations concern concerns raises raise
across alongside combination combined together therefore thus also while but however'''.split())


def words(text: str) -> set[str]:
    return set(re.findall(r'[a-z]+|\d+(?:[.,]\d+)*',text.lower()))


def inference_grounding_error(claim, facts, passages, draft: GroundedInferenceDraft) -> str | None:
    error, _ = check_inference_grounding(claim, facts, passages, draft)
    return error


def check_inference_grounding(
    claim, facts, passages, draft: GroundedInferenceDraft,
) -> tuple[str | None, tuple[InferencePremise, ...]]:
    """Return the grounding decision and the exact, resolved premises from the check."""
    qualification_error = (
        None if draft.preserves_qualifications and draft.is_substantive
        else 'qualification_lost or topic_relevance_unestablished'
    )
    if not draft.premises:
        return qualification_error or 'premise_evidence_missing', ()
    fact_map = {f'F{i}': f for i,f in enumerate(facts,1)}
    passage_map = {f'P{i}': p for i,p in enumerate(passages,1)}
    premises = []
    contexts = []
    for premise in draft.premises:
        fact, passage = fact_map.get(premise.claim_label), passage_map.get(premise.passage_label)
        if fact is None or passage is None or fact.finding_id not in claim.depends_on:
            return qualification_error or 'invalid_premise_reference', ()
        if passage.id not in {e.passage_id for e in fact.evidence}:
            return qualification_error or 'premise_not_dependency_evidence', ()
        quote=premise.supporting_quote.strip()
        if not quote or quote not in passage.content:
            return qualification_error or 'premise_quote_not_found', ()
        if grounding(passage).get('role') in ('listing','maintenance'):
            return qualification_error or 'listing_only_premise', ()
        premises.append(InferencePremise(
            dependency_finding_id=fact.finding_id, passage_id=passage.id, supporting_quote=quote,
        ))
        # A model cannot evade negation/modality by quoting only a substring.
        # Inspect all enclosing statements when a quotation occurs repeatedly.
        for match in re.finditer(re.escape(quote), passage.content):
            start, end = match.span()
            left = max(passage.content.rfind(mark, 0, start) for mark in ('.', '\n', ';')) + 1
            stops = [pos for mark in ('.', '\n', ';') if (pos := passage.content.find(mark, end)) >= 0]
            right = min(stops) if stops else len(passage.content)
            contexts.append(passage.content[left:right])
    mappings = tuple(premises)
    if qualification_error:
        return qualification_error, mappings
    source=' '.join(premise.supporting_quote for premise in mappings)
    target=f'{claim.draft.title} {claim.draft.content}'
    missing=words(target)-words(source)-_ASSESSMENT
    if missing:
        return 'unsupported_descriptive_premise: ' + ', '.join(sorted(missing)[:12]), mappings
    # Even matching vocabulary cannot remove a material source qualification.
    qualified_source = ' '.join(contexts)
    for qualifier in ('may','might','could','proposed','some','not','unless','except'):
        if qualifier in words(qualified_source) and qualifier not in words(target):
            return 'qualification_lost: ' + qualifier, mappings
    if 'according to' in qualified_source.lower() and 'according to' not in target.lower():
        return 'qualification_lost: attribution', mappings
    if claim.draft.key_date is not None:
        if not any(f.draft.key_date == claim.draft.key_date and f.draft.key_date_kind == claim.draft.key_date_kind for f in facts):
            return 'unsupported_inference_date', mappings
    return None, mappings
