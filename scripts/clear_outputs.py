"""Clear all files from the outputs/ directory (keeps the directory itself)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"


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


if __name__ == "__main__":
    clear_outputs()
