# Working in this repository

## Coordination

- The coordinator owns integration, shared contracts, orchestration, migrations, PRD changes, and any push. Do not edit these without an explicit file-level assignment.
- Keep one writer per file. Use an isolated `codex/` branch/worktree for write tasks when available; in a shared checkout, edit only assigned disjoint files. Do not change global Codex settings or Mira API model configuration.
- Delegate only bounded tasks with explicit file ownership, model/effort, and handover. Keep to three workers plus the coordinator. Start with narrow scoped checks; run the full suite once after integration. Do not repeat proof runs or claim throttling without evidence.
- The coordinator dispatches workers; workers do not recursively create more agents. Give fresh workers a self-contained assignment rather than inheriting the long chat.
- No paid/live API run unless the coordinator explicitly authorizes one, bounded to a single validation.
- Handover format: objective and base SHA; owned and read-only files; sources/commands; changes, tests, and results; open risks; exact next step; completion or blocked status. Do not require reading historic chat.
- Follow `docs/agent-handoffs/README.md` for current roles and checkpoint.
- Project-scoped profiles live in `.codex/agents/`. New Codex sessions load these definitions; an existing session's context is not reset by creating them. Ownership instructions are coordination rules, not separate filesystem sandboxes.

## Ownership boundaries

- `coverage_engineer` (gpt-6.1-terra, medium): scout/fetch/extract/SFC/seed/planner/completeness and research-coverage tests.
- `evidence_architect` (gpt-6-astra, medium): read-only design/review until coverage exits. Corroboration is approved for later work, not built yet; once activated, owns only corroboration module/schema/design and coordinates contracts/orchestrator with coordinator.
- `evaluation_engineer` (gpt-6.1-sol, medium): `eval/` and evidence artifacts. No runtime search changes or benchmark injection.
- `presentation_editor` (gpt-6-luna, medium): narrative and slide outline in `docs/presentation/`; use approved factual metrics only. Actual slide production requires the appropriate skill.
- `demo_engineer` (gpt-6.1-sol, medium): demo/recording assets, script, and browser rehearsal. No runtime code or claim updates.
- `reviewer` (gpt-6-astra, medium): read-only, diff-focused checks; do not implement reviewed changes.

No worker may edit another role's files. The coordinator explicitly assigns exceptions and shared files. Keep handoffs concise and actionable.
