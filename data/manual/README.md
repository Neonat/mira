# Documents imported by hand

Some sources refuse automated access, and Mira does not work around that. Since 26 October 2026 `www.mas.gov.sg` serves a block page to Mira's client. Singapore Statutes Online, HK e-Legislation, FATF and BIS also refuse automated requests. For these sources, download the documents in your own browser and import them here.

Everything in this folder except this README and `manifest.example.csv` is ignored by git, so downloaded documents are never committed. MAS's terms restrict redistribution (see the [approved sources](../../docs/mira_approved_sources.md)).

## 1. Download

Put each source's files in its own folder, for example `data/manual/mas/`. Save each document as a **PDF** (the MAS PDF itself) or an **HTML page** (in the browser, File → Save Page As → "Web Page, HTML Only"). Keep the address the document came from: Mira cites that URL in its reports.

Good MAS documents to start with, for the AML/CFT brief:
- MAS Notice 626 and its latest amendment
- the Guidelines to Notice 626
- AML/CFT enforcement actions and media releases in the period
- AML/CFT circulars and consultation papers in the period

## 2. Import

One file:

```sh
.venv/bin/python -m mira import mas data/manual/mas/notice-626.pdf \
  --url https://www.mas.gov.sg/regulation/notices/notice-626 --title "MAS Notice 626" --published 2025-06-30
```

Several files: copy `manifest.example.csv` into the folder as `manifest.csv`, fill in one row per file, then run:

```sh
.venv/bin/python -m mira import mas --manifest data/manual/mas/manifest.csv
```

In the manifest, `file` is relative to the manifest, `url` is required, and `title` and `published` (YYYY-MM-DD) may be left blank. Give `published` whenever you know it: a scout only picks up a stored document if it was published in the run's period or was imported by hand, and the date is what places it on the report's timeline.

## What the import checks

- The URL must be `https` on the source's own site (for MAS, `www.mas.gov.sg`), so a citation cannot point anywhere else.
- Only PDF and HTML files up to 15 MB. A saved copy of the block page is refused.
- You must be a curator or admin in the workspace (the command runs as `MIRA_DEV_EMAIL`).

The command prints one line per file: `saved`, `unchanged` (the same file was imported before) or `failed`, with the reason. Each import is recorded as an `ingestion_runs` row with mode `manual_upload`.

Re-importing a changed file at the same URL creates a new version; the old one is kept. Imported passages are marked "Imported by hand" in the report's evidence appendix. Coverage rows that rest on them say "from documents imported by hand".

Sources that permit only `metadata` (SSO, HK e-Legislation, FATF, BIS) save the document's details but no text, so nothing from them can be cited until their terms are reviewed for `store_text`.
