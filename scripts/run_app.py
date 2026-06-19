"""Launch the Streamlit chat UI: `python scripts/run_app.py`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app" / "streamlit_app.py"


def main() -> int:
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(APP)])


if __name__ == "__main__":
    raise SystemExit(main())
