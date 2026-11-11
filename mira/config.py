"""Settings from the environment, with the repository's ``.env`` as a fallback.

Values already in the environment win, so a deployment can override ``.env``.
Nothing here prints or logs a value.
"""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"


def workspace_slug() -> str:
    """Server-selected UI workspace; signed-in reads still use normal RLS."""
    return os.environ.get("MIRA_WORKSPACE_SLUG", "mira").strip() or "mira"


def report_artifact_path(run_id: UUID, version: int, *, reviewed: bool = False) -> Path:
    """Return the relative HTML path for a report from a specific run."""
    suffix = "-reviewed" if reviewed else ""
    return Path(str(run_id)) / f"report-v{version}{suffix}.html"


def report_file(
    relative: str | None, *, run_id: UUID | str, version: int, reviewed: bool,
    reports_dir: Path = REPORTS_DIR,
) -> Path | None:
    """Find the artifact for the run and report already authorized by the database."""
    if not relative:
        return None
    try:
        expected = report_artifact_path(UUID(str(run_id)), version, reviewed=reviewed)
        if Path(relative) != expected:
            return None
        path = reports_dir.resolve() / expected
        return path if path.is_file() and path.resolve() == path else None
    except (OSError, RuntimeError, ValueError):
        return None


def load_env(path: Path | None = None, keys: Collection[str] | None = None) -> None:
    """Copy ``KEY=value`` lines from ``.env`` into ``os.environ`` where not already set.

    With ``keys``, only those names are copied: the Streamlit app passes its own
    list so the worker's database URL and API key never enter its process.
    """
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in os.environ and (keys is None or key in keys):
            os.environ[key] = value
