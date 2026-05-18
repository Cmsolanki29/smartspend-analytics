#!/usr/bin/env python3
"""Apply migrations + seed judge demo users on production Postgres (Neon).

Usage (from backend/, with DATABASE_URL in env or .env):

    python -m scripts.deploy_production_db
    python -m scripts.deploy_production_db --skip-seed
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-seed", action="store_true", help="Only run migrations.")
    args = parser.parse_args()

    py = sys.executable
    r = subprocess.run([py, "-m", "scripts.apply_migrations"], cwd=_BACKEND)
    if r.returncode != 0:
        return r.returncode

    if args.skip_seed:
        print("Skipping judge demo seed.")
        return 0

    r = subprocess.run([py, "-m", "scripts.seed_judge_demo_users"], cwd=_BACKEND)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
