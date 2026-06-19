"""Copy each merchant's latest generated deck into deliverables/ with a friendly name.

`data/output/` is gitignored (it holds versioned, regenerable artifacts). This script
publishes a clean, committed sample set for review:

    deliverables/<merchant>_performance_review.pptx

Run after `make decks` (or `python scripts/generate_decks.py`). Re-running overwrites the
samples with the newest version. Usage: `python scripts/export_deliverables.py`.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECKS_DIR = ROOT / "data" / "output" / "decks"
OUT_DIR = ROOT / "deliverables"


def main() -> int:
    if not DECKS_DIR.exists():
        print(f"No decks found at {DECKS_DIR}. Run: python scripts/generate_decks.py")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for merchant_dir in sorted(p for p in DECKS_DIR.iterdir() if p.is_dir()):
        latest_file = merchant_dir / "LATEST"
        if not latest_file.exists():
            continue
        version = latest_file.read_text().strip()
        src = merchant_dir / f"{merchant_dir.name}_{version}.pptx"
        if not src.exists():
            print(f"  ! missing {src}")
            continue
        friendly = f"{merchant_dir.name.replace('-', '_')}_performance_review.pptx"
        shutil.copyfile(src, OUT_DIR / friendly)
        print(f"  {src.relative_to(ROOT)} -> deliverables/{friendly}")
        copied += 1

    if not copied:
        print("No decks copied. Run: python scripts/generate_decks.py")
        return 1
    print(f"Exported {copied} deck(s) to deliverables/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
