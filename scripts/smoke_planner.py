"""One live planner call to Claude: checks the API accepts the ResearchPlan schema with fallbacks on.

Makes at most one API request. If the plan fails Mira's code checks, the repair
retry is blocked and the rejection is printed instead.

Run from the repository root:
    .venv/bin/python scripts/smoke_planner.py
Reads ANTHROPIC_API_KEY from the environment or from the repository's .env.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

REPO = Path.cwd()
if not (REPO / "mira" / "contracts.py").exists():
    sys.exit("run this from the mira repository root")

from mira.config import load_env  # noqa: E402

load_env(keys={"ANTHROPIC_API_KEY", "MIRA_MODEL_PLANNER"})
if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
    sys.exit("no ANTHROPIC_API_KEY in the environment or .env")
os.environ.setdefault("MIRA_MODEL_PLANNER", "anthropic:claude-opus-5-5")

import anthropic  # noqa: E402

from mira.agents import planner  # noqa: E402
from mira.contracts import Brief  # noqa: E402
from mira.llm import AnthropicClient, LLMError  # noqa: E402
from mira.store import ExpectedSourceRecord, SourceRecord  # noqa: E402

ALL = ("metadata", "fetch", "store_text", "quote", "embed")


def source(name, kind, url, code, ops=ALL):
    return SourceRecord(uuid4(), name, kind, url, code, ops)


MAS = source("MAS", "regulator", "https://www.mas.gov.sg", "SG")
SSO = source("Singapore Statutes Online", "manual", None, "SG", ("metadata",))
ABS = source("Association of Banks in Singapore", "website", "https://abs.org.sg", "SG", ("metadata", "fetch"))
HKMA = source("HKMA", "regulator", "https://www.hkma.gov.hk", "HK")
SFC = source("SFC", "regulator", "https://www.sfc.hk", "HK")
FSTB = source("FSTB", "regulator", "https://www.fstb.gov.hk", "HK", ("metadata", "fetch"))
ELEG = source("HK e-Legislation", "manual", None, "HK", ("metadata",))
APG = source("Asia/Pacific Group on Money Laundering", "website", "https://apgml.org", None, ("metadata", "fetch"))
WOLFSBERG = source("Wolfsberg Group", "website", "https://wolfsberg-group.org", None, ("metadata", "fetch"))
SOURCES = [MAS, SSO, ABS, HKMA, SFC, FSTB, ELEG, APG, WOLFSBERG]


def expected(code, category, hint, src):
    return ExpectedSourceRecord(uuid4(), 1, code, category, src.id, hint)


EXPECTED = [
    expected("SG", "rule", "MAS Notice 626 and amendments", MAS),
    expected("SG", "guideline", "Guidelines to MAS Notice 626", MAS),
    expected("SG", "enforcement", "MAS enforcement actions involving AML/CFT", MAS),
    expected("SG", "consultation", "MAS consultation papers on AML/CFT", MAS),
    expected("SG", "legislation", "CDSA amendments", SSO),
    expected("SG", "industry", "ABS industry AML/CFT guidance", ABS),
    expected("HK", "legislation", "AMLO (Cap. 615) amendments", ELEG),
    expected("HK", "guideline", "HKMA Guideline on AML/CFT (for authorized institutions)", HKMA),
    expected("HK", "enforcement", "HKMA disciplinary actions for AML breaches", HKMA),
    expected("HK", "guideline", "SFC AML/CFT Guideline for licensed corporations", SFC),
    expected("HK", "circular", "FSTB AML/CFT policy and risk assessment updates", FSTB),
    expected("SG", "industry", "APG mutual evaluation and follow-up reports", APG),
    expected("HK", "industry", "APG mutual evaluation and follow-up reports", APG),
    expected("SG", "industry", "Wolfsberg Group publications", WOLFSBERG),
    expected("HK", "industry", "Wolfsberg Group publications", WOLFSBERG),
]

BRIEF = Brief(
    topic="AML/CFT", jurisdictions=["SG", "HK"], period_start=date(2025, 10, 26), period_end=date(2026, 10, 26),
    as_of_date=date(2026, 10, 26), plan_requires_approval=False,
)


class OneCall:
    """Lets exactly one request through and keeps its result for inspection."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.last = None

    def structured(self, **kwargs):
        self.calls += 1
        if self.calls > 1:
            raise LLMError("second call blocked by the smoke test")
        self.last = self.inner.structured(**kwargs)
        return self.last


client = OneCall(AnthropicClient())
started = time.monotonic()
try:
    planned = planner.plan(client, BRIEF, SOURCES, EXPECTED, 60)
except anthropic.APIStatusError as exc:
    print(f"API REJECTED the request: HTTP {exc.status_code}\n{exc.message}")
    sys.exit(1)
except anthropic.APIConnectionError as exc:
    print(f"COULD NOT REACH the API: {exc}")
    sys.exit(1)
except LLMError as exc:
    print(f"CALL FAILED: {exc} (tokens in/out {exc.tokens_in}/{exc.tokens_out})")
    if client.last is not None:
        print("\nThe API accepted the schema; the plan failed Mira's checks. Model output:")
        print(client.last.output.model_dump_json(indent=2))
    sys.exit(2)

elapsed = time.monotonic() - started
result = planned.llm
print(f"OK in {elapsed:.0f}s: model {result.model}, tokens in/out {result.tokens_in}/{result.tokens_out}")
print(f"{len(planned.tasks)} tasks; plan passed every planner check on the first attempt\n")
names = {s.id: s.name for s in SOURCES}
for task in planned.tasks:
    print(f"{task.task_label} {task.role} {task.jurisdiction_code or '-'} max_docs={task.max_documents}")
    print(f"   sources: {', '.join(names[i] for i in task.source_ids)}")
    print(f"   expected items: {len(task.expected_source_ids)}")
    print(f"   question: {task.question}")
if planned.plan.notes:
    print(f"\nnotes: {planned.plan.notes}")
