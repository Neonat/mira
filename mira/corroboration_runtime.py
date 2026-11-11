"""Coordinate saved-first assessments, optional permitted follow-up and persistence."""
from uuid import UUID
from dataclasses import dataclass
from mira.corroboration import CorroborationService, LlmAssessor, SearchLimits, MAX_ASSESSOR_CANDIDATES
from mira.corroboration_store import CorroborationStore


class CorroborationPersistenceFailure(RuntimeError):
    def __init__(self, assessment, cause):
        super().__init__(f"corroboration persistence failed: {type(cause).__name__}")
        self.assessment=assessment


@dataclass
class PreparedSavedAssessment:
    """Frozen reads first; provider-only work; persistence on the owner thread."""
    runtime: object
    ctx: object
    claim: object
    base: dict
    sources: list
    candidates: list
    authoritative: bool

    def evaluate(self,budget):
        service=CorroborationService(LlmAssessor(self.runtime.client))
        result=service.assess(ctx=self.ctx,claim=self.claim,base_evidence_input=self.base,
            saved_candidates=self.candidates,sources=self.sources,budget=budget,
            authoritative_primary=self.authoritative,
            limits=SearchLimits(max_passages=MAX_ASSESSOR_CANDIDATES,max_seconds=90)).model_dump(mode='json')
        # With an eligible saved candidate the ordinary service spends its one
        # assessment attempt, then stops before discovery. Preserve that reason
        # rather than suggesting the user's enabled discovery was disabled.
        if self.runtime.discovery is not None and 'discovery_disabled' in result['stop_reasons']:
            result['stop_reasons'].remove('discovery_disabled')
            if result['candidates']:
                result['stop_reasons'].append('assessment_attempt_limit')
        return result

    def persist(self,result):
        try:
            return self.runtime.ledger.save(self.ctx,self.claim,self.base,result)
        except Exception as exc:
            raise CorroborationPersistenceFailure(result,exc) from None


class ClaimCorroborator:
    def __init__(self, conn, client, *, discovery=None, browser=None, live_browser=None):
        self.conn, self.client = conn, client
        self.discovery, self.browser = discovery,browser
        self.live_browser=live_browser
        self.ledger = CorroborationStore(conn)
        self.acquisition = None

    def prepare_saved(self,ctx,claim,base_input):
        # No-candidate/fresh acquisition retains the existing serial connection
        # path. A nonempty saved assessment already suppresses discovery in the
        # service, so evaluating this prepared job changes no search policy.
        from mira.research_settings import restrict_sources
        sources=restrict_sources([s for s in self.ledger.evidence.list_sources(ctx.workspace_id)
            if s.jurisdiction_code is None or s.jurisdiction_code in ctx.brief.jurisdictions],
            ctx.research_settings,ctx.brief.jurisdictions)
        candidates=self.ledger.candidates(ctx,claim,max_passages=MAX_ASSESSOR_CANDIDATES)
        if not candidates:
            return None
        source_map={s.id:s for s in sources}
        primary=list(base_input['passages'].values())
        primary_ids={UUID(p['id']) for p in primary}
        def eligible(c):
            p=c.passage
            source=source_map.get(p.source_id)
            return (not claim.draft.is_inference and bool(primary) and p.id not in primary_ids
                and c.workspace_id==ctx.workspace_id and c.eligible and c.current and source is not None
                and {'fetch','store_text'}<=set(source.permitted_operations)
                and (not source.jurisdiction_code or source.jurisdiction_code in ctx.brief.jurisdictions)
                and (not p.published_at or p.published_at<=ctx.brief.as_of_date)
                and (not p.jurisdiction_code or p.jurisdiction_code in ctx.brief.jurisdictions))
        if not any(eligible(c) for c in candidates):
            return None
        authoritative=bool(primary) and all(source_map.get(UUID(p['source_id'])) is not None
            and source_map[UUID(p['source_id'])].source_type=='regulator' for p in primary)
        return PreparedSavedAssessment(self,ctx,claim,base_input,sources,candidates,authoritative)

    def __call__(self, ctx, claim, base_input, budget):
        sources = [s for s in self.ledger.evidence.list_sources(ctx.workspace_id)
                   if s.jurisdiction_code is None or s.jurisdiction_code in ctx.brief.jurisdictions]
        from mira.research_settings import restrict_sources
        sources=restrict_sources(sources,ctx.research_settings,ctx.brief.jurisdictions)
        # Bound retrieval before projecting/freeze: the primary verifier must not
        # inherit twenty full passages when the assessor can check only two.
        limits = SearchLimits(max_passages=MAX_ASSESSOR_CANDIDATES,max_seconds=90)
        candidates = self.ledger.candidates(ctx,claim,max_passages=limits.max_passages)
        if self.discovery is not None and self.acquisition is None:
            from mira.corroboration_acquisition import CorroborationDiscovery
            self.acquisition = CorroborationDiscovery(self.conn,sources,self.discovery,browser=self.browser,live_browser=self.live_browser)
        service = CorroborationService(LlmAssessor(self.client),self.acquisition)
        source_map={s.id:s for s in sources}
        primary=list(base_input['passages'].values())
        authoritative=bool(primary) and all(source_map.get(UUID(p['source_id'])) is not None
            and source_map[UUID(p['source_id'])].source_type=='regulator' for p in primary)
        assessment=service.assess(ctx=ctx,claim=claim,base_evidence_input=base_input,
            saved_candidates=candidates,sources=sources,budget=budget,authoritative_primary=authoritative,limits=limits)
        result=assessment.model_dump(mode='json')
        try:
            return self.ledger.save(ctx,claim,base_input,result)
        except Exception as exc:
            raise CorroborationPersistenceFailure(result,exc) from None

    def close(self):
        if self.acquisition is not None:
            self.acquisition.close()
