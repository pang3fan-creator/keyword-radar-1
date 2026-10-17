"""Load the project's .env file into os.environ.

The project keeps its keys in .env at the repository root, not in the shell
profile. `main()` calls load() before a command runs; a project-local value
overrides a stale global one, so the file is the source of truth for the keys
it defines.

Only variables read when a call is made are guaranteed to see the file. Two
module-level constants (AISA_ROUTER_BASE_URL, AISA_API_BASE_URL in aisa.py) are
read at import time; they are not in .env today. If they join it, move this
call to the top of the package or make aisa read them at call time.

Tests set RADAR_SKIP_ENV_FILE=1 (see tests/conftest.py) so a developer's real
keys never change a test's behaviour.
"""
from __future__ import annotations

import os
from pathlib import Path


def load(path: Path, override: bool = True) -> int:
    """Set KEY=VALUE pairs from `path`; return how many variables were set.

    Blank lines, comments and lines without '=' are ignored. A value may be
    wrapped in matching single or double quotes; the quotes are stripped.
    `export KEY=value` is accepted. A missing file is a no-op.
    """
    if not path.exists():
        return 0
    loaded = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded
