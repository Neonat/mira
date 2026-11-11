from datetime import date
import json
from uuid import uuid4

import pytest

from mira.brief import check_brief_scope
from mira.contracts import Brief
from mira.extract import extract
from mira.fetch import AllowList, FetchedPage, FetchRefused
from mira.seed import SOURCES
from mira.store import SourceRecord


def test_new_briefs_offer_only_approved_new_jurisdictions():
    for code in ('AU', 'AE'):
        check_brief_scope(Brief(topic='AML/CFT', jurisdictions=[code], period_start=date(2025,11,10),
                               period_end=date(2026,11,10), as_of_date=date(2026,11,10), plan_requires_approval=False))
    for code in ('MY', 'DF'):
        with pytest.raises(ValueError, match='not offered'):
            check_brief_scope(Brief(topic='AML/CFT', jurisdictions=[code], period_start=date(2025,11,10),
                                   period_end=date(2026,11,10), as_of_date=date(2026,11,10), plan_requires_approval=False))


def test_source_profiles_are_direct_and_permission_scoped():
    seeds={s.key:s for s in SOURCES}
    assert seeds['mas'].is_active is False
    au=seeds['au-register']; ae=seeds['cbuae']
    assert au.jurisdiction=='AU' and ae.jurisdiction=='AE'
    assert au.connector_config()['acquisition_profile']=='register_api_files'
    assert ae.connector_config()['acquisition_profile']=='federal_hub_pdf'
    assert 'embed' in au.operations and 'embed' not in ae.operations
    assert 'store_text' in ae.operations and 'quote' in ae.operations
    assert au.connector_config()['allow_live_browser'] is False
    assert ae.connector_config()['allow_live_browser'] is False
    assert ae.extra_hosts==()
    assert '© Central Bank of the UAE' in ae.connector_config()['source_reuse']['notice']
    assert all(s.jurisdiction!='MY' and 'dfsa' not in s.key for s in SOURCES)
    allowed=AllowList([SourceRecord(uuid4(),ae.name,ae.source_type,ae.base_url,ae.jurisdiction,ae.operations,ae.connector_config())])
    for url in ('https://rulebook.centralbank.ae/a','https://www.dfsa.ae/a','https://www.bnm.gov.my/a','https://www.mas.gov.sg/a'):
        with pytest.raises(FetchRefused):allowed.source_for(url)


def test_native_register_metadata_dispatch_keeps_all_native_fields():
    from datetime import UTC, datetime
    seed=next(s for s in SOURCES if s.key=='au-register')
    source=SourceRecord(uuid4(),seed.name,seed.source_type,seed.base_url,seed.jurisdiction,seed.operations,seed.connector_config())
    data={'id':'C2006A00169','name':'AML Act','makingDate':'2006-12-12','status':'In force','extraFutureField':{'facts':['A','B','C']}}
    page=FetchedPage('https://api.prod.legislation.gov.au/v1/Titles/C2006A00169','https://api.prod.legislation.gov.au/v1/Titles/C2006A00169',source,'json','application/json',json.dumps(data).encode(),datetime.now(UTC))
    result=extract(page)
    assert result.status=='complete'
    assert result.metadata['native_record']==data
    assert result.metadata['role']=='discovery_metadata'
    assert 'not legal text' in result.text


def test_fixed_australian_pdf_is_recognized_and_shares_only_its_html_key():
    from mira.agents.scout import _is_pdf, document_key
    stem='https://www.legislation.gov.au/C2006A00169/2026-07-01/2026-07-01/text/original/'
    assert _is_pdf(stem+'pdf')
    assert document_key(stem+'pdf')==document_key(stem+'epub/OEBPS/document_1/document_1.html')
    assert document_key(stem+'pdf')!=document_key('https://www.legislation.gov.au/C2006A00169/2026-07-01/text')
