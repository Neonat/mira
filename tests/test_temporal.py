from datetime import date
from uuid import uuid4

import pytest

from mira.agents.analyst import analyse, rewrite
from mira.agents.temporal import check_claim_period
from mira.contracts import Brief, ClaimDraft
from mira.llm import LLMOutputError, ScriptedClient
from mira.store import PassageRecord, ClaimEvidence, StoredClaim

BRIEF = Brief(topic='AML/CFT', jurisdictions=['SG'], period_start=date(2025,10,26),
              period_end=date(2026,10,26), as_of_date=date(2026,11,6), plan_requires_approval=False)


def passage(published):
    return PassageRecord(uuid4(),uuid4(),uuid4(),uuid4(),'DBS','SG','AI in banking',
                         'https://www.dbs.com/example',published,1,'Flagged cases are reviewed by human analysts.',True)


def claim(**updates):
    values=dict(claim_label='C1',finding_type='external_fact',title='Human review',
                content='DBS introduced human review.',jurisdiction_code='SG',change_type='new',
                industry_category=None,key_date=None,key_date_kind=None,is_inference=False,
                citations=[dict(passage_label='P1',supporting_quote='reviewed by human analysts')],depends_on=[],
                priority='medium',priority_reason=None,evidence_confidence='high',evidence_confidence_reason=None)
    return ClaimDraft(**(values | updates))


@pytest.mark.parametrize('published', [date(2023,4,18), date(2026,10,27)])
def test_old_and_post_period_evidence_cannot_be_relabelled_current(published):
    for draft in (claim(),claim(key_date=date(2026,5,1),key_date_kind='published')):
        with pytest.raises(ValueError,match='out-of-period'):
            check_claim_period(draft,BRIEF,[passage(published)])


@pytest.mark.parametrize('published', [BRIEF.period_start, BRIEF.period_end, None])
def test_boundaries_and_unknown_publication_dates_remain_eligible(published):
    check_claim_period(claim(),BRIEF,[passage(published)])


def test_future_publication_is_rejected_even_with_current_evidence():
    with pytest.raises(ValueError,match='as-of'):
        check_claim_period(claim(),BRIEF,[passage(BRIEF.period_start),passage(date(2026,11,7))])


@pytest.mark.parametrize('kind',['published','event'])
def test_claims_explicitly_dated_outside_period_are_rejected(kind):
    with pytest.raises(ValueError,match='outside the research period'):
        check_claim_period(claim(key_date=date(2023,4,18),key_date_kind=kind),BRIEF,[passage(None)])


@pytest.mark.parametrize('key_date,change',[(date(2026,6,1),'new'),(date(2027,1,1),'upcoming')])
def test_old_rules_can_support_current_or_upcoming_deadlines(key_date,change):
    check_claim_period(claim(key_date=key_date,key_date_kind='deadline',change_type=change),
                       BRIEF,[passage(date(2023,4,18))])


def test_analyst_retries_and_drops_historical_only_development():
    client=ScriptedClient({'analyst':[{'claims':[claim()]},{'claims':[]}]})
    result=analyse(client,BRIEF,[passage(date(2023,4,18))])
    assert result.claims==[]
    assert 'out-of-period' in client.calls[1].user
    assert result.llm.tokens_in==200


def test_analyst_cannot_keep_historical_claim_after_retry():
    client=ScriptedClient({'analyst':[{'claims':[claim()]},{'claims':[claim()]}]})
    with pytest.raises(LLMOutputError,match='out-of-period'):
        analyse(client,BRIEF,[passage(date(2023,4,18))])


def test_rewrite_cannot_reintroduce_historical_development():
    p = passage(date(2023,4,18))
    original = claim(key_date=date(2026,6,1),key_date_kind='deadline')
    stored = StoredClaim(uuid4(), original, (ClaimEvidence(p.id, 'reviewed by human analysts'),), ())
    client = ScriptedClient({'analyst':[claim(),claim()]})
    with pytest.raises(LLMOutputError,match='out-of-period'):
        rewrite(client,BRIEF,stored,[p],'Narrow the claim')


def test_cybersecurity_retrospective_requires_the_observation_year_in_the_quote():
    from dataclasses import replace

    cyber = Brief(topic="Cybersecurity", jurisdictions=["AE"], period_start=date(2023, 1, 1),
                  period_end=date(2025, 12, 31), as_of_date=date(2026, 11, 11), plan_requires_approval=False)
    text = "In 2025, financial institutions reported phishing campaigns."
    evidence = [replace(passage(date(2026, 8, 17)), content=text, jurisdiction_code="AE")]
    draft = claim(content=text, jurisdiction_code="AE", change_type=None,
                  citations=[dict(passage_label="P1", supporting_quote=text)])
    check_claim_period(draft, cyber, evidence)
    with pytest.raises(ValueError, match="out-of-period"):
        check_claim_period(draft.model_copy(update={"content": text.replace("2025", "2024")}), cyber, evidence)
    with pytest.raises(ValueError, match="out-of-period"):
        check_claim_period(draft, cyber.model_copy(update={"topic": "AML/CFT"}), evidence)
    with pytest.raises(ValueError, match="out-of-period"):
        check_claim_period(draft, cyber.model_copy(update={"period_end": date(2025, 6, 30)}), evidence)
