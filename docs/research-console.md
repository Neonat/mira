# Research console and temporary keys

Audience: pilot analysts and reviewers using Mira, and the developer operating a local demonstration.

## Demo timing and normal research

The user clarified on 10 November that the demonstration must finish within five
minutes, while normal research may take substantially longer. These are separate
acceptance targets. The demo target must not become a blanket timeout for full
acquisition, passage analysis or verification.

Normal requests already expose **Advanced limits → Maximum run time (minutes)**,
from 1 to 240 minutes, with a 15-minute default unless configured otherwise.
Analysis depth is separately selectable from 1 to 64 batches. Choose time and
depth for the requested scope while preserving the USD allowance, source
restrictions and truthful coverage. A longer ceiling does not guarantee complete
coverage. The previous ten-minute HK validation ceiling was a test-specific
coordinator choice, not a user requirement for normal research.

Useful fresh report generation within five minutes remains unproven. A demo must
state its source/date scope and whether acquisition or an existing archive was
used; previously generated output must be identified as such. This timing
clarification does not authorize another paid validation.

Analysts sign in, choose **Research**, set markets and dates, restrict the approved source set, choose discovery/browser and archive-search options, and set a USD allowance. Advanced controls set documents, active run time and whole-passage analysis batches. **Review research** shows the submitted request and current price units before temporary masked keys are entered. The configured model profile is unchanged. Plan approval is optional; when selected, acquisition waits for review and fresh keys.

**Runs** shows steps, source and passage coverage, known estimated charges, unknown reservations and pending admissions. **Reports & review** retains evidence navigation and finding-level sign-off. New console reports include methods and cost estimates in the coverage appendix. **Country methods** shows approved engineering comparisons separately from workspace evidence. The dedicated local sample is visibly synthetic; its one fact is not a measured Hong Kong result.

## Local service setup

Keep the existing Supabase database, Auth, REST and gateway running. Apply all local migrations, including `20261110160000_mira_byok_resources.sql`; do not reset an evidence database. Existing local Auth accounts work without buying a hosted Supabase plan. The worker-only database credential remains separate from the anon key and must never be passed to Streamlit.

Start the explicit local broker on the same trusted machine as the UI and worker:

```sh
python -m mira broker --directory /tmp/mira-byok-local
```

Use a new short directory. The broker creates a private directory, client socket, worker socket and capability file. Provider keys stay in memory; the capability file contains only a random worker-service credential. File permissions separate ordinary access, but processes sharing this operating-system identity remain trusted. Multi-machine hosting requires a separately designed secret service; this prototype does not provide one.

Configure `MIRA_BROKER_SOCKET` with the printed client socket for the UI. Configure `MIRA_BROKER_WORKER_SOCKET` and `MIRA_BROKER_CAPABILITY_PATH` only for the trusted worker. Set `MIRA_ENABLE_BYOK_RUNS=1` explicitly in both processes to enable paid launch. Template/demo installations keep it off. Existing source and global Exa/browser/hybrid flags still restrict capabilities; a key grants no new source access. Start a worker only for an explicitly approved research session.

The UI needs the existing Supabase URL/anon key, workspace slug, role-model names, capability flags and client socket. Do not inherit provider keys, database credentials, storage upload credentials or the worker capability into that process. The separately managed CLI retains operator credentials for authorized operator runs.

## Key and allowance lifetime

- A pending lease belongs to one signed-in user, workspace and queued run; it expires after at most 60 minutes. The trusted worker claims it once after checking current access.
- No provider key enters the run record, report, rate metadata, command arguments, environment files or logs. Errors use safe operational text. Python memory is released; cryptographic memory zeroisation is not claimed.
- Completion, failure, cancellation and plan pauses discard keys. Missing or restarted broker state requires fresh entry. Cancelling an already dispatched request cannot undo that provider charge.
- Approval continuation uses fresh keys and current prices while retaining prior estimated charges, unknown/pending reservations, token consumption and active elapsed time. Waiting for a human is excluded from active time. A new rerun gets a new allowance and fresh credentials.
- The worker journals conservative pending consumption before dispatch. A crash or failed settlement write leaves that reservation charged as uncertain. Loss of the usage journal stops further calls; requests are never retried using operator keys.

## Prices and comparisons

Validated first-party prices live only in memory. Current support covers the existing `gpt-5.4`/`gpt-5.4-mini` role profile, optional `text-embedding-3-small` and URL-only Exa Auto search. A different or ambiguously priced model fails closed. Cached-input discounts are not assumed; applicable context premiums and output caps are reserved conservatively. Unknown costs never become zero.

Model, embedding and Exa calls share the Decimal allowance and downstream reserve. HTTP/browser acquisition has no model-provider API fee in this ledger; infrastructure, tax and other external charges are outside it. Recorded amounts are public-price estimates, not account invoices or promises about discounts/credits. The allowance and aggregate usage/estimated charges persist; no rate catalogue is retained or used to reprice historical reports.

Hong Kong has a measured 153/153-passage index and six unlabelled archive questions; latency differs, but relevance superiority is unproven. Its historical research report has 19 verified facts with 6/18 acquisition and 5/18 citation benchmark coverage. Australia’s full PDF/HTML comparison and the tested UAE federal direct route support a mixture of acquisition methods. Exa discovery, publication acquisition and archive ranking perform different jobs. Storage size/cost and causal method quality comparisons are not yet established. Full permitted evidence stays in PostgreSQL, with optional rebuildable pgvector indexes. MAS, Malaysia and DFSA remain disabled; CBUAE external embedding remains disallowed under the current grant.

## Validation boundary

Automated validation uses a real local database and private broker with scripted providers and a fake web, including approval continuation and report generation. Actual local Auth ownership/refusal is checked separately. No new paid model, embedding or Exa research request is included. A fresh bounded real-country validation and human relevance labels remain separate work before claiming improved research coverage or a quality winner.
