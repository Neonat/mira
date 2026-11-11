# Latest bounded AU/UAE checkpoint

Objective: push/check PR13 first, keep local DB running, execute one additional bounded AU/UAE test, update PR13 and share reports. Base SHA `86f2bfe`; no runtime or model/effort changes this task. Coordinator owns integration/docs/push; evaluator's bounded audit was read-only. Old reports remain unchanged.

Preflight: push up to date; GitHub MERGEABLE/CLEAN and local merge-tree passed. Ewen/PR6 ancestor retained.23 focused checks passed in 0.21 s; code-identical full suite remains 1075 + 8/no skips/70.34 s. No repeated full proof run. Source permissions/MAS disablement preserved.

Run `5fad1aa1-e8bc-41a9-9f3d-d5ed223a29c0`: normal pipeline **partial after 821.877 s**, report `6ab90880-eb7c-468a-bb9d-3a2f65e85d85`. Detached supervisor and scoped caffeinate kept local DB available:164 successful five-second checks, zero failures, same postmaster/container/mounts. DB left running with existing unless-stopped policy. No reset/restore/restart or paid continuation/replacement. The supervisor ends with the run; no recurring research was scheduled.

Same caps:8 representations/600 k tokens/25 min/4 Exa/10 embedding + 100 k bytes/0 gap. Analysis profile:4 x 3 passages/6000 chars/8192 output/120 s, protect 60000 tokens/360 s. Runtime production analysis default 16384 output was not validated by this smaller profile. Malaysia/DFSA/MAS disabled in dedicated workspace, zero MAS versions; only 3 approvedprofiles active. Hybrid experimental,61 AUvectors/zero UAE.

Failures: B1 output_limit at 8192/118.652 s; B3 output_validation/106.728 s; writer output_limit at 8192/35.249 s. B2/B4 succeeded. All scouts and eight verifier model calls completed, zero timeouts. Three corrob assessments persisted, all inconclusive due workload/origin-evidence incompleteness. Three AU facts verified; two inferences rejected; zero verified AE claims. Writer was reached but did not generate a summary. Normal fallback renderer saved the partial report; this is not the prior offline recovery export. **Clean acceptance remains unmet.**

Retention/accounting:8 versions(3 metadata/5 readable),747381 extractedcharacters,1197 passages; all extraction hashes/offsets/non-whitespace match; native JSON complete.12 attempted = 6 analysed + 6 failed;1185 deferred;0 pending.21 model/3 Exa/6 embedding;40008 embeddingbytes.166470 model + 8654 embedding = 175124 known;0 unknown/pending. DB step, embedding, ledger and report counters match exactly.

Coverage drop trace: extra Documents metadata for `C2026C00274` used an acquisition slot; prior CBUAE press-release HTML not acquired. Prior 3 AU + 1 AE facts vs current 3 AU + 0 AE; sources/caps match but corpus/planner allocation differs. No publication-recall, country-completeness, human precision, hybrid ranking or storage-method winner claim.

Evidence and peer outputs: [validation](../../eval/evidence/2026-11-10-au-ae-uninterrupted-validation.md), [measurements](../../eval/evidence/2026-11-10-au-ae-uninterrupted-validation.json), [artifact hashes](../../eval/evidence/2026-11-10-au-ae-uninterrupted-artifacts.json). Private logs/HTML/PDF live under `reports/au-ae-clean-20261110/`. Actual HTML preserved;8/6 PDF pages visually checked; PDF-only Ref. heading abbreviation. Package excludes keys, originals/full bodies, dumps, vectors and private logs.

Exact next step: user can review/share the labelled partial draft. Engineering follow-up should reproduce analyst structured-output failures and review analysis/writer workloads and output caps without changing role models/effort or hiding deferrals. No further paid execution is authorized on this allowance. Status: test/report/PR delivery complete; clean end-to-end acceptance remains unmet.
