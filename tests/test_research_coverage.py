"""Coverage regressions at discovery, publication fetching and evidence selection."""

from datetime import date
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from mira.agents.scout import WebScout, _ScoutRun, document_key
from mira.extract import Extracted, extract, extract_html
from mira.fetch import FetchedPage
from test_fetch_extract import HKMA
from mira.contracts import ScoutReport
from test_orchestrator import E_RULE, MAS
from test_orchestrator import context


def test_public_sfc_search_uses_post_and_refuses_unregistered_post_targets():
    import pytest
    from mira.fetch import AllowList, Fetcher, FetchRefused, RawResponse
    from mira.sfc import search_payload

    source = replace(HKMA, base_url="https://apps.sfc.hk", connector_config={})
    calls = []

    class PublicService:
        def get(self, url, headers, timeout, max_bytes):
            assert url.endswith("/robots.txt")
            return RawResponse(404, {}, b"")

        def post(self, url, headers, timeout, max_bytes, body):
            calls.append((url, json.loads(body)))
            return RawResponse(200, {"content-type": "application/json"}, b'{"items": [], "total": 0}')

    fetcher = Fetcher(AllowList([source]), transport=PublicService(), resolver=lambda _: ["93.184.216.34"])
    url = "https://apps.sfc.hk/edistributionWeb/api/circular/search?category=anti-money-laundering&year=2025"
    payload = search_payload(url)
    assert fetcher.fetch(url, json_body=payload).kind == "json"
    assert calls == [(url, payload)]
    with pytest.raises(FetchRefused, match="limited"):
        fetcher.fetch("https://apps.sfc.hk/unregistered", json_body={})


def test_publication_dates_stay_with_their_own_table_rows():
    body = b'''<table>
      <tr><td><a href="/a">AML guidance A</a></td><td>12 Dec 2025</td></tr>
      <tr><td><a href="/b">AML guidance B</a></td><td>21 Nov 2025</td></tr>
    </table>'''
    links = extract_html(body, "https://www.hkma.gov.hk/list").links
    assert [link.published for link in links] == [date(2025, 12, 12), date(2025, 11, 21)]
    assert all(link.date_source and "table" in link.date_source for link in links)


def test_hkma_publication_identity_includes_the_document_repository_link():
    url = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251210-1-EN"
    assert document_key(url) == document_key(url.replace("docId/", "current/"))
    assert document_key(url) == document_key(
        "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20251210-1-EN/20251210-1-EN.pdf"
    )


def test_hkma_publication_fetch_starts_with_its_primary_pdf(monkeypatch):
    calls = []
    scout = WebScout("unused", None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)), max_rounds=0)
    run = _ScoutRun(scout, None, context(), uuid4(), SimpleNamespace(max_documents=2))
    monkeypatch.setattr(run, "_fetch", lambda url, link=None: calls.append(url) or Extracted("Guidance", "complete", ["AML guidance"]))

    run._fetch_document("https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251210-1-EN")

    assert calls == ["https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20251210-1-EN/20251210-1-EN.pdf"]


def test_sfc_public_search_discovers_full_publications_without_citing_the_index():
    from datetime import UTC, datetime

    body = json.dumps({"items": [{"refNo": "25EC62", "title": "Detection of layering in money laundering",
                                 "releasedDate": "2025-11-17T19:52:56"}], "total": 1}).encode()
    url = "https://apps.sfc.hk/edistributionWeb/api/circular/search?category=anti-money-laundering&year=2025"
    result = extract(FetchedPage(url, url, HKMA, "json", "application/json", body, datetime.now(UTC)))

    assert result.status == "complete"
    assert result.pages == []
    assert result.links[0].url == "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=25EC62&lang=EN"
    assert result.links[0].published == date(2025, 11, 17)


def test_sfc_public_content_preserves_text_and_the_issued_date():
    from datetime import UTC, datetime

    body = json.dumps({"refNo": "25EC62", "title": "Layering activities", "html": "<p>Firms should detect layering.</p>",
                       "releasedDate": "2025-11-17T19:52:56", "modificationTime": "2026-01-01T10:00:00"}).encode()
    url = "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=25EC62&lang=EN"
    result = extract(FetchedPage(url, url, HKMA, "json", "application/json", body, datetime.now(UTC)))

    assert "Firms should detect layering." in result.text
    assert result.published == date(2025, 11, 17)
    assert "releasedDate" in result.published_basis


def test_sfc_consultation_listing_uses_paper_fields_and_its_issue_date():
    from datetime import UTC, datetime

    body = json.dumps({"items": [{"cpRefNo": "26CP1", "cpTitle": "Consultation on AML controls",
                                 "cpIssueDate": "2026-01-29T16:30:00", "ccRefNo": "26CC1",
                                 "ccTitle": "Conclusions", "ccIssueDate": "2026-06-05T16:30:00"}], "total": 1}).encode()
    url = "https://apps.sfc.hk/edistributionWeb/api/consultation/search?year=2026"
    result = extract(FetchedPage(url, url, HKMA, "json", "application/json", body, datetime.now(UTC)))

    assert result.pages == []
    assert result.links[0].url.endswith("/consultation/content?refNo=26CP1&lang=EN")
    assert result.links[0].published == date(2026, 1, 29)
    assert result.links[1].url.endswith("/consultation/conclusion?refNo=26CP1&lang=EN")
    assert result.links[1].published == date(2026, 6, 5)


def test_enforcement_tasks_start_at_the_enforcement_index(monkeypatch):
    index = "https://www.mas.gov.sg/enforcement"
    source = replace(MAS, connector_config={
        "feeds": ["https://www.mas.gov.sg/circulars.xml"], "start_urls": [],
        "category_urls": {"enforcement": [index]},
    })
    ctx = context()
    task = SimpleNamespace(max_documents=6, source_ids=(source.id,), expected_source_ids=(E_RULE.id,),
                           question="AML enforcement", role="regulatory_scout", jurisdiction_code="SG")
    scout = WebScout("unused", None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)), max_rounds=0)
    run = _ScoutRun(scout, None, ctx, uuid4(), task)
    run.store = SimpleNamespace(list_sources=lambda workspace: [source],
                                list_expected_sources=lambda *args: [replace(E_RULE, category="enforcement")])
    calls = []

    def fetch(url):
        calls.append(url)
        run.allowance -= 1

    monkeypatch.setattr(run, "_fetch", fetch)
    monkeypatch.setattr(run, "_report", lambda: (ScoutReport(documents=[], expected_source_statuses=[], notes=None), {}))

    run.execute()

    assert calls == [index]
    assert run.allowance == 5
    assert any(link.url.endswith("circulars.xml") for link in run.candidates)


def test_analyst_gets_the_available_context_of_each_selected_publication():
    from test_orchestrator import FakeScout, make

    class SelectiveScout(FakeScout):
        def run(self, ctx, step_id, task):
            outcome = super().run(ctx, step_id, task)
            document = outcome.result.report.documents[0].model_copy(update={"relevant_passage_labels": ["P1"]})
            report = outcome.result.report.model_copy(update={"documents": [document]})
            return replace(outcome, result=outcome.result.model_copy(update={"report": report}))

    orchestrator, _, _, _ = make(scout=SelectiveScout())

    outcome = orchestrator.run(context())

    assert outcome.status == "draft", outcome.reasons
    assert not outcome.snapshot.unresolved_finding_ids


def test_cross_year_search_reads_both_year_indexes_before_selecting_publications(monkeypatch):
    template = "https://apps.sfc.hk/edistributionWeb/api/circular/search?year={year}"
    source = replace(MAS, connector_config={"category_urls": {"circular": [template]}})
    ctx = context()
    # A later as-of date must not displace the requested reporting years.
    ctx = replace(ctx, brief=ctx.brief.model_copy(update={"as_of_date": date(2028, 10, 26)}))
    task = SimpleNamespace(max_documents=6, source_ids=(source.id,), expected_source_ids=(E_RULE.id,),
                           question="AML circulars", role="regulatory_scout", jurisdiction_code="SG")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace(), max_rounds=0), None, ctx, uuid4(), task)
    run.store = SimpleNamespace(list_sources=lambda _: [source],
                                list_expected_sources=lambda *args: [replace(E_RULE, category="circular")])
    calls = []

    def fetch(url):
        calls.append(url)
        run.allowance -= 1

    monkeypatch.setattr(run, "_fetch", fetch)
    monkeypatch.setattr(run, "_report", lambda: (ScoutReport(documents=[], expected_source_statuses=[], notes=None), {}))
    run.execute()

    assert calls == [template.format(year=2026), template.format(year=2025)]
    assert run.allowance == 4


def test_passage_selection_covers_distinct_publications_before_more_pages(monkeypatch):
    from mira.agents import scout as module
    from mira.agents.scout import _Visit
    from test_orchestrator import PASSAGES

    first = PASSAGES[0]
    second_page = replace(first, id=uuid4(), passage_number=2, content=first.content + " More guidance.")
    other = replace(first, id=uuid4(), document_version_id=uuid4(), document_id=uuid4(),
                    source_url="https://www.mas.gov.sg/another-notice")
    records = [first, second_page, other]
    task = SimpleNamespace(max_documents=2, source_ids=(first.source_id,), question="AML")
    scout = WebScout("unused", None, SimpleNamespace())
    connection = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchall=lambda: []))
    run = _ScoutRun(scout, connection, context(), uuid4(), task)
    run.store = SimpleNamespace(get_passages=lambda *args: records)
    run.visits = [_Visit(p.source_url, p.document_version_id, [p.id]) for p in records]
    monkeypatch.setattr(module, "MAX_PASSAGES_SHOWN", 2)

    chosen = run._passages()

    assert {p.document_id for p in chosen} == {first.document_id, other.document_id}


def test_selection_diagnostics_distinguish_filtered_and_presented(monkeypatch):
    from mira.agents import scout as module
    from mira.extract import Link
    from mira.contracts import LinkSelection

    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, question="AML", role="regulatory_scout")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace(), max_rounds=1), None, context(), uuid4(), task)
    run.candidates = [Link("https://example.org/future", "", "", date(2030, 1, 1), "date"),
                      Link("https://example.org/a", "", ""), Link("https://example.org/b", "", "")]
    monkeypatch.setattr(module, "call_checked", lambda *args, **kwargs: SimpleNamespace(output=LinkSelection(link_labels=["L1"], notes=None), model="scripted", tokens_in=0, tokens_out=0))
    monkeypatch.setattr(run, "_fetch_document", lambda *args: None)
    run._select_and_fetch()
    diagnostic = run.selection_diagnostics[0]
    assert [(item["url"], item["reason"]) for item in diagnostic["filtered"]] == [("https://example.org/future", "out_of_as_of")]
    assert [(item["label"], item["url"], item["selected"]) for item in diagnostic["presented"]] == [
        ("L1", "https://example.org/a", True), ("L2", "https://example.org/b", False)]


def test_selection_diagnostics_cap_filtered_and_keep_presented(monkeypatch):
    from mira.agents import scout as module
    from mira.extract import Link
    from mira.contracts import LinkSelection

    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, question="AML", role="regulatory_scout")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace()), None, context(), uuid4(), task)
    duplicate = Link("https://example.org/dup", "", "")
    run.candidates = [duplicate, duplicate] + [Link(f"https://example.org/old{i}", "", "", date(2020, 1, 1), "date") for i in range(5)] + [Link(f"https://example.org/{i}", "", "") for i in range(4)]
    monkeypatch.setattr(module, "MAX_DIAGNOSTIC_RECORDS", 2)
    monkeypatch.setattr(module, "MAX_LINKS_SHOWN", 2)
    monkeypatch.setattr(module, "call_checked", lambda *a, **kw: SimpleNamespace(output=LinkSelection(link_labels=[], notes=None), model="s", tokens_in=0, tokens_out=0))
    run._select_and_fetch()
    record = run.selection_diagnostics[0]
    assert [item["reason"] for item in record["filtered"]] == ["duplicate_or_alias", "before_period"]
    assert record["filtered_omitted"] == 7
    assert record["prompt_cap_omitted"] == 3
    assert [(item["rank"], item["label"], item["url"]) for item in record["presented"]] == [(1, "L1", "https://example.org/dup"), (2, "L2", "https://example.org/0")]
    assert record["stop_reason"] == "no_selection"


def test_scout_result_old_data_and_telemetry_step_persistence():
    from test_orchestrator import FakeScout, make, steps
    from mira.contracts import ScoutResult

    class TelemetryScout(FakeScout):
        def run(self, ctx, step_id, task):
            outcome = super().run(ctx, step_id, task)
            old = outcome.result.model_dump(mode="json", exclude={"selection_diagnostics"})
            assert ScoutResult.model_validate(old).selection_diagnostics == {}
            return replace(outcome, result=outcome.result.model_copy(update={"selection_diagnostics": {"rounds": [{"stop_reason": "no_selection"}], "remaining_allowance": 1}}))

    orchestrator, store, _, _ = make(scout=TelemetryScout())
    orchestrator.run(context())
    record = next(r for r in steps(store) if r.role == "regulatory_scout")
    assert record.output_refs["selection_diagnostics"] == {"rounds": [{"stop_reason": "no_selection"}], "remaining_allowance": 1}


def test_selection_records_allowance_and_fetch_references(monkeypatch):
    from datetime import UTC, datetime
    from mira.agents import scout as module
    from mira.extract import Link
    from mira.contracts import FetchAttempt, LinkSelection

    task = SimpleNamespace(max_documents=1, max_llm_tokens=None, question="AML", role="regulatory_scout")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace(), links_per_round=2), None, context(), uuid4(), task)
    run.allowance = 2
    run.candidates = [Link("https://example.org/a", "", ""), Link("https://example.org/b", "", "")]
    version = uuid4()
    monkeypatch.setattr(module, "call_checked", lambda *a, **kw: SimpleNamespace(output=LinkSelection(link_labels=["L1", "L2"], notes=None), model="s", tokens_in=0, tokens_out=0))

    def fetch(url, link):
        if run.allowance:
            run.allowance = 0
            run.log.append(FetchAttempt(url=url, outcome="saved", document_version_id=version, error=None, attempted_at=datetime.now(UTC)))
    monkeypatch.setattr(run, "_fetch_document", fetch)
    run._select_and_fetch()
    first, second = run.selection_diagnostics[0]["presented"]
    assert first["fetch_attempts"] == [{"url": "https://example.org/a", "outcome": "saved", "document_version_id": str(version)}]
    assert second["fetch_status"] == "allowance_exhausted"
    assert run.selection_diagnostics[0]["remaining_allowance"] == 0


def test_repeated_selected_label_keeps_original_fetch_diagnostic(monkeypatch):
    from datetime import UTC, datetime
    from mira.agents import scout as module
    from mira.agents.scout import _Visit
    from mira.extract import Link
    from mira.contracts import FetchAttempt, LinkSelection

    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, question="AML", role="regulatory_scout")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace(), links_per_round=2), None, context(), uuid4(), task)
    url = "https://example.org/article"
    version = uuid4()
    run.candidates = [Link(url, "", "")]
    monkeypatch.setattr(module, "call_checked", lambda *a, **kw: SimpleNamespace(output=LinkSelection(link_labels=["L1", "L1"], notes=None), model="s", tokens_in=0, tokens_out=0))

    def fetch_new(url, link):
        run.seen.add(url)
        run.allowance -= 1
        run.log.append(FetchAttempt(url=url, outcome="saved", document_version_id=version, error=None, attempted_at=datetime.now(UTC)))
        run.visits.append(_Visit(url, version))
        return Extracted("title", "complete", ["body"])

    monkeypatch.setattr(run, "_fetch_new", fetch_new)
    run._select_and_fetch()
    record = run.selection_diagnostics[0]["presented"][0]
    assert len(run.log) == 1
    assert record["fetch_attempts"] == [{"url": url, "outcome": "saved", "document_version_id": str(version)}]
    assert record["fetch_status"] == "attempted"
