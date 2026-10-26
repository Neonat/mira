"""Settings from the environment, with the repository's ``.env`` as a fallback.

Values already in the environment win, so a deployment can override ``.env``.
Nothing here prints or logs a value.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"


def load_env(path: Path | None = None) -> None:
    """Copy ``KEY=value`` lines from ``.env`` into ``os.environ`` where not already set."""
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
        if key and value and key not in os.environ:
            os.environ[key] = value
