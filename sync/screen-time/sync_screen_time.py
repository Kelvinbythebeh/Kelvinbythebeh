#!/usr/bin/env python3
"""
Screen Time → Life OS Sync

Apple Screen Time doesn't have an API. Data flows via:
1. iPhone Shortcuts → Export Screen Time data as JSON → Google Drive
2. Manual weekly screenshot → paste to Claude for OCR
3. Third-party: use iOS app "ScreenZen" or "one sec" which export data

For Android: Digital Wellbeing data via Google Takeout

Usage:
    # From Shortcuts export:
    python sync_screen_time.py --input ~/Downloads/screen_time.json

    # From Google Takeout (Android):
    python sync_screen_time.py --input ~/Downloads/takeout/ --format takeout
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "screen-time"


def parse_shortcuts_export(filepath: Path) -> list:
    """
    Parse JSON from Apple Shortcuts screen time export.

    Build a Shortcut:
    1. Get Screen Time data (iOS 17+)
    2. Format as JSON with: app_name, category, duration_min, date
    3. Save to Files/Google Drive
    """
    with open(filepath) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get('entries', [])


def parse_google_takeout(input_dir: Path) -> list:
    """Parse Android Digital Wellbeing from Google Takeout."""
    entries = []
    wellbeing_dir = input_dir / "My Activity" / "Android"

    if not wellbeing_dir.exists():
        # Try alternate paths
        for candidate in input_dir.rglob('*.json'):
            if 'android' in str(candidate).lower() or 'wellbeing' in str(candidate).lower():
                with open(candidate) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        entries.extend(data)

    return entries


def save_screen_time(entries: list):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"screen_time_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_path, 'w') as f:
        json.dump(entries, f, indent=2)

    log_path = BASE_DIR / "life" / "mental-wellness" / "screen-time-data.yaml"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Screen Time Data - Auto-synced\n",
        f"# Last sync: {datetime.now().isoformat()}\n",
        f"# Entries: {len(entries)}\n\n",
        "entries:\n",
    ]

    for entry in entries:
        lines.append(f"  - date: \"{entry.get('date', '')}\"\n")
        if entry.get('app'):
            lines.append(f"    app: \"{entry['app']}\"\n")
        if entry.get('category'):
            lines.append(f"    category: \"{entry['category']}\"\n")
        if entry.get('duration_min'):
            lines.append(f"    duration_min: {entry['duration_min']}\n")
        if entry.get('pickups'):
            lines.append(f"    pickups: {entry['pickups']}\n")
        lines.append("\n")

    log_path.write_text(''.join(lines), encoding='utf-8')
    print(f"  Entries: {len(entries)}")
    print(f"  Saved: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Sync Screen Time → Life OS")
    parser.add_argument('--input', '-i', required=True)
    parser.add_argument('--format', choices=['json', 'takeout'], default='json')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {args.input} not found")
        sys.exit(1)

    if args.format == 'takeout':
        entries = parse_google_takeout(input_path)
    else:
        entries = parse_shortcuts_export(input_path)

    save_screen_time(entries)
    print("\nScreen Time sync complete!")


if __name__ == '__main__':
    main()
