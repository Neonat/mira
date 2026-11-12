"""Build the Hong Kong training game using frozen local Mira verifications."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from uuid import UUID

import psycopg

from eval.hk_blind_review import local_connection_info
from mira.agents.temporal import check_claim_period
from mira.agents.verifier import quote_match
from mira.brief import brief_from_rows
from mira.claim_grounding import substantive_evidence
from mira.contracts import Brief, ClaimCitation, ClaimDraft, EvidenceInput
from mira.db import acting_as, connect, require_role
from mira.store import ClaimEvidence, PassageRecord, StoredClaim


DEFAULT_OUTPUT = Path("reports/hk-verification-game/index.html")
TEMPLATE = Path(__file__).with_suffix(".html")
THEME = TEMPLATE.parent.parent / "app" / "guest" / "review-theme.css"
SOURCE_HOSTS = {"brdr.hkma.gov.hk", "www.hkma.gov.hk"}


@dataclass(frozen=True)
class Scenario:
    check_id: UUID
    title: str
    situation: str
    verdict: str
    action: str
    explanation: str
    excerpt_start: str
    excerpt_end: str
    cutoff: date | None = None


SCENARIOS = (
    Scenario(
        check_id=UUID("8e7fd9cd-e3ae-49fe-9959-388aa749375d"),
        title="Testing schedule",
        situation="You’re reviewing a line for the bank’s sanctions screening oversight briefing.",
        verdict="supported",
        action="approve",
        explanation="The passage supports all three parts of the finding: risk, past testing performance and senior management approval. The source is within the review period.",
        excerpt_start="The frequency of testing should align with risk",
        excerpt_end="be approved by senior management.",
    ),
    Scenario(
        check_id=UUID("b73c3d21-5517-4a9e-9e2f-25f82a142fc2"),
        title="Guidance update",
        situation="You’re signing off a historical briefing on changes to controls for politically exposed persons (PEPs).",
        verdict="supported",
        action="send-back",
        explanation="The quotation is genuine. The publication came out on 28 August, one day after this brief’s cutoff. Ask for evidence available by the cutoff or move the finding to a later brief.",
        excerpt_start="Additional good practices have been brought to our attention.",
        excerpt_end="version 2.0 of the Smart Tips.",
        cutoff=date(2026, 8, 27),
    ),
    Scenario(
        check_id=UUID("f9310fe6-8a18-47bd-8e20-f4f282a13f71"),
        title="Information-sharing controls",
        situation="The bank plans to rely on this finding in a control standard. Its policy owner resolves material gaps in the basis for a control.",
        verdict="partially_supported",
        action="escalate",
        explanation="The excerpt lists the items. The evidence packet is missing the lead-in that establishes which controls should cover them. Ask the policy owner to verify the complete provision before relying on the finding.",
        excerpt_start="(b) access to designated platforms;",
        excerpt_end="(d) maintaining related records.",
    ),
)


def check_evidence(claim: StoredClaim, passages: list[PassageRecord], brief: Brief) -> tuple[bool, str | None]:
    """Apply the factual verifier's deterministic citation and evidence gates."""
    by_id = {passage.id: passage for passage in passages}
    matched = bool(claim.evidence) and all(
        item.passage_id in by_id and quote_match(item.supporting_quote, by_id[item.passage_id].content)
        for item in claim.evidence
    )
    if not matched:
        return False, None
    error = None if substantive_evidence(passages) else "listing only"
    try:
        check_claim_period(claim.draft, brief, passages)
    except ValueError as exc:
        error = str(exc)
    return True, error


def read_case(conn, scenario: Scenario) -> dict:
    row = conn.execute(
        """
        select c.finding_id, c.verdict, c.checked_at, c.input_snapshot,
               c.input_fingerprint = private.evidence_input_fingerprint(c.input_snapshot) as fingerprint_matches,
               r.created_by, r.as_of_date, r.retrieval_settings,
               v.risk_topics, v.markets, v.reporting_period_start, v.reporting_period_end
        from public.claim_checks c
        join public.analysis_runs r on r.id = c.analysis_run_id and r.workspace_id = c.workspace_id
        join public.project_revisions v on v.id = r.project_revision_id and v.workspace_id = r.workspace_id
        where c.id = %s and c.method = 'llm' and c.input_snapshot is not null
        """,
        (scenario.check_id,),
    ).fetchone()
    if not row or not row["fingerprint_matches"] or row["verdict"] != scenario.verdict:
        raise ValueError(f"Expected frozen verification is unavailable for {scenario.title}.")

    snapshot = EvidenceInput.model_validate(row["input_snapshot"])
    with acting_as(conn, row["created_by"]):
        require_role(conn, snapshot.workspace_id)
    finding = snapshot.findings[row["finding_id"]]
    if (finding.jurisdiction_code != "HK" or finding.is_inference or finding.depends_on
            or len(snapshot.passages) != 1 or not finding.evidence):
        raise ValueError(f"Unexpected evidence scope for {scenario.title}.")
    saved = next(iter(snapshot.passages.values()))
    if any(c.passage_id != saved.id or c.document_version_id != saved.document_version_id for c in finding.evidence):
        raise ValueError(f"Citation does not match the frozen source for {scenario.title}.")
    permitted = conn.execute(
        """
        select 1 from public.sources
        where id = %s and workspace_id = %s and source_key = 'hkma' and jurisdiction_code = 'HK'
          and is_active and permitted_operations @> array['store_text', 'quote']::text[]
        """,
        (saved.source_id, snapshot.workspace_id),
    ).fetchone()
    source = urlsplit(saved.source_url)
    if not permitted or not saved.published_at or source.scheme != "https" or source.hostname not in SOURCE_HOSTS:
        raise ValueError(f"Approved local source is unavailable for {scenario.title}.")

    draft = ClaimDraft(
        **finding.model_dump(exclude={"finding_id", "depends_on", "evidence"}),
        claim_label="F1",
        depends_on=[],
        citations=[ClaimCitation(passage_label="P1", supporting_quote=c.supporting_quote) for c in finding.evidence],
    )
    claim = StoredClaim(finding.finding_id, draft,
                        tuple(ClaimEvidence(c.passage_id, c.supporting_quote) for c in finding.evidence), ())
    brief = brief_from_rows(row, row)
    if scenario.cutoff:
        brief = Brief.model_validate({
            **brief.model_dump(), "as_of_date": scenario.cutoff,
            "period_end": min(brief.period_end, scenario.cutoff),
        })
    matched, date_error = check_evidence(claim, [PassageRecord(**saved.model_dump())], brief)
    expected_error = "cited publication is after the brief's as-of date" if scenario.cutoff else None
    if not matched or date_error != expected_error:
        raise ValueError(f"Verification checks changed for {scenario.title}.")

    clean = " ".join(saved.content.split())
    start = clean.find(scenario.excerpt_start)
    end = clean.find(scenario.excerpt_end, start) if start >= 0 else -1
    if end < 0:
        raise ValueError(f"The excerpt changed for {scenario.title}.")
    excerpt = clean[start:end + len(scenario.excerpt_end)]
    if len(excerpt) > 480 or not quote_match(excerpt, saved.content):
        raise ValueError(f"Expected short source excerpt is unavailable for {scenario.title}.")

    recorded = {
        "supported": "Supported in the saved check.",
        "partially_supported": "Partially supported in the saved check.",
    }
    return {
        "title": scenario.title, "situation": scenario.situation, "finding": finding.content,
        "cutoff": brief.as_of_date.isoformat(), "action": scenario.action, "explanation": scenario.explanation,
        "source": {
            "title": saved.title, "url": saved.source_url, "date": saved.published_at.isoformat(),
            "page": saved.page_number, "excerpt": excerpt,
        },
        "checks": [
            ["Quotation", "Matched the frozen passage."],
            ["Review date", "Blocked. The publication is after the cutoff." if date_error else "Passed."],
            ["Support for this finding", "Date gate blocks this case before the support check." if date_error
             else recorded[row["verdict"]] + f" Recorded {row['checked_at']:%d %b %Y}."],
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    dsn = os.environ.get("MIRA_TEST_DATABASE_URL")
    if not dsn:
        parser.error("Set MIRA_TEST_DATABASE_URL to the local saved archive database.")
    try:
        with connect(local_connection_info(dsn)) as conn, conn.transaction():
            conn.execute("set transaction isolation level repeatable read read only")
            conn.execute("set local statement_timeout = '10s'")
            cases = [read_case(conn, scenario) for scenario in SCENARIOS]
        template = TEMPLATE.read_text(encoding="utf-8")
        if template.count("{{CASES}}") != 1 or template.count("{{THEME}}") != 1:
            raise ValueError("The training template has an invalid placeholder.")
        html = template.replace("{{THEME}}", THEME.read_text(encoding="utf-8").strip(), 1)
        html = html.replace("{{CASES}}", json.dumps(cases, ensure_ascii=False).replace("<", r"\u003c"), 1)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=args.output.parent, mode="w", encoding="utf-8", delete=False) as temp:
            path = Path(temp.name)
            try:
                temp.write(html)
                temp.close()
                path.replace(args.output)
            finally:
                path.unlink(missing_ok=True)
    except (psycopg.Error, OSError, KeyError, ValueError) as exc:
        detail = str(exc) if type(exc) is ValueError else "Could not read the local archive or write the game."
        print(detail, file=sys.stderr)
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
