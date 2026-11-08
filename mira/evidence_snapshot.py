"""Canonical evidence inputs captured before verification, without temporary labels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from uuid import UUID

from mira.contracts import EvidenceInput, FrozenCitation, FrozenFinding, FrozenPassage
from mira.store import PassageRecord, RunContext, StoredClaim


def build_verification_input(
    ctx: RunContext,
    claim: StoredClaim,
    claims: Mapping[UUID, StoredClaim],
    passages: Mapping[UUID, PassageRecord],
    corroboration: Mapping[UUID, dict] | None = None,
) -> EvidenceInput:
    """Freeze the claim and its complete dependency closure, failing on missing inputs.

    StoredClaim.evidence is the supporting-link input handed to the verifier. No
    unseen context/contradiction links or made-up provenance are certified here.
    """
    frozen_findings: dict[UUID, FrozenFinding] = {}
    frozen_passages: dict[UUID, FrozenPassage] = {}
    visiting: set[UUID] = set()

    def visit(item: StoredClaim) -> None:
        finding_id = item.finding_id
        if finding_id in visiting:
            raise ValueError(f"dependency cycle at finding {finding_id}")
        if finding_id in frozen_findings:
            return
        visiting.add(finding_id)
        for dependency_id in sorted(item.depends_on, key=str):
            dependency = claims.get(dependency_id)
            if dependency is None or dependency.finding_id != dependency_id:
                raise ValueError(f"missing dependency finding {dependency_id}")
            visit(dependency)
        evidence = []
        seen_quotes: set[tuple[UUID, str]] = set()
        for citation in sorted(item.evidence, key=lambda e: (str(e.passage_id), e.supporting_quote)):
            quote_key = (citation.passage_id, citation.supporting_quote)
            if quote_key in seen_quotes:
                continue
            seen_quotes.add(quote_key)
            passage = passages.get(citation.passage_id)
            if passage is None or passage.id != citation.passage_id:
                raise ValueError(f"missing passage {citation.passage_id}")
            frozen_passages[passage.id] = FrozenPassage(**asdict(passage))
            evidence.append(FrozenCitation(
                passage_id=passage.id, document_version_id=passage.document_version_id,
                supporting_quote=citation.supporting_quote, support_type="supports",
            ))
        fields = item.draft.model_dump(exclude={"claim_label", "citations", "depends_on"})
        frozen_findings[finding_id] = FrozenFinding(
            finding_id=finding_id, **fields, depends_on=sorted(item.depends_on, key=str), evidence=evidence,
        )
        visiting.remove(finding_id)

    visit(claim)
    return EvidenceInput(
        workspace_id=ctx.workspace_id, analysis_run_id=ctx.analysis_run_id,
        analysis_revision_id=ctx.analysis_revision_id,
        findings=dict(sorted(frozen_findings.items(), key=lambda pair: str(pair[0]))),
        passages=dict(sorted(frozen_passages.items(), key=lambda pair: str(pair[0]))),
        corroboration={fid: corroboration[fid] for fid in frozen_findings if fid in (corroboration or {})} or None,
    )
