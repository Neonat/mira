"""The Streamlit app must never reach the worker's database credentials (PRD v2 §5.1)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {"psycopg", "mira.db", "mira.pg_store", "mira.runner", "mira.evidence", "mira.agents.scout", "mira.seed"}


def imports_of(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def reachable(start: Path) -> set[str]:
    seen: set[str] = set()
    queue = list(imports_of(start))
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        if name.startswith("mira"):
            module = ROOT / (name.replace(".", "/") + ".py")
            package = ROOT / name.replace(".", "/") / "__init__.py"
            for candidate in (module, package):
                if candidate.exists():
                    queue.extend(imports_of(candidate))
    return seen


def test_app_never_imports_worker_modules():
    reached = reachable(ROOT / "app" / "streamlit_app.py")
    assert not {name for name in reached if name.split(".")[0] == "psycopg" or name in FORBIDDEN}


def test_app_reads_only_its_own_settings():
    source = (ROOT / "app" / "streamlit_app.py").read_text()
    assert "MIRA_WORKER_DATABASE_URL" not in source and "ANTHROPIC_API_KEY" not in source
    assert "load_env(keys=UI_KEYS)" in source


def test_workspace_setting_defaults_to_mira_and_can_isolate_a_rehearsal(monkeypatch):
    from mira.config import workspace_slug

    monkeypatch.delenv("MIRA_WORKSPACE_SLUG", raising=False)
    assert workspace_slug() == "mira"
    monkeypatch.setenv("MIRA_WORKSPACE_SLUG", " local-review-rehearsal ")
    assert workspace_slug() == "local-review-rehearsal"
    monkeypatch.setenv("MIRA_WORKSPACE_SLUG", " ")
    assert workspace_slug() == "mira"
