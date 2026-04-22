"""Bootstrap local imports when the orchestrator runs as a module.

This helper inserts the project root onto `sys.path` so `shared` imports work
reliably from CLI entry points and tests. It is important because the pipeline
depends on consistent module resolution across local and CI executions.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
