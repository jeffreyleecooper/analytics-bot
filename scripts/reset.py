"""Reset analysis state: clear outputs/ and reset scripts/analysis.py to a shell."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
ANALYSIS = ROOT / "scripts" / "analysis.py"

ANALYSIS_SHELL = '"""Scratch analysis file. Overwrite freely per task."""\n'


def clear_outputs() -> int:
    if not OUTPUTS.exists():
        print(f"{OUTPUTS} does not exist; nothing to clear.")
        return 0
    removed = 0
    for p in OUTPUTS.iterdir():
        if p.is_file():
            p.unlink()
            removed += 1
    print(f"Removed {removed} file(s) from {OUTPUTS}")
    return removed


def reset_analysis() -> None:
    ANALYSIS.write_text(ANALYSIS_SHELL, encoding="utf-8")
    print(f"Reset {ANALYSIS} to scratch shell")


if __name__ == "__main__":
    clear_outputs()
    reset_analysis()
