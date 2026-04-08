#!/usr/bin/env python3
"""
Master Processor - Runs all vault → brain transformations.

Usage:
    python processors/process_all.py              # Process everything
    python processors/process_all.py --only health # Just health data
    python processors/process_all.py --days 30     # Last 30 days only
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSORS_DIR = BASE_DIR / "processors"

PROCESSORS = {
    'health': 'process_health.py',
    'finance': 'process_finance.py',
    'time': 'process_time.py',
    'notes': 'process_notes.py',
}


def run_processor(name: str, extra_args: list = None) -> bool:
    script = PROCESSORS_DIR / PROCESSORS[name]
    cmd = [sys.executable, str(script)] + (extra_args or [])

    print(f"\n{'─' * 50}")
    print(f"  Processing: {name}")
    print(f"{'─' * 50}")

    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Process all vault data → life/ brain")
    parser.add_argument('--only', choices=list(PROCESSORS.keys()),
                        help='Run only one processor')
    parser.add_argument('--days', type=int, help='Process last N days only')
    args = parser.parse_args()

    print("=" * 50)
    print("  VAULT → BRAIN PROCESSING")
    print("=" * 50)

    to_run = [args.only] if args.only else list(PROCESSORS.keys())
    results = {}

    for name in to_run:
        extra = []
        if args.days and name in ('health', 'time'):
            extra = ['--days', str(args.days)]
        results[name] = run_processor(name, extra)

    print(f"\n{'=' * 50}")
    print("  RESULTS")
    print(f"{'=' * 50}")
    for name, ok in results.items():
        print(f"  {name:<15} {'OK' if ok else 'FAILED'}")

    if all(results.values()):
        print("\nAll processors complete! Claude can now read your life data.")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
