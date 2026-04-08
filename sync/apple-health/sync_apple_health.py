#!/usr/bin/env python3
"""
Apple Health → Google Drive / Local Sync

Apple Health doesn't have an API. Data flows via:
1. iPhone Shortcuts → Export health data as JSON → Save to Google Drive
2. Manual export: Settings → Health → Export All Health Data → XML
3. Third-party apps: Health Auto Export (iOS app) → Google Drive

This script reads the exported data and transforms it into health log entries.

Usage:
    # From Shortcuts JSON export (recommended):
    python sync_apple_health.py --input ~/Downloads/health_export.json

    # From Apple Health XML export:
    python sync_apple_health.py --input ~/Downloads/export.xml --format xml

    # From Health Auto Export app (CSV):
    python sync_apple_health.py --input ~/Downloads/health/ --format csv

    # From Google Drive (after auto-export uploads there):
    python sync_apple_health.py --from-drive
"""

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "apple-health"
HEALTH_LOG = BASE_DIR / "life" / "health"


# ── Shortcuts JSON Import ────────────────────────────────────────────────────

def parse_shortcuts_json(filepath: Path) -> list:
    """
    Parse JSON exported by Apple Shortcuts.

    Build a Shortcut like:
    1. Find Health Samples (type: Steps, last 7 days)
    2. Find Health Samples (type: Heart Rate, last 7 days)
    3. Find Health Samples (type: Sleep Analysis, last 7 days)
    4. Find Health Samples (type: Active Energy, last 7 days)
    5. Find Health Samples (type: Body Mass, last 7 days)
    6. Combine into dictionary
    7. Save File (JSON) to Google Drive or Files
    """
    with open(filepath, 'r') as f:
        data = json.load(f)

    entries = []

    # Handle both flat array and categorized dict
    if isinstance(data, dict):
        for category, samples in data.items():
            if isinstance(samples, list):
                for sample in samples:
                    sample['_category'] = category
                    entries.append(sample)
    elif isinstance(data, list):
        entries = data

    return entries


# ── Apple Health XML Export ──────────────────────────────────────────────────

def parse_health_xml(filepath: Path, days_back: int = 30) -> list:
    """Parse Apple Health export.xml (can be very large)."""
    print(f"Parsing XML (this may take a moment for large exports)...")

    cutoff = datetime.now() - timedelta(days=days_back)
    entries = []

    # Stream parse to handle large files
    for event, elem in ET.iterparse(str(filepath), events=('end',)):
        if elem.tag != 'Record':
            continue

        record_type = elem.get('type', '')
        start_date = elem.get('startDate', '')
        value = elem.get('value', '')

        # Parse date
        try:
            dt = datetime.strptime(start_date[:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, IndexError):
            elem.clear()
            continue

        if dt < cutoff:
            elem.clear()
            continue

        # Only extract useful types
        useful_types = {
            'HKQuantityTypeIdentifierStepCount': 'steps',
            'HKQuantityTypeIdentifierHeartRate': 'heart_rate',
            'HKQuantityTypeIdentifierRestingHeartRate': 'resting_hr',
            'HKQuantityTypeIdentifierHeartRateVariabilitySDNN': 'hrv',
            'HKQuantityTypeIdentifierActiveEnergyBurned': 'active_calories',
            'HKQuantityTypeIdentifierBasalEnergyBurned': 'basal_calories',
            'HKQuantityTypeIdentifierBodyMass': 'weight_kg',
            'HKQuantityTypeIdentifierBodyFatPercentage': 'body_fat_pct',
            'HKQuantityTypeIdentifierOxygenSaturation': 'spo2',
            'HKQuantityTypeIdentifierBloodPressureSystolic': 'bp_systolic',
            'HKQuantityTypeIdentifierBloodPressureDiastolic': 'bp_diastolic',
            'HKQuantityTypeIdentifierDietaryWater': 'water_ml',
            'HKQuantityTypeIdentifierDietaryEnergyConsumed': 'calories_consumed',
            'HKCategoryTypeIdentifierSleepAnalysis': 'sleep',
            'HKQuantityTypeIdentifierAppleExerciseTime': 'exercise_minutes',
        }

        metric = useful_types.get(record_type)
        if metric:
            try:
                val = float(value) if value else None
            except ValueError:
                val = value

            entries.append({
                'date': dt.strftime('%Y-%m-%d'),
                'time': dt.strftime('%H:%M'),
                'metric': metric,
                'value': val,
                'unit': elem.get('unit', ''),
            })

        elem.clear()

    print(f"  Extracted {len(entries)} records from XML")
    return entries


# ── CSV Import (Health Auto Export app) ──────────────────────────────────────

def parse_csv_export(input_dir: Path) -> list:
    """Parse CSV files from Health Auto Export iOS app."""
    entries = []

    for csv_file in input_dir.glob('*.csv'):
        metric_name = csv_file.stem.lower().replace(' ', '_')
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row.get('Date', row.get('date', row.get('Start', '')))
                value = row.get('Value', row.get('value', row.get('Qty', '')))

                if date and value:
                    try:
                        entries.append({
                            'date': date[:10],
                            'metric': metric_name,
                            'value': float(value),
                        })
                    except ValueError:
                        pass

    print(f"  Parsed {len(entries)} records from CSV files")
    return entries


# ── Aggregate by Day ─────────────────────────────────────────────────────────

def aggregate_daily(entries: list) -> list:
    """Aggregate raw health samples into daily summaries."""
    from collections import defaultdict

    daily = defaultdict(lambda: defaultdict(list))

    for entry in entries:
        day = entry['date']
        metric = entry['metric']
        value = entry.get('value')
        if value is not None and isinstance(value, (int, float)):
            daily[day][metric].append(value)

    summaries = []
    for day in sorted(daily.keys()):
        metrics = daily[day]
        summary = {
            'date': day,
            'source': 'apple-health',
        }

        # Aggregate rules per metric
        if 'steps' in metrics:
            summary['steps'] = int(sum(metrics['steps']))
        if 'heart_rate' in metrics:
            summary['avg_heart_rate'] = round(sum(metrics['heart_rate']) / len(metrics['heart_rate']), 1)
        if 'resting_hr' in metrics:
            summary['resting_hr'] = round(min(metrics['resting_hr']), 1)
        if 'hrv' in metrics:
            summary['hrv'] = round(sum(metrics['hrv']) / len(metrics['hrv']), 1)
        if 'active_calories' in metrics:
            summary['active_calories'] = int(sum(metrics['active_calories']))
        if 'weight_kg' in metrics:
            summary['weight_kg'] = round(metrics['weight_kg'][-1], 1)  # latest
        if 'body_fat_pct' in metrics:
            summary['body_fat_pct'] = round(metrics['body_fat_pct'][-1], 1)
        if 'exercise_minutes' in metrics:
            summary['exercise_min'] = int(sum(metrics['exercise_minutes']))
        if 'water_ml' in metrics:
            summary['water_ml'] = int(sum(metrics['water_ml']))
        if 'sleep' in metrics:
            # Sleep entries are complex, simplify
            summary['sleep_entries'] = len(metrics['sleep'])

        summaries.append(summary)

    return summaries


# ── Save ─────────────────────────────────────────────────────────────────────

def save_health_data(summaries: list):
    """Save aggregated health data for Claude to read."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    HEALTH_LOG.mkdir(parents=True, exist_ok=True)

    # Save raw
    raw_path = RAW_DIR / f"daily_summary_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_path, 'w') as f:
        json.dump(summaries, f, indent=2)

    # Save as YAML for Claude
    log_path = HEALTH_LOG / "apple-health-data.yaml"
    header = (
        "# Apple Health Data - Auto-synced\n"
        f"# Last sync: {datetime.now().isoformat()}\n"
        f"# Records: {len(summaries)} days\n\n"
        "entries:\n"
    )

    yaml_entries = ""
    for entry in summaries:
        yaml_entries += f"  - date: \"{entry['date']}\"\n"
        for k, v in entry.items():
            if k == 'date':
                continue
            if isinstance(v, str):
                yaml_entries += f"    {k}: \"{v}\"\n"
            else:
                yaml_entries += f"    {k}: {v}\n"
        yaml_entries += "\n"

    log_path.write_text(header + yaml_entries, encoding='utf-8')
    print(f"\n  Raw saved: {raw_path}")
    print(f"  Health log: {log_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync Apple Health → Life OS")
    parser.add_argument('--input', '-i', help='Path to exported health data')
    parser.add_argument('--format', choices=['json', 'xml', 'csv'], default='json',
                        help='Export format (default: json from Shortcuts)')
    parser.add_argument('--days', type=int, default=30,
                        help='Days back to process from XML export')
    parser.add_argument('--from-drive', action='store_true',
                        help='Read from local data/raw/apple-health/ (after Drive sync)')
    args = parser.parse_args()

    if args.from_drive:
        # Read from already-synced Drive data
        drive_dir = RAW_DIR
        if not drive_dir.exists() or not list(drive_dir.glob('*')):
            print("No Apple Health data in data/raw/apple-health/")
            print("Run drive_bridge.py --pull first, or use --input")
            sys.exit(1)

        entries = []
        for f in sorted(drive_dir.glob('*.json')):
            with open(f) as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    entries.extend(data)
        print(f"Loaded {len(entries)} records from Drive cache")

    elif args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"ERROR: {args.input} not found")
            sys.exit(1)

        if args.format == 'xml':
            entries = parse_health_xml(input_path, args.days)
        elif args.format == 'csv':
            entries = parse_csv_export(input_path)
        else:
            entries = parse_shortcuts_json(input_path)
    else:
        print("ERROR: Provide --input or --from-drive")
        sys.exit(1)

    summaries = aggregate_daily(entries)
    print(f"\n  Aggregated into {len(summaries)} daily summaries")
    save_health_data(summaries)
    print("\nApple Health sync complete!")


if __name__ == '__main__':
    main()
