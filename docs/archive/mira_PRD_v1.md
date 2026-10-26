Mira Product Requirements

Banking incident research and regulatory risk analysis

Version 1.0 | 11 October 2026 | Audience: all three developers and the product owner

Mira will help auditors at a Singapore based bank turn external news and historical incidents into project specific risk research. It will combine a stored project and its linked incident evidence with relevant regulations, then produce a cited report for human review. This document defines the whole product, the shared data contracts and the work required from each developer.

**End goal** A scalable, searchable evidence platform covering 20 to 30 years of available news and regulatory history across selected markets and broader regions such as APAC and EMEA. Users must be able to update records manually, trigger ingestion, investigate developments and reproduce the evidence behind an assessment.

**Core domain flow** External news becomes stored Incidents. Incidents are linked into stored Projects. External regulations become stored Regulation versions. Analysis combines a Project revision and relevant Regulation versions. A stored Analysis run produces a versioned Report for external output.

**Development approach** The data model and interfaces are agreed by all three developers. Developer 3 implements shared storage and retrieval. Developers 1 and 2 use those interfaces and example records while infrastructure is being completed.

| **Dev** | **Primary ownership** | **Required outcome** |
| --- | --- | --- |
| Dev 1 | News and shared ingestion | Reliable collection, historical imports, incident records and user controlled ingestion. |
| Dev 2 | Projects, regulations and analysis | Project relevance, regulatory versions, evidence based implications and report content. |
| Dev 3 | Storage, search and report delivery | Shared records, searchable evidence, controlled edits and reproducible report output. |

**Requirement status** Confirmed product requirements reflect the agreed direction in the project discussion. Pilot boundaries, implementation choices and numerical targets in this PRD are proposed baselines for team agreement. They are not bank approval or evidence that production readiness has already been achieved.

**How to use this document** Read the goal, domain model, workflow and data contracts before building a module. Each developer then implements the owned requirements and acceptance criteria. Shared tests and early integration are required for all three workstreams.

# 1 Product goal and scope

## Problem and intended users

Auditors currently assemble external developments from news, regulator publications and previous cases. The work is difficult to repeat consistently across a long historical period or several markets. Mira should reduce the time spent finding and checking evidence while preserving the auditor's judgement about relevance and risk.

| **User** | **Main need** |
| --- | --- |
| Auditor or analyst | Find developments relevant to an audit project, inspect original evidence and draft review questions. |
| Reviewer | Check factual support, regulatory applicability and the reasoning behind priorities before accepting a report. |
| Data curator | Manage sources, run historical imports, correct records, resolve duplicates and inspect coverage gaps. |
| Administrator | Configure access, connectors, region definitions, model settings and operational controls. |

## Confirmed requirements

* Preserve the end goal of 20 to 30 years of news and regulatory history. Support both curated source collections and broader financial news coverage.
* Support country or market queries and regional queries such as APAC and EMEA. The bank must be able to configure its region groupings.
* Allow users to add and correct records and manually trigger ingestion. Show progress, failures and the resulting data changes.
* Store Incidents, Projects and Regulations as distinct domain records. Analyse Projects with Regulations and generate reports from the analysis.
* Use hybrid project creation: users can create Projects directly, and reviewed system suggested themes can become Projects. Suggestions do not create Projects automatically.
* Use the latest news to trigger investigations, and archived incidents to provide historical context. Regulatory updates must also be collected independently.
* Retain original evidence, citations, dates, versions and review history. Preserve factual claims separately from inferred risk implications.

## Outcome and boundaries

Success means a reviewer can understand why a development matters to a project, inspect the source passages and regulatory versions, and decide what to investigate next. Search scores, news volume and external enforcement actions do not by themselves establish the bank's control effectiveness or compliance status.

The first release uses public or appropriately licensed external material. A later bank deployment can link requirements to internal controls, tests and evidence under approved access arrangements. Internal gap assessment and compliance sign off require that additional evidence and accountable review.

# 2 Release scope and domain model

## Release boundaries

| **Stage** | **Included** | **Completion condition** |
| --- | --- | --- |
| First working release | One complete workflow using the production oriented data model, manual ingestion and edits, country and region filters, versioned regulations and cited reports. | End to end acceptance tests pass on representative real public documents and controlled fixtures. |
| Archive expansion | Additional sources, historical imports, scanned document handling where needed, more topics and markets, and appropriate language support. | Coverage is measured by source and year; imports resume safely; retrieval and costs are tested at representative scale. |
| Bank deployment | Approved hosting, identity integration, access controls, operational recovery, licensed feeds and any internal control evidence integration. | Bank defined operational, security, legal and model validation criteria are met. |

Proposed first topic: AML/CFT customer due diligence, initially with Singapore and Hong Kong sources. This is a delivery sequence, not a permanent limit on the product. Region filters must work against a configurable mapping from the first release. The final pilot topic and source list remain product decisions.

## Core classes

| **Class** | **Purpose** | **Main relationships** |
| --- | --- | --- |
| Incident | A stored event or case supported by source evidence. Articles about the same event can share one incident. | Links to many source versions; can have related developments; can link to many projects. |
| Project | A stored audit or research context with scope, questions and linked incidents. Its scope and membership are versioned. | Connects many incidents through ProjectIncident links; has many Analysis runs. |
| Regulation | An identifiable instrument with one or more versions and source backed provisions. | Versions link to source passages and applicability information; analysis cites exact versions. |
| Analysis | A persisted run that evaluates a specific Project revision against selected Regulation versions and evidence. | Contains findings, supporting passages, uncertainty, proposed review actions and reviewer decisions. |
| Report | A versioned presentation of one Analysis revision. | References the analysis, evidence snapshot, report template and review status. |

The core flow is News to Incidents to Projects; Regulations to stored Regulation versions; Projects plus Regulations to Analysis; Analysis to Report. News articles, file versions, passages, ingestion runs and indexes are supporting records. They do not replace these core classes.

Use an explicit ProjectIncident relationship with a relevance reason, origin and review status. A single incident can inform several projects without being copied. Report exports must not modify the underlying analysis.

## Confirmed hybrid project creation

The product starts with a large historical backlog and no existing history in this research platform. Import and index that backlog independently of Projects. The system then proposes themes from related incidents. A user reviews the evidence, scope, period and markets before promoting a theme into a Project or linking it to an existing Project. Users can also create a Project directly.

| **Option** | **Advantages** | **Limitations** |
| --- | --- | --- |
| User defined Projects | Clear ownership and scope; focused reports; straightforward evaluation against audit questions. | Requires initial scoping and can miss patterns outside the chosen questions. |
| System generated Projects | Can organise a backlog and surface recurring or unfamiliar themes with less initial manual work. | Can generate overlapping or weak Projects, overvalue historical news frequency and lack internal bank context. |
| Selected hybrid model | Combines automatic discovery with reviewed scope and ownership; also supports manually created Projects. | Requires a suggestion queue, meaningful evidence for suggestions and a review step. |

A ThemeSuggestion is a candidate grouping, not an approved Project or a risk finding. Store its membership, explanation, periods, markets and review state. Pending or dismissed themes remain separate from the Project list. The backlog does not require one Project per incident.

# 3 User workflow

## Collect and maintain evidence

A curator selects configured sources, markets and a date range, then starts an ingestion run. The app returns a job identifier immediately. Workers fetch or import documents, preserve source versions, extract content, validate metadata and group reports into incidents. Users can inspect failures and resume interrupted work.

Regulatory connectors run through the same ingestion framework. They additionally identify the instrument, version, status, effective dates and provisions. The regulatory library is updated even when no news incident triggers an investigation. An older instrument that remains in force stays available for current analysis.

## Use latest news and the archive

Latest and Archive are views over the same incident collection. Latest uses the chosen reporting window and supported publication or material development dates. Importing an old story today must not make the event appear recent. The app stores discovery and event dates separately and provides an undated queue when dates cannot be established.

An older incident with a newly evidenced development can reappear in Latest. Recency is independent of review state: an archived incident may still have an unresolved question. Repeated coverage contributes evidence to a case and does not count as repeated incidents.

## Assemble the project context

The user either creates a Project or reviews a ThemeSuggestion and promotes it into one. A Project records its objective, questions, relevant bank entities or activities, markets, risk topics and reporting period. The user can adjust the suggested incident set before saving. Incidents are attached through reviewed or clearly labelled suggested links. Project revision history records scope and membership changes; analysis uses a fixed Project revision.

## Research and analyse

The analyst selects a Project and starts analysis. The system checks incident relevance, retrieves historical context and relevant regulatory passages, tests applicability and date constraints, and drafts implications. A bounded research loop may retrieve further evidence when support is missing. The run records which sources and versions were used and which questions remain unanswered.

Analysis separates source facts, applicability reasoning, potential risk implications and proposed audit work. Foreign cases can provide context while the system separately evaluates the requirements relevant to the project. No matching regulation is a recorded research outcome, not proof that an incident is irrelevant or that no obligation exists.

## Review and report

The reviewer inspects evidence and can accept, amend, reject or mark a finding as needing more evidence. Changes create new revisions. A report shows the Project scope, period, findings, priority reasons, confidence, source coverage and citations. Draft reports are visibly labelled; reviewed reports identify the reviewer and decision date.

# 4 Architecture and retrieval

## Storage and execution responsibilities

| **Component** | **Responsibility** | **Proposed implementation** |
| --- | --- | --- |
| Source archive | Original files or permitted snapshots, extracted text and immutable source version references. | Versioned object storage in the approved environment. |
| Structured store | Core classes, relationships, jobs, revisions, coverage and access metadata. | PostgreSQL from the first integrated release. |
| Retrieval layer | Keyword and semantic retrieval, filters, evidence passages and grouping by incident or instrument. | Begin with PostgreSQL full text plus pgvector; evaluate OpenSearch against the expected workload. |
| Workers and job queue | Backfills, incremental collection, extraction, OCR when supported, embeddings and analysis jobs. | Background jobs with checkpoints, retries, cancellation and source limits. |
| Application | Source management, project workspaces, search, record corrections, review and report delivery. | One repository with separate modules and shared contracts; workers can scale independently. |

The source archive and versioned structured records are authoritative. Search indexes and embeddings are derived and must be rebuildable. SQLite is not the intended shared system database. Exact deployment products, hosting and search engine selection require workload and environment decisions. [T1 to T5]

## Search behaviour

* Apply access, source, market, region, document type and date constraints to retrieval. Do not rely on the similarity model to enforce these conditions.
* Combine lexical retrieval for names, identifiers and phrases with semantic retrieval for related concepts. Merge candidates, optionally rerank, and return evidence grouped by incident or instrument.
* Index useful source passages with document version IDs and page or section locations. Summaries may help discovery, but a finding must cite source evidence.
* Store the embedding model and index version. Rebuild and compare retrieval quality before changing them. Respect each model's input length and supported languages.
* Return an explanation of matches, coverage limits and index freshness. Distinguish retrieval relevance from risk priority and evidence confidence.

## Acquisition and extensibility

Exa may be one discovery connector. Direct regulator feeds, approved websites, uploaded files and licensed archive imports must use the same contracts. A vendor integration must not control the domain model. A general web search is not a claim of complete historical coverage. [T8]

Keep a source coverage register with the requested years, known available years, verified ingested periods, languages, failed periods and access conditions. Approximately 1996 to 2026 spans the 30 year goal. Archive availability and source terms must be established before planning the complete import. [T6, T7]

# 5 Developer 1 requirements

Owner of news acquisition, incident extraction and shared ingestion infrastructure. Dev 1 owns the source and ingestion screens. Dev 2 reuses the ingestion framework for regulatory connectors. All writes use the shared storage interfaces owned by Dev 3.

**IN01 Source catalogue** Configure approved websites, feeds, uploads and archive connectors with source type, publisher, languages, coverage, access conditions and collection limits. Keep source credibility and document verification as separate fields.

**Acceptance** A curator can add or disable a source and see which requested years are available, missing, failed or not yet checked.

**IN02 Manual ingestion jobs** Allow source, market, period and import mode selection. Return a job ID immediately and support progress, retry, resume and cancellation at a safe checkpoint.

**Acceptance** An interrupted import resumes without duplicate logical records. The run reports new, updated, unchanged, skipped and failed items.

**IN03 Shared extraction pipeline** Fetch permitted HTML and PDF content or import supplied archives. Preserve the original version and extraction result, content hash, source URL, language and dates. Flag scanned, unreadable or unsupported files for processing or review.

**Acceptance** A fetch or extraction failure remains visible and never becomes an empty successful document. A changed source creates a new version.

**IN04 Incident construction** Extract an event description, entities, incident dates, affected markets, topics and source references. Normalise aliases while preserving the source wording. Distinguish allegations, reported events and authoritative findings.

**Acceptance** Every factual incident field can be traced to evidence or a labelled manual entry. Unknown dates and locations remain unknown.

**IN05 Duplicate and development handling** Group repeated articles about the same event using source identifiers, hashes and event evidence. Preserve distinct cases involving the same entity and link later developments. Allow curator merge and split decisions.

**Acceptance** Repeated coverage does not inflate incident counts. A later enforcement action can remain a distinct linked development.

**IN06 Latest and archive views** Classify by the selected reporting window and supported event or publication information. Keep first discovery, material updates and review status separate. Historical imports must preserve their original dates.

**Acceptance** A newly imported old article stays historical; a supported new development can reappear in Latest without losing its case history.

**IN07 Reliable storage handoff** Validate submissions against the shared schema. Use idempotency keys, returned version IDs and explicit errors. Preserve accepted manual corrections when later source extraction differs.

**Acceptance** Replaying a completed ingestion request has no extra effect. Conflicting automatic updates become reviewable proposals.

**IN08 Backfill operation** Partition imports into resumable source and time ranges, respect source limits and prioritise incremental updates alongside backfill work. Record throughput, failures and coverage by range.

**Acceptance** A failed range can be retried independently. Backfill progress and gaps are visible without blocking ordinary user searches.

**Handoff** Outputs are source versions, evidence extraction and incident candidates. Dev 1 does not write risk conclusions or decide regulatory applicability. First integration uses one source, one update, a duplicate and a controlled failure.

# 6 Developer 2 requirements

Owner of project meaning, incident relevance, regulatory knowledge, analysis and report content. Dev 2 owns the analysis and review panel. Dev 3 implements storage, search and rendering; Dev 1 supplies shared ingestion machinery.

**RA01 Regulatory ingestion** Build regulatory connectors that identify the instrument, version, authority, source status, provisions and effective dates. Preserve amendments, supersession and older baselines. Keep consultations, guidance and binding instruments distinguishable.

**Acceptance** Old and new versions can be retrieved separately. Unsupported dates, status or applicability remain flagged for review.

**RA02 Projects and incident links** Support user created Projects and reviewed theme promotion. Define scope and maintain incident links with relevance reasons, origin and review state. Version the scope and membership used by analysis.

**Acceptance** One incident can support two projects with different relevance reasons. Removing a link does not erase the incident or earlier project revisions.

**RA03 Project relevance** Screen linked or suggested incidents against project questions, bank activities, markets and risk topics before deeper regulatory research. Record exclusions and uncertain matches.

**Acceptance** The reviewer can see why each incident is included. A familiar bank name or similar phrase alone is insufficient justification.

**RA04 Regulatory applicability and time** Research requirements using jurisdiction, institution type, activity and the requested as of date. Cite exact versions and provisions. Treat foreign cases as context unless applicability is supported.

**Acceptance** A historical analysis does not silently apply a later requirement. Claimed changes cite an amendment or the compared versions.

**RA05 Risk implications** Explain the potential exposure to the Project, the mechanism of harm, impact, urgency and suggested audit work. Keep priority separate from evidence confidence and distinguish internal evidence gaps from observed facts.

**Acceptance** Every priority has a reason. An external incident cannot alone establish this bank's control failure, residual risk or breach.

**RA06 Evidence verification** Check each material factual or regulatory claim against cited source passages, including entity, jurisdiction, dates and source status. Record contradictory evidence and support failures.

**Acceptance** Unsupported claims are removed, qualified or marked as unresolved. Working URLs alone do not count as factual verification.

**RA07 Bounded research workflow** Implement retrieve, check, identify gaps, retrieve again and draft steps with configurable source, time, iteration and cost limits. Treat retrieved content as data and record model, prompt and retrieval versions.

**Acceptance** The run ends with a useful incomplete result when evidence or budget is exhausted. It follows no instructions embedded in source documents.

**RA08 Structured analysis and review** Persist findings and report content against a fixed Project revision and regulation evidence set. Capture reviewer amendments and distinguish accepted, rejected and unresolved findings.

**Acceptance** Dev 3 can render the report without generating new conclusions. A new source or Project revision marks affected analysis as potentially stale.

**RA09 Historical theme discovery** Suggest themes from deduplicated incidents using topics, entities, time and market context. Explain membership and source coverage. Let users inspect, rename, adjust, dismiss or promote suggestions; keep existing suggestions stable across reruns.

**Acceptance** No Project is created before a user decision. Promotion creates or links one Project exactly once and retains the theme and incident provenance.

**Handoff** Outputs are versioned regulatory records, ProjectIncident links and Analysis revisions. Comparative trends must use deduplicated events and disclose changes in source coverage. First integration includes one supported finding and one deliberately insufficient evidence case.

# 7 Developer 3 requirements

Owner of shared persistence, retrieval, permissions, record editing and report delivery. Dev 3 implements the physical schema after joint contract agreement. Prioritise storage interfaces first, retrieval second and presentation third.

**DB01 Authoritative storage** Implement PostgreSQL records, object storage references, stable IDs, relationships, migrations and revisions. Preserve original evidence separately from corrections and generated material.

**Acceptance** Incidents, Projects, Regulations, Analysis runs and Reports are distinct records with enforceable references. Schema migration tests preserve existing evidence links.

**DB02 Storage interfaces** Provide validated operations for ingestion, Project revisions, regulatory versions, analysis, review and export. Handle transactions, expected revisions, pagination and structured errors.

**Acceptance** Both other developers can use the same example payloads in local fixtures and integration tests. Invalid references and stale edits are rejected clearly.

**DB03 Hybrid retrieval** Implement keyword and semantic search over incident summaries and evidence passages with access, market, region, type and date filters. Keep regulation and incident retrieval distinguishable.

**Acceptance** Exact names and concept queries work on the benchmark. Results identify source versions and locations; filters remain enforced after candidate merging.

**DB04 Index consistency** Update search after record changes through a reliable queued mechanism. Track indexed revision and failures; rebuild derived indexes without reacquiring source evidence.

**Acceptance** A failed indexing task is retried. The UI exposes pending indexing and an analysis run never claims to include unseen updates.

**DB05 Manual record management** Provide permission controlled add, correct, link, merge, split and archive actions with a reason and edit history. Preserve source snapshots. Use revision checks to prevent one user overwriting another.

**Acceptance** A manual correction persists after reingestion. Conflicting edits require resolution, and reversal creates a new revision rather than erasing history.

**DB06 Access and reproducibility** Enforce role and source entitlements across storage, search, caches and exports. Persist the Project revision, evidence set, retrieval settings and analysis configuration used for each run.

**Acceptance** An unauthorised source cannot appear through search or export. A previous report can be retrieved after current records or models change.

**DB07 Report delivery** Render saved Analysis content into a readable report with source passages, citations, scope, coverage and review status. Provide an initial downloadable HTML report and machine readable JSON; other formats may follow.

**Acceptance** The report introduces no new factual claims. Exports are versioned and carry a report ID, creation date, analysis ID and review state.

**DB08 Operational foundation** Provide configuration, backups, restore procedures, health checks and metrics for storage, search and report jobs. Keep secrets out of stored report content and logs.

**Acceptance** A restore exercise recovers the linked records and permitted source objects. The team can measure retrieval latency and indexing lag during ingestion.

**Handoff** Outputs are stable storage and search interfaces plus reviewable report artifacts. Source management UI belongs to Dev 1 and analysis content to Dev 2, keeping Dev 3's presentation work bounded.

# 8 Shared data contract

The following is the logical contract, not a final SQL schema. Use stable opaque IDs and an explicit schema\_version. Referential integrity and revision history are required. Each nullable fact needs an unknown or review reason where its absence affects analysis. Never substitute the ingestion date for a missing source date.

| **Record** | **Minimum fields and relationships** |
| --- | --- |
| Source | source\_id, name, publisher or authority, source\_type, connector, permitted operations, languages, expected coverage, actual coverage and access scope. |
| Document and version | document\_id, document\_version\_id, source\_id, original URL or file reference, content hash, raw and extracted content references, language, published\_at, retrieved\_at, extraction status and supersession link. |
| Passage | passage\_id, document\_version\_id, exact text or retrievable text reference, page or section location, character offsets where available, language and extraction version. Embeddings reference the passage and model version. |
| Incident and development | incident\_id, version, description, entities, event date or interval, locations, affected markets, risk topics, factual status, source evidence IDs, first\_seen\_at, last\_material\_update\_at and related incidents or developments. |
| ThemeSuggestion | theme\_id, version, title, description, incident revision IDs, membership explanation, markets, periods, coverage, generation settings, suggested or dismissed or promoted state, reviewer and resulting Project link. |
| Project and revision | project\_id, project\_revision\_id, title, objective, questions, owner, bank entities or activities, markets, topics, reporting period, profile settings and membership snapshot. |
| ProjectIncident | project\_id, project\_revision\_id, incident\_id and revision, relevance reason, proposed\_by, link origin, review status and supporting evidence. This is a many to many relationship. |
| Regulation and version | regulation\_id, regulation\_version\_id, authority, instrument type, title, jurisdiction, publication date, effective interval, status, applicability fields, provisions and source evidence IDs. |
| Analysis and finding | analysis\_id, analysis\_revision\_id, project\_revision\_id, as of mode and dates, selected regulation and incident versions, finding IDs, claim evidence links, applicability reasoning, implications, priority, confidence and review decisions. |
| Report | report\_id, version, analysis\_revision\_id, evidence snapshot reference, template version, generated\_at, format, artifact location, review status and access scope. |
| Run and audit event | run\_id or audit\_event\_id, actor, operation, inputs, previous and resulting revisions, idempotency key, timestamps, progress or outcome, reason, failures and correlation ID. |

Store bank entities, market definitions and controlled topic vocabularies as shared reference data. A geography assignment must identify its role: event location, affected market, entity domicile or regulatory jurisdiction. These roles must not be collapsed into one country field.

News can support multiple incidents, and an incident can cite multiple document versions. A report points to a saved analysis; it is an external output with internal metadata and a reproducible evidence record.

# 9 Time geography and record state

## Time semantics

| **Time concept** | **Required behaviour** |
| --- | --- |
| Event and publication | Retain both when known. A later article can report an earlier incident. Unknown dates remain explicit and can be included through a labelled undated filter. |
| Effective period | A regulation version or provision has supported valid\_from and valid\_to values. Define interval boundaries consistently; proposed convention is inclusive start and exclusive end. |
| System knowledge | Record when a version or correction entered the system and when it was superseded. This supports reproducing a previous analysis and manual edit history. |
| Historical knowledge | A claim about what was publicly known at a past date requires evidence of the source version available then. A present day download alone does not establish that historical availability. |
| Query mode | The user selects current research or historical applicability. A known at the time backtest is offered only when the source history supports it; otherwise state the limitation. |

Historical imports use their actual retrieval timestamps while preserving original publication dates. A retrospective analysis may use later evidence, but it must disclose that choice. Never imply a current source snapshot is an exact historical snapshot.

## Markets regions and language

Maintain configurable market to region mappings with a mapping version. Expand APAC or EMEA into the selected market set at query time and save that set with the Analysis run. An incident can affect several markets. The location of an event or publisher does not determine which rules apply to the Project.

Keep the original language and any translation reference. English language material is proposed for the initial evaluation. Broader coverage requires appropriate multilingual retrieval or controlled translations and language specific quality checks; untranslated gaps remain visible.

## Lifecycle separation

* Recency: Latest, Archive or Undated is a view based on the requested window; it is not a deletion or review decision.
* Incident and source review: unreviewed, reviewed, disputed or excluded. A source claim can be disputed without deleting the original evidence.
* Project links: suggested, accepted or rejected. Store the decision and reason independently for each Project.
* Theme suggestions: suggested, dismissed or promoted. Retain the reviewed incident set and resulting Project link; repeat generation must not multiply the same suggestion.
* Analysis: queued, running, partial, failed, draft, reviewed or superseded. Review decisions can also apply to individual findings.
* Ingestion: queued, running, completed, completed with errors, failed or cancelled. Progress includes saved checkpoints and a list of failures.

Manual edits create revisions. A reingestion result must preserve accepted corrections or propose a conflict for review. A source, Project or regulation change flags dependent analysis as potentially stale; previously exported reports remain unchanged.

# 10 Interfaces and dependency management

These are logical operations; the first implementation may use shared Python interfaces or HTTP APIs. Keep their schemas and semantics stable. Contract tests must run against fixtures and the real storage implementation. All mutations carry actor, request ID and relevant access context.

| **Operation** | **Inputs** | **Outputs and guarantees** |
| --- | --- | --- |
| Create ingestion run | Source IDs, period and date basis, markets, mode and idempotency key. | run\_id, accepted scope and job status. Duplicate submissions do not create duplicate work. |
| Save document version | Source identity, original location, hash, text reference, metadata and extraction status. | Stable document and version IDs; new, unchanged or conflict outcome; validation errors. |
| Save incident revision | Incident facts, evidence IDs, related developments and expected revision when editing. | Incident and revision IDs plus conflict or review state. Source support remains linked. |
| Save Project revision | Project scope, questions, membership changes, link decisions and expected revision. | Project revision ID and membership snapshot. Concurrent edits cannot silently overwrite each other. |
| Review theme suggestion | Theme revision, reviewer decision, edited scope and incident set, target Project if applicable and idempotency key. | Saved decision and Project link when promoted. A suggestion alone creates no Project; replaying promotion creates no duplicate. |
| Save regulation version | Instrument identity, status, applicability, effective interval, provisions and evidence IDs. | Regulation and version IDs; validation or unresolved metadata flags. |
| Search evidence | Query, source and domain filters, market or region mapping, time mode, access scope and result limit. | Ranked passages, incident or instrument links, source versions, citation locations and freshness or coverage warnings. |
| Start analysis | project\_revision\_id, regulatory scope, as of dates, research settings and budget limits. | analysis\_id and job state. The resolved regulation versions and evidence set are saved with the run. |
| Save analysis or review | Analysis findings, claim evidence links, priority reasons, confidence, reviewer decision and expected revision. | Analysis revision ID, validation issues and review state. Unsupported references are rejected. |
| Export report | analysis\_revision\_id, format, template and permitted audience. | report\_id, artifact reference and review label. Export does not rerun or invent analysis. |

## Shared contract rules

* Commit versioned schemas and examples in a shared contracts module. Use additive compatible fields for routine changes and a migration plan for breaking changes.
* Dev 3 owns physical migrations and persistence. Dev 1 owns extraction field semantics; Dev 2 owns Project, regulation and assessment semantics. Review changed contracts together.
* Provide structured validation, conflict, access denied, partial result and retryable failure responses. Unknown evidence is a supported outcome, not an empty success.
* Persist change events reliably with record writes so index jobs can retry. Expose pending index revisions and analysis evidence cutoffs to callers.

# 11 Product screens and report requirements

## Required user surfaces

| **Surface** | **Owner** | **Required behaviour** |
| --- | --- | --- |
| Sources and ingestion | Dev 1 | Configure sources; select markets and periods; start, inspect, retry or cancel jobs; view source coverage and failed ranges. |
| Incident library | Dev 3 with Dev 1 | Search Latest, Archive and Undated; inspect sources and developments; correct facts; merge or split with history. |
| Themes and Projects | Dev 2 with Dev 3 | Review and promote suggested themes; create Projects directly; edit scope and incident membership; save revisions; start analysis. |
| Evidence and analysis review | Dev 2 | Inspect claims, original passages, applicability, priority reasons, missing evidence and reviewer decisions. |
| Reports | Dev 3 | View saved analysis, distinguish draft and reviewed versions, inspect citations and download a report snapshot. |

Use plain language in user flows. Show unknown, incomplete, indexing pending and source unavailable states explicitly. The interface must support keyboard navigation and must not rely on colour alone to show review status or priority.

## Report content

* Project title, objective, revision, owner, selected markets or region mapping, reporting period and analysis as of mode.
* Executive overview of relevant developments and the reasons for the proposed priorities. Report only topics that were actually assessed.
* Findings with the underlying incidents, supported facts, regulatory versions and provisions, applicability explanation, risk implications and proposed audit questions.
* Priority and evidence confidence as separate fields, including the reason for each and any missing internal evidence.
* Historical comparisons with their period and coverage basis. Article counts must not be represented as incident counts.
* Evidence appendix with source titles, publishers, dates, URLs or accessible file references, passage locations and version identifiers.
* Coverage summary, failed sources or periods, disputed claims, unresolved questions, reviewer decisions, generation date and report revision.

## Priority and confidence

Proposed initial priorities are High, Medium, Low and Unrated. Use Project exposure, potential impact and urgency, and show a written explanation. High indicates a reason for prompt auditor attention; it is not an automatic finding of noncompliance. An unknown exposure or missing evidence must remain visible.

Evidence confidence reflects source authority, direct support, corroboration, contradictions and applicability certainty. It is not a calibrated probability unless a separate validated method establishes one. The reviewer can change a rating with a recorded reason.

The first report formats are proposed as downloadable HTML and JSON. PDF or DOCX export can be added after core evidence and review behaviour works. Automatic email delivery, regulatory submissions and changes to bank controls are outside the first release.

# 12 Nonfunctional requirements

**NF01 Access boundaries** Apply role and source access controls before returning candidates, passages, cached content or exports. Separate public research inputs from confidential bank context. External services receive only approved query content.

**Acceptance** Permission tests cover direct record access, search, cached answers and report downloads. Production identity integration is a bank deployment condition.

**NF02 Evidence integrity** Preserve content hashes, version references and author or reviewer events. Treat source text as untrusted data. Record models, prompts and retrieval configurations used by analysis.

**Acceptance** A source correction cannot silently rewrite an old report. Source instructions cannot change tool permissions or analysis policy.

**NF03 Recovery and consistency** Make ingestion and indexing retryable and resumable. Protect manual revisions from lost updates. Back up records and source objects and test restoration of their relationships.

**Acceptance** Failure injection shows no duplicate logical records, silent lost corrections or falsely complete jobs. A documented restore exercise succeeds.

**NF04 Observable operation** Track source coverage, extraction errors, queue age, ingestion throughput, indexing lag, search latency, model usage and analysis failures. Keep logs correlated with run IDs.

**Acceptance** A developer can identify the failed source or stage from the run record. Logs avoid unnecessary full source content, secrets and sensitive Project details.

**NF05 Cost and workload control** Configure source limits, retry limits, concurrency and analysis budgets. Keep long historical jobs from exhausting resources used for current queries. Record actual compute and service usage where available.

**Acceptance** A backfill and an interactive search can run together under the agreed benchmark; budget exhaustion produces a partial result and an explicit reason.

**NF06 Deployment readiness** Before bank use, establish approved hosting, encryption, secret management, identity integration, high availability, restore objectives, retention policy and content entitlements with the bank owners.

**Acceptance** The deployment review records evidence for these requirements. The academic prototype is not labelled bank production ready without that review.

## Capacity planning

The 20 to 30 year goal describes historical coverage, not a measured document count or a legal retention period. Estimate volume per source, average passages per document, growth, languages, concurrent users and update frequency before selecting a full scale search deployment.

Illustrative sizing: 10 million documents with 10 passages each create 100 million passages. At 768 float32 values per embedding, raw vectors occupy about 307 GB in decimal units before indexes, replicas, text or backups. This is a planning example, not a forecast or a required embedding model.

Dev 3 leads a measured comparison of the initial PostgreSQL retrieval implementation and a dedicated search service when warranted. Dev 1 supplies ingestion workload; Dev 2 supplies relevance judgements and time or applicability test cases. Keep engine selection behind the shared retrieval contract.

# 13 Acceptance and evaluation

All functional checks below are required for the first integrated release. Numerical quality and performance thresholds are proposed starting targets; the team must record the corpus, hardware, model, index settings and concurrency used to evaluate them.

| **Test** | **Owner** | **Pass condition** |
| --- | --- | --- |
| AC01 Ingestion replay | Dev 1 and 3 | Repeat the same import and retry a failed batch. No duplicate document versions or incidents appear, and failures retain their source references. |
| AC02 Historical import | Dev 1 | An old article imported today retains its historical publication and event dates. It does not become latest solely because it was discovered today. |
| AC03 Duplicate coverage | Dev 1 | Two articles about one event map correctly; an unrelated case involving the same bank remains separate. A user can reverse an incorrect grouping. |
| AC04 Project relationship | Dev 2 and 3 | The same incident can link to two Projects with different relevance reasons. Analysis uses the saved scope and membership revision. |
| AC05 Regulatory history | Dev 2 | A known amendment case selects the supported version for the requested date and cites its provision. Unknown effective dates are flagged. |
| AC06 Regional retrieval | Dev 2 and 3 | Country and APAC or EMEA filters match the configured mapping and geography roles. The saved query records the actual market set. |
| AC07 Manual corrections | Dev 1 and 3 | A corrected fact survives reingestion. A conflicting edit is detected. Search refreshes or visibly reports that indexing is pending. |
| AC08 Evidence and uncertainty | Dev 2 | Every material claim has a resolving citation and is checked for support. Contradictory and insufficient evidence cases produce qualified or unresolved findings. |
| AC09 Report reproducibility | Dev 2 and 3 | Changing a Project, source or regulation produces a new analysis revision or stale flag. An earlier exported report remains retrievable unchanged. |
| AC10 Access and failure | All three | An unauthorised source is absent from search and export. A worker failure can be recovered. Instructions in source content do not control the workflow. |
| AC11 Hybrid creation | Dev 2 and 3 | Generate a theme without creating a Project. Review and promote it; replaying promotion does not duplicate the Project. Direct manual creation also works. |

## Proposed quality benchmark

Create at least 40 manually labelled questions or scenarios across current and historical records, exact names, concept queries, country and regional scope, duplicates, missing dates and insufficient evidence. Include real public documents for relevance and grounding; label synthetic fixtures clearly for controlled edge cases.

Proposed targets: recall at 20 of at least 90 percent for labelled relevant evidence; at least 80 percent relevant results in the first five; at least 95 percent supported material claims after the verification stage. All citations must resolve to the correct saved version, and all critical applicability or effective date fixtures must pass. No observed unsupported critical claim can remain in the release report set.

Compare keyword only, semantic only and hybrid retrieval using the same questions. Compare research time against a manual baseline on the same tasks, while measuring review effort and errors. Targets describe the benchmark, not a guarantee about every future answer.

# 14 Delivery plan and team coordination

## First integration sequence

| **Milestone** | **Parallel work** | **Exit condition** |
| --- | --- | --- |
| M0 Shared foundation | All agree domain classes, field meanings, permissions and contracts. Dev 3 creates storage interfaces; Dev 1 and 2 provide realistic example records. | Schemas, fixtures and interface tests are committed. Each module can work against the agreed examples. |
| M1 First complete flow | Dev 1 ingests one news source. Dev 2 creates themes, ingests one regulatory source and analyses a reviewed Project. Dev 3 supplies storage, retrieval and a report view. | Both manual creation and reviewed theme promotion produce Projects that can be analysed and reported with exact evidence links. |
| M2 Correctness and review | Add history, duplicate resolution, manual corrections, review decisions, date and geography tests. | AC01 to AC11 pass. Missing evidence and partial jobs are visible to users. |
| M3 Archive and scale | Expand connectors and historical ranges; benchmark retrieval and concurrent ingestion; decide search deployment. | Measured coverage and workload results support the next archive stage. No claim of complete coverage is inferred from successful ingestion. |
| M4 Bank readiness | Complete deployment, identity, entitlements, recovery and any internal evidence integration with bank owners. | Documented operational and governance acceptance for the intended environment. |

Timebox the initial contract workshop to one or two working days. Integrate M1 early rather than completing each layer in isolation. Calendar dates and staffing capacity must be agreed by the team; these milestones are not a committed bank deployment schedule.

## Working agreements

* Use one repository with clear module ownership: ingestion and sources for Dev 1; regulations, Projects and analysis for Dev 2; storage, retrieval and report delivery for Dev 3.
* Keep schemas, representative fixtures and contract tests in a shared module. Domain owners propose semantic changes; Dev 3 reviews and implements migrations.
* Make the first storage interface available before a full search cluster is ready. Other developers use the same contracts against fixtures while implementation continues.
* Dev 2 supplies structured report content. Dev 3 templates and exports it. Dev 1 owns source management and ingestion UI, preventing all interface work from falling on Dev 3.
* Run a small end to end test whenever contracts change. Review open questions, coverage and failed evidence cases during regular integration sessions.

## Proposed performance baseline

Initial benchmark proposal: 100,000 source documents and approximately 1 million passages, with 10 concurrent search users and an active ingestion worker on documented hardware. Target a 95th percentile stored evidence search latency of 5 seconds or less and return a manual job ID within 2 seconds. Measure indexing delay separately and always display pending updates. These figures require team agreement and do not establish full archive capacity.

Before archive expansion, benchmark a representative projected workload and report latency, retrieval quality, ingestion throughput, memory, storage, recovery and cost. Record any unavailable historical data separately from infrastructure performance.

# 15 Decisions and assumptions

The project creation model is confirmed below. Other items have a working default or a proposed owner and must remain visible in the backlog. A proposed value is not an approved bank requirement.

| **Decision** | **Working position** | **Owner and resolution point** |
| --- | --- | --- |
| OD01 Project creation | Confirmed hybrid: users create Projects directly or promote system suggested themes after review. Preserve suggestion provenance; no automatic Project creation. | Product owner selected this model. Dev 2 owns behaviour and Dev 3 owns persistence; verify at M1. |
| OD02 Pilot scope | Propose AML/CFT customer due diligence with Singapore and Hong Kong. Keep additional topics and regions configurable. | Product owner and class sponsor or mentor before the evaluation set is fixed. |
| OD03 Risk area breadth | Class notes mention five risk areas, while later proposals narrow the pilot. Do not label unassessed areas low risk. | Product owner confirms required presentation breadth and acceptance criteria. |
| OD04 Data sources and rights | Support curated and broad coverage. Exact publishers, archive access, permitted storage, embedding and export rights are not yet agreed. | Product owner and source or licensing owner before each archive connector is enabled. |
| OD05 Bank context | Configure legal entities, activities, markets and regional groupings. No specific production cloud or internal data integration is assumed. | Product owner and bank technology owner before deployment design is final. |
| OD06 Models and search | Local or hosted models are implementation options. PostgreSQL plus object storage is the proposed foundation; search engine selection follows measurement. | All developers with the bank technology owner before production rollout. |
| OD07 Scale and service levels | Document and passage volumes, concurrency, response targets, recovery objectives and budget remain to be sized. Initial numerical targets are proposals. | Dev 3 leads workload sizing with Dev 1, Dev 2 and product owner at M3. |
| OD08 Review and priority | Use a transparent priority rubric and separate confidence. Confirm reviewer roles and the status needed to issue a reviewed report. | Audit or risk reviewer with Dev 2 before reports are relied on operationally. |
| OD09 Languages and history | Begin evaluation with English material. Define further language coverage, OCR processing and access to missing historical regulatory versions. | Product owner with Dev 1 and Dev 2 before broad regional coverage claims. |
| OD10 Schedule and formats | Milestones are sequenced without a delivery commitment. HTML and JSON are the proposed initial report exports. | Team agrees calendar, available effort and export priorities at kickoff. |

## Dependencies that can limit delivery

Historical coverage depends on the available source records and access arrangements. LSEG distinguishes Reuters archives back to 1996 from the history available for other sources. Singapore Statutes Online states that pre 1998 versions are available only where digital records exist. Track these gaps explicitly rather than converting them into a software completion claim. [T6, T7]

Bank deployment also depends on identity, hosting, reviewer availability and any internal evidence access. Developers can complete and evaluate the external research workflow while those integrations remain separate milestones. A complete database cannot alone establish complete regulatory coverage or a bank compliance conclusion.

# 16 Sources and design references

Product direction is taken from the project discussion through 11 October 2026, including the latest domain flow supplied by the product owner. Earlier proposals and class notes provide context; the later requirements for manual control, regional queries and a scalable historical archive take precedence.

## Project materials

**C1** 8 October SMU.pdf, pages 1 and 2. Class clarifications on public data, evidence, emerging risks, period specific conclusions and evaluation.

**C2** NTU UOB lesson Dr Ng.pdf, pages 3 to 5. Auditor workflow, source and relevance checks, confidentiality, review and initial topic scope.

**C3** YTP-AIF DBS Project.docx. Earlier external driver research proposal and jurisdiction or topic restrictions.

**C4** YTP-AIF DBS Project.pdf, pages 1 to 5. Mira proposal, approved source retrieval, original links, dates, coverage and a three person implementation.

**C5** DBS Annual Report 2025.pdf. Institution specific risk context; it is not a complete cross jurisdiction regulatory inventory.

**C6** AI\_in\_Technology\_and\_Operations.pdf. Class context for measurable value, human oversight, runtime controls and evaluation.

**C7** Monograph MAS Approach to Resolution of FIs in Singapore September 2026.pdf. Supporting policy context; applicability and current obligations require their own authoritative source checks.

## Technical and historical source references

**T1** [SQLite guidance on appropriate uses](https://www.sqlite.org/whentouse.html). Concurrency and shared database considerations.

**T2** [PostgreSQL concurrency control](https://www.postgresql.org/docs/current/mvcc-intro.html). Concurrent access and database consistency.

**T3** [pgvector documentation](https://github.com/pgvector/pgvector). Vector retrieval, filtering, hybrid search and scaling options.

**T4** [OpenSearch hybrid search](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/). Keyword and semantic retrieval, fusion and filtering.

**T4a** [OpenSearch cluster design](https://docs.opensearch.org/latest/tuning-your-cluster/). Distributed search and ingestion considerations.

**T5** [Cloud Storage object versioning](https://docs.cloud.google.com/storage/docs/object-versioning). Example of versioned object storage behaviour, not a selected cloud provider.

**T6** [Singapore Statutes Online FAQs](https://sso.agc.gov.sg/Help/FAQ). Historical versions, current status and limits on pre 1998 digital availability.

**T7** [LSEG News Service documentation](https://developers.lseg.com/en/product/news/news_service_rdp). Archive coverage and differences between API access and historical archives.

**T8** [Exa Search API documentation](https://exa.ai/docs/reference/search). An optional discovery integration; the domain and storage contracts remain independent.

Technical links were checked during the project discussion on 11 October 2026. The PRD specifies product behaviour and proposed engineering choices; each implementation must verify provider capabilities, source terms and the deployment requirements that apply at the time of use.