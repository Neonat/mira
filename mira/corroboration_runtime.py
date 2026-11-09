"""Coordinate saved-first assessments, optional permitted follow-up and persistence."""
from uuid import UUID
from mira.corroboration import CorroborationService, LlmAssessor, SearchLimits, MAX_ASSESSOR_CANDIDATES
from mira.corroboration_store import CorroborationStore


class CorroborationPersistenceFailure(RuntimeError):
    def __init__(self, assessment, cause):
        super().__init__(f"corroboration persistence failed: {type(cause).__name__}")
        self.assessment=assessment


class ClaimCorroborator:
    def __init__(self, conn, client, *, discovery=None, browser=None, live_browser=None):
        self.conn, self.client = conn, client
        self.discovery, self.browser = discovery,browser
        self.live_browser=live_browser
        self.ledger = CorroborationStore(conn)
        self.acquisition = None

    def __call__(self, ctx, claim, base_input, budget):
        sources = [s for s in self.ledger.evidence.list_sources(ctx.workspace_id)
                   if s.jurisdiction_code is None or s.jurisdiction_code in ctx.brief.jurisdictions]
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
