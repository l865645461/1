"""Run the A+B+C v1.2.1 replay contract and diagnostic test suite."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "A_demo_base"


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-v",
        "-s",
        str(APP_DIR),
        "-p",
        "test*.py",
    ]
    return subprocess.call(command, cwd=str(APP_DIR))


if __name__ == "__main__":
    raise SystemExit(main())

