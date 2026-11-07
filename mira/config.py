"""Settings from the environment, with the repository's ``.env`` as a fallback.

Values already in the environment win, so a deployment can override ``.env``.
Nothing here prints or logs a value.
"""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"


def workspace_slug() -> str:
    """Server-selected UI workspace; signed-in reads still use normal RLS."""
    return os.environ.get("MIRA_WORKSPACE_SLUG", "mira").strip() or "mira"


def report_file(relative: str | None, reports_dir: Path = REPORTS_DIR) -> Path | None:
    """The saved HTML report at ``relative``, or None if it is missing or outside ``reports_dir``.

    ``reports.artifact_storage_path`` is written by app users too, so a stored
    path is never trusted to stay inside the reports folder.
    """
    if not relative:
        return None
    root = reports_dir.resolve()
    path = (root / relative).resolve()
    if path.suffix != ".html" or not path.is_relative_to(root) or not path.is_file():
        return None
    return path


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
