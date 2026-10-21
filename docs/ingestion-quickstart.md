# Nat's local ingestion workbench

This implements a local slice of IN02/IN03/IN07 and AG06/AG12: HTML and PDF extraction, resumable batch attempts and a Streamlit source inspector. It needs no Supabase or LLM credentials. Run commands from the repository root on macOS/Linux with Python 3.10+.

## Setup and open the screen

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://127.0.0.1:8501 and expand **Try the workflow** in the sidebar and choose **Load synthetic demo**. It contains invented HTML, a two-page text PDF and an image-only scan. Expect **2 saved, 1 failed**: the scan intentionally needs OCR. The demo is not regulatory evidence.

Use **Add sources** to upload up to 20 PDFs with their original MAS URLs, or paste one URL per line. Confirm source permissions, then start extraction. The **Ingestion queue** updates once a second, shows progress and attempt history, and offers **Retry this item** or **Resume / retry remaining items**. Saved items are skipped. Extraction runs in one background worker while the server stays running; after a server restart, resume unfinished items explicitly.

The **Library** searches saved titles, URLs and extracted wording across submissions. Open a source to inspect the original PDF beside page-filtered passages, exact character offsets and unknown publication dates. The PDF viewer scrolls independently of the passage filter. HTML originals appear as literal source code. Original downloads and evidence JSON exports are available; file integrity is checked before preview. Loading the demo again reuses its existing run. A saved extraction is not a verified claim or approval to publish a report.

The app binds to localhost and has no authentication. Keep it local; workspace access controls must be implemented before shared hosting. `MIRA_DATA_DIR` optionally changes the inspector's data directory; point the CLI's `--output-dir` at the same directory.

## Import one PDF or HTML file

```sh
python -m mira.ingest \
  --url https://www.mas.gov.sg/fixtures/synthetic-notice.pdf \
  --pdf-file tests/fixtures/synthetic_notice.pdf --fixture

python -m mira.ingest \
  --url https://www.mas.gov.sg/fixtures/synthetic-html \
  --html-file tests/fixtures/mas_notice.html --fixture
```

For a real, permitted local file, supply its original MAS URL and omit `--fixture`. Local imports are labelled `local`; live fetches are `live`. Neither implies independent verification of provenance. The CLI prints the saved bundle path. Single-file bundles are usable handoff files; the library lists outputs associated with runs, so use the upload form or a batch manifest for files you want to inspect in the UI.

PDF extraction preserves physical, one-based page numbers, and each passage stays within a page. Character offsets refer to the complete saved extracted text (exclusive end); pages are separated by two newlines. It records the parser version and raw-file hash. PDF creation/modification metadata is never treated as publication time. Pages with fewer than 40 non-whitespace characters are flagged for visual review/OCR, not definitively classified as scanned. An image-only or unreadable PDF fails instead of becoming empty evidence. Encrypted files fail with an actionable message; no passwords are stored.

`complete` means the PDF yielded substantial text on every page. It does not establish correct reading order, table extraction, factual accuracy or historical coverage. HTML remains `partial` because linked PDFs and page completeness have not been assessed.

## Start a batch and resume it

```sh
python -m mira.batch start tests/fixtures/batch.json --max-items 1
python -m mira.batch resume RUN_ID
python -m mira.batch resume RUN_ID --retry-failed
```

Copy the run ID printed by `start`. `--max-items` pauses after that many attempts and provides a reproducible checkpoint test. Ctrl-C records cancellation; resume that same run to continue. An interrupted in-flight attempt is marked interrupted when resumed. No attempt is automatically retried in a loop.

Manifest paths are relative to the manifest file. Example:

```json
{
  "schema_version": 1,
  "items": [
    {
      "id": "notice-example",
      "kind": "pdf",
      "path": "notice.pdf",
      "url": "https://www.mas.gov.sg/regulation/notices/notice-626",
      "fixture": false,
      "passage_size": 1000
    }
  ]
}
```

Kinds are `html`, `pdf` and `url`. A `url` item has no local path and accepts HTML or an application/pdf response through the guarded fetch adapter. IDs must be unique. The tool accepts up to 100 items and passage sizes of 50–4000 characters. Local input bytes are pinned when the run starts. A changed file cannot silently resume as the previous source: start a new batch to capture it as new input. Missing files are recorded as item failures; supply the missing file and retry.

Starting the identical manifest reuses its run. Use `start MANIFEST --refresh` for a fresh observation of unchanged input specifications, such as checking a live URL again. Successful snapshots are deduplicated within the output directory. Each item gets at most one attempt per invocation. A process lock rejects concurrent writers to the same run.

Batch exit codes: 0 for completed or deliberately paused, 1 for failed items/invalid input, 130 for user interruption. A `completed_with_errors` run may still have usable saved evidence.

## Live HTML fetching

```sh
python -m mira.ingest --url https://www.mas.gov.sg/regulation/notices/notice-626
```

Only HTTPS URLs on `www.mas.gov.sg` and `mas.gov.sg` are enabled. The adapter checks robots.txt, delays requests, validates redirect targets, rejects non-public DNS answers and pins the validated address for TLS. Unknown robots policy, HTTP failures and recognised service-unavailable/challenge pages fail visibly. The previous live MAS smoke test returned such a service-unavailable page; no browser challenge bypass is implemented.

The UI and batch URL adapter support direct PDF responses up to 2 MB; upload larger permitted PDFs locally (up to 10 MB). The single-source CLI URL mode remains HTML-only. Additional source domains and configurable source approvals are not implemented. The host restriction is not a licensing decision: check publisher permissions before retaining or exporting real content. This tool does not crawl links or run a web-search API.

## Storage and recovery

All output is ignored by Git under `data/ingestion/`:

- `uploads/`: content-addressed uploaded PDFs; filenames are never used as paths.
- `intake/`: generated submission manifests. Identical submissions reuse the same run; use the CLI `--refresh` option for a new live observation.
- `raw/`: content-addressed local input snapshots (live HTML is the decoded/re-encoded text, not original transport bytes).
- `HASH.json`: immutable extraction envelopes, with content hash, metadata and passages.
- `runs/RUN_ID.json`: atomically replaced checkpoints containing inputs, attempts, errors and bundle hashes.
- `runs/RUN_ID.lock`: process locks; an existing lock file alone does not mean a process is running.

If a process stops after saving evidence but before recording success, resume deduplicates the existing snapshot. The inspector validates bundle hashes before display. Changed/corrupted evidence is reported; do not edit saved envelopes to correct facts. Local snapshot paths are absolute, so moving the output directory requires care. These are development staging records, not a substitute for the shared Supabase database or its audit trail.

Limits: 2 MB live/local HTML, 10 MB local PDF, 200 PDF pages, 2 million extracted PDF characters, and 60 seconds per batch item. Each batch item runs in a separate process. This bounds duration but is not an OS memory sandbox; use trusted public documents in this prototype. Direct single-file extraction has no subprocess timeout. Batch processing is sequential. UI extraction and retries run in a background worker, with progress read from atomic checkpoints.

## Validation

```sh
python -m unittest discover -s tests -v
python -m pip check
```

Tests cover page/character citations, unknown dates, scan/encryption failures, mixed text/blank PDFs, URL and DNS restrictions, robots responses, redirects, immutable replay, interruption/resume, explicit retries, input changes, concurrent-run rejection, corrupted bundles, upload validation, targeted retries, snapshot integrity and UI filtering. Source content is rendered literally in the passage viewer and is never executed.

The checked-in PDF fixtures are synthetic. `scripts/make_pdf_fixtures.py` regenerates them with the optional development dependency `reportlab`; normal usage and tests need only `requirements.txt`.

## Supabase handoff and remaining work

The staging JSON is not a direct insert payload. The next shared interface must resolve `workspace_id` and `source_id`, validate the initiating actor, assign database IDs/version numbers, and save document/version/passages in one transaction. The existing schema deduplicates versions by `(document_id, content_sha256)`; metadata-only changes still need an agreed persistence policy. Local envelopes retain those observations separately.

Ingestion requires curator/admin permissions; authenticated search requires workspace membership. Do not use elevated credentials to bypass a missing role. Saai owns migrations and shared persistence, while Nat owns extraction semantics. This work changes no migrations and writes nothing to Supabase.

Still separate: OCR, source discovery, incident construction, embeddings, formal curator/reviewer decisions, source/year coverage assessment, the agent workflow and production hosting. Inspecting or downloading evidence does not mark a report reviewed.
