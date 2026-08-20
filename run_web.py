#!/usr/bin/env python3
"""Run the FastAPI UI without editable installs.

Adds the repo root to ``sys.path`` so ``import sea_of_colours`` works, then
starts Uvicorn. Use from repo root::

    python run_web.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(ROOT / "server"), str(ROOT / "sea_of_colours")],
    )
