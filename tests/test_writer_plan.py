from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

import pytest

from mira.agents import writer
from mira.llm import LLMOutputError, ScriptedClient


def saved(text, kind='external_fact', key_date=None):
    draft = SimpleNamespace(finding_type=kind, is_inference=False, jurisdiction_code='HK',
                            change_type=None, industry_category=None, key_date=key_date,
                            key_date_kind=None, priority=None, priority_reason=None,
                            evidence_confidence=None, evidence_confidence_reason=None,
                            title='Notice', content=text)
    return SimpleNamespace(finding_id=uuid4(), draft=draft)


def plan(**groups):
    return {'sections': [{'section': section, 'groups': groups.get(section, [])}
                         for section in writer.WRITER_SECTIONS]}


def run(client, claims):
    with patch.object(writer, 'brief_text', return_value='Brief'):
        return writer.write(client, object(), claims)


def test_compact_plan_renders_saved_text_and_falls_back_for_omitted_claims():
    long_text = 'Verified condition. ' * 500
    claims = [saved(long_text), saved('Second verified fact.')]
    client = ScriptedClient({'writer': [plan(executive_summary=[['C2']],
                                               regulatory_developments=[['C2']])]})
    result = run(client, claims)
    assert result.sections[0].sentences[0].text == 'Second verified fact.'
    assert [s.text for s in result.sections[1].sentences] == ['Second verified fact.', long_text]
    schema = str(client.calls[0].output_type.model_json_schema())
    assert 'text' not in schema and long_text not in schema


@pytest.mark.parametrize('bad', [
    plan(executive_summary=[['C999']]),
    plan(executive_summary=[[]]),
    {'sections': [{'section': 'executive_summary', 'groups': [['C1']], 'text': 'invented'}]},
])
def test_invalid_or_invented_plan_is_rejected(bad):
    client = ScriptedClient({'writer': [bad, bad]})
    with pytest.raises(LLMOutputError):
        run(client, [saved('Verified fact.')])


def test_plan_rejects_more_than_64_label_references():
    bad = plan(regulatory_developments=[['C1'] * 33, ['C1'] * 32])
    client = ScriptedClient({'writer': [bad, bad]})
    with pytest.raises(LLMOutputError, match='64 label references'):
        run(client, [saved('Verified fact.')])


def test_complete_plan_cannot_smuggle_prose_in_an_extra_field():
    bad=plan(executive_summary=[['C1']])
    bad['sections'][0]['text']='The bank must rebuild controls by 2027.'
    with pytest.raises(LLMOutputError):
        run(ScriptedClient({'writer':[bad,bad]}),[saved('Verified fact.')])


def test_eligibility_and_timeline_order_remain_code_enforced():
    from datetime import date
    claims = [saved('Later fact.', key_date=date(2027, 1, 1)),
              saved('Earlier fact.', key_date=date(2026, 1, 1))]
    client = ScriptedClient({'writer': [plan(impact_assessment=[['C1']],
        deadlines_timeline=[['C1'], ['C2']])]})
    result = run(client, claims)
    assert result.sections[6].no_verified_items
    assert [s.text for s in result.sections[2].sentences] == ['Earlier fact.', 'Later fact.']


def test_ordinary_injected_client_uses_the_plan_contract():
    from mira.llm import LLMResult

    class OrdinaryClient:
        def structured(self, *, role, system, user, output_type, prompt_version):
            return LLMResult(output_type.model_validate(plan(executive_summary=[['C1']])),
                             'ordinary', prompt_version, 1, 1)

    result = run(OrdinaryClient(), [saved('Verified fact.')])
    assert result.sections[0].sentences[0].text == 'Verified fact.'
