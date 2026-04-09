"""Install dependencies from the root requirements.txt."""
import subprocess
import sys
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"


def main() -> int:
    if not REQUIREMENTS.exists():
        print(f"requirements.txt not found at {REQUIREMENTS}", file=sys.stderr)
        return 1
    return subprocess.call(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    )


if __name__ == "__main__":
    raise SystemExit(main())
