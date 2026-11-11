import pytest


def test_run_controls_roundtrip_without_credential_values():
    from mira.research_settings import ResearchSettings
    value={'source_ids':['00000000-0000-0000-0000-000000000001'],'enable_exa':True,
        'enable_browser':False,'retrieval':'hybrid','max_analysis_batches':24,
        'credential_mode':'byok','credential_handle':'x'*43}
    settings=ResearchSettings.from_dict(value)
    assert settings.as_dict()==value and settings.source_ids==tuple(value['source_ids'])


@pytest.mark.parametrize('value',[
    {'api_key':'do-not-save-this-key'}, {'source_ids':[]}, {'source_ids':['https://unapproved.example']},
    {'source_ids':['00000000-0000-0000-0000-000000000001']*2},
    {'enable_exa':'yes'}, {'enable_browser':1}, {'retrieval':'vector-only'},
    {'max_analysis_batches':True},{'max_analysis_batches':0},{'max_analysis_batches':65},
    {'credential_mode':'fallback-to-server'},{'credential_mode':'byok','credential_handle':'bad'},
    {'credential_mode':'operator','credential_handle':'x'*43},
])
def test_invalid_or_secret_bearing_controls_are_rejected(value):
    from mira.research_settings import ResearchSettings
    with pytest.raises(ValueError) as error:ResearchSettings.from_dict(value)
    assert 'do-not-save-this-key' not in str(error.value)


def test_defaults_are_immutable_and_pending_byok_handle_is_allowed():
    from mira.research_settings import ResearchSettings
    settings=ResearchSettings.from_dict({'credential_mode':'byok'})
    assert settings.credential_handle is None and settings.retrieval=='keyword'
    assert settings.max_analysis_batches==8
    result=settings.as_dict();result['max_analysis_batches']=60
    assert settings.max_analysis_batches==8
