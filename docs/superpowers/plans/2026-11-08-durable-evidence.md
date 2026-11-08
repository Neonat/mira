# Durable Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. No recursive delegation; one writer per file.

**Goal:** Protect complete evidence and reports against local-file loss with permission-controlled private storage, consistent backup/restore, and a reviewable quality-validation preflight.
**Architecture:** Pure object/package adapters are separate from coordinator-owned worker, database, CLI and authenticated UI integration. Storage identity and RLS preserve evidence bindings; native database snapshots carry all relational facts.
**Tech Stack:** Python, PostgreSQL/Supabase Storage, existing authenticated Streamlit app, local scripted/HTTP/PostgreSQL/Chromium fixtures.
**Spec:** docs/superpowers/specs/2026-11-08-durable-evidence-design.md

## Global constraints

MAS remains disabled. No role-model/source-grant changes, historical report rewrites, paid calls or remote migration/deployment. Credential dialogs write ignored0600.env only; anon/app credentials never become worker upload credentials. One final full suite after integrated scoped checks, repeats only for changed code/failures.

## Review focus

Current grant revocation must block direct bucket reads, not just UI actions. Upload retries cannot overwrite immutable content or declare missing/corrupt objects durable. Backups must pair relational state and referenced bytes from the same snapshot. Restore cannot overwrite a shared database or accept a partial/tampered package. Live-validation preparation must not silently invoke a provider.

- [x] Pure private object adapter: bounded immutable put/get, digest/size/identity and secret-safe errors; scoped red/green.
- [x] Pure recovery package: complete dump+referenced-object manifest, verify-before-write and malformed/corrupt/symlink cases; scoped red/green.
- [x] Coordinator storage policy/reference migration, original/report worker integration and authenticated access/failure retry; local RLS and real HTTP/SDK fixture checks.
- [x] Consistent database dump, safe local recovery command and a restore drill preserving A/B/C passages, original bytes, report HTML and frozen review identities.
- [x] Offline quality preflight/blinded precision/comparison, no provider calls; identify the concrete bounded run for later approval.
- [x] Independent focused reviews resolved; complete local PostgreSQL/Chromium suite939passed+8subtests,no skips,64.05s. Hosted deployment/live checks remain separately scoped.
- [x] Implementation240aef8 pushed; PR13 opened on PR12, mergeable and unmerged. Documentation-only status follows the tested implementation.
