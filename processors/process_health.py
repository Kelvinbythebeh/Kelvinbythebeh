#!/usr/bin/env python3
"""
Health Processor - Reads raw vault data → writes to life/health/

Combines data from: Garmin, Oura, Apple Health
into a single unified health log that Claude can read.

Usage:
    python processors/process_health.py                # Process all available data
    python processors/process_health.py --days 30      # Last 30 days only
    python processors/process_health.py --source garmin # Only Garmin data
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "vault"
OUTPUT_DIR = BASE_DIR / "life" / "health"


def load_vault_json(source: str) -> list:
    """Load all JSON files from a vault source directory."""
    source_dir = VAULT_DIR / source
    if not source_dir.exists():
        return []

    all_data = []
    for f in sorted(source_dir.glob('*.json')):
        with open(f) as fh:
            try:
                data = json.load(fh)
                if isinstance(data, list):
                    all_data.extend(data)
                elif isinstance(data, dict):
                    all_data.append(data)
            except json.JSONDecodeError:
                pass
    return all_data


# ── Garmin Extractors ────────────────────────────────────────────────────────

def extract_garmin_sleep(raw_data: list) -> dict:
    """Extract sleep metrics from Garmin vault data."""
    by_date = {}
    for item in raw_data:
        date = item.get('date', '')
        data = item.get('data', item)
        if not date:
            continue

        sleep_data = data if isinstance(data, dict) else {}
        daily = sleep_data.get('dailySleepDTO', sleep_data)

        entry = {}
        if daily.get('sleepTimeSeconds'):
            entry['sleep_hours'] = round(daily['sleepTimeSeconds'] / 3600, 1)
        if daily.get('deepSleepSeconds'):
            entry['deep_sleep_hours'] = round(daily['deepSleepSeconds'] / 3600, 1)
        if daily.get('lightSleepSeconds'):
            entry['light_sleep_hours'] = round(daily['lightSleepSeconds'] / 3600, 1)
        if daily.get('remSleepSeconds'):
            entry['rem_sleep_hours'] = round(daily['remSleepSeconds'] / 3600, 1)
        if daily.get('awakeSleepSeconds'):
            entry['awake_hours'] = round(daily['awakeSleepSeconds'] / 3600, 1)
        if daily.get('averageSpO2Value'):
            entry['avg_spo2'] = daily['averageSpO2Value']
        if daily.get('averageRespirationValue'):
            entry['avg_respiration'] = daily['averageRespirationValue']
        if daily.get('sleepScores', {}).get('overall', {}).get('value'):
            entry['sleep_score'] = daily['sleepScores']['overall']['value']

        if entry:
            entry['source'] = 'garmin'
            by_date[date] = entry

    return by_date


def extract_garmin_activity(raw_data: list) -> dict:
    """Extract daily activity from Garmin vault data."""
    by_date = {}
    for item in raw_data:
        date = item.get('date', '')
        data = item.get('data', item)
        if not date:
            continue

        entry = {}
        if data.get('totalSteps'):
            entry['steps'] = data['totalSteps']
        if data.get('activeKilocalories'):
            entry['active_calories'] = data['activeKilocalories']
        if data.get('totalKilocalories'):
            entry['total_calories'] = data['totalKilocalories']
        if data.get('floorsAscended'):
            entry['floors'] = data['floorsAscended']
        if data.get('minHeartRate'):
            entry['resting_hr'] = data['minHeartRate']
        if data.get('restingHeartRate'):
            entry['resting_hr'] = data['restingHeartRate']
        if data.get('averageStressLevel'):
            entry['stress_avg'] = data['averageStressLevel']
        if data.get('maxStressLevel'):
            entry['stress_max'] = data['maxStressLevel']
        if data.get('bodyBatteryChargedValue'):
            entry['body_battery_high'] = data['bodyBatteryChargedValue']
        if data.get('bodyBatteryDrainedValue'):
            entry['body_battery_low'] = data['bodyBatteryDrainedValue']
        if data.get('moderateIntensityMinutes'):
            entry['moderate_intensity_min'] = data['moderateIntensityMinutes']
        if data.get('vigorousIntensityMinutes'):
            entry['vigorous_intensity_min'] = data['vigorousIntensityMinutes']

        if entry:
            entry['source'] = 'garmin'
            by_date[date] = entry

    return by_date


def extract_garmin_workouts(raw_data: list) -> list:
    """Extract workouts from Garmin vault data."""
    workouts = []
    for item in raw_data:
        data = item.get('data', item) if isinstance(item, dict) and 'data' in item else item

        workout = {
            'date': (data.get('startTimeLocal') or '')[:10],
            'name': data.get('activityName', ''),
            'type': data.get('activityType', {}).get('typeKey', '') if isinstance(data.get('activityType'), dict) else str(data.get('activityType', '')),
            'duration_min': round(data.get('duration', 0) / 60, 1),
            'distance_km': round(data.get('distance', 0) / 1000, 2) if data.get('distance') else 0,
            'calories': data.get('calories', 0),
            'avg_hr': data.get('averageHR', 0),
            'max_hr': data.get('maxHR', 0),
            'source': 'garmin',
        }

        if workout['date']:
            workouts.append(workout)

    return sorted(workouts, key=lambda x: x['date'], reverse=True)


# ── Oura Extractors ─────────────────────────────────────────────────────────

def extract_oura_sleep(raw_data: list) -> dict:
    """Extract sleep from Oura vault data."""
    by_date = {}
    for item in raw_data:
        day = item.get('day', item.get('date', ''))
        if not day:
            continue

        entry = {}
        if item.get('score'):
            entry['sleep_score'] = item['score']

        contributors = item.get('contributors', {})
        if contributors.get('total_sleep'):
            val = contributors['total_sleep']
            if val > 100:  # seconds
                entry['sleep_hours'] = round(val / 3600, 1)

        if contributors.get('efficiency'):
            entry['sleep_efficiency'] = contributors['efficiency']

        if entry:
            entry['source'] = 'oura'
            by_date[day] = entry

    return by_date


def extract_oura_readiness(raw_data: list) -> dict:
    """Extract readiness from Oura vault data."""
    by_date = {}
    for item in raw_data:
        day = item.get('day', item.get('date', ''))
        if not day:
            continue

        entry = {}
        if item.get('score'):
            entry['readiness_score'] = item['score']

        contributors = item.get('contributors', {})
        if contributors.get('hrv_balance'):
            entry['hrv_balance'] = contributors['hrv_balance']
        if contributors.get('resting_heart_rate'):
            entry['resting_hr'] = contributors['resting_heart_rate']

        if entry:
            entry['source'] = 'oura'
            by_date[day] = entry

    return by_date


def extract_oura_activity(raw_data: list) -> dict:
    """Extract activity from Oura vault data."""
    by_date = {}
    for item in raw_data:
        day = item.get('day', item.get('date', ''))
        if not day:
            continue

        entry = {}
        if item.get('score'):
            entry['activity_score'] = item['score']
        if item.get('steps'):
            entry['steps'] = item['steps']
        if item.get('active_calories'):
            entry['active_calories'] = item['active_calories']

        if entry:
            entry['source'] = 'oura'
            by_date[day] = entry

    return by_date


# ── Apple Health Extractors ──────────────────────────────────────────────────

def extract_apple_health(raw_data: list) -> dict:
    """Extract daily summaries from Apple Health vault data."""
    by_date = {}
    for item in raw_data:
        date = item.get('date', '')
        if not date:
            continue
        entry = {k: v for k, v in item.items() if k != 'date' and v}
        if entry:
            entry['source'] = 'apple-health'
            by_date[date] = entry
    return by_date


# ── Merger ───────────────────────────────────────────────────────────────────

def merge_health_data(cutoff_days: int = None) -> dict:
    """Merge all health sources into unified daily entries.

    Priority: Garmin > Oura > Apple Health (for overlapping metrics)
    """
    cutoff = None
    if cutoff_days:
        cutoff = (datetime.now() - timedelta(days=cutoff_days)).strftime('%Y-%m-%d')

    # Load from vault
    garmin_sleep_raw = load_vault_json('garmin')
    garmin_stats_raw = load_vault_json('garmin')
    oura_raw = load_vault_json('oura')
    apple_raw = load_vault_json('apple-health')

    # Separate garmin data by type (based on filename patterns in vault)
    garmin_sleep_files = list((VAULT_DIR / 'garmin').glob('sleep_*.json')) if (VAULT_DIR / 'garmin').exists() else []
    garmin_stats_files = list((VAULT_DIR / 'garmin').glob('daily_stats_*.json')) if (VAULT_DIR / 'garmin').exists() else []
    garmin_workout_files = list((VAULT_DIR / 'garmin').glob('workouts_*.json')) if (VAULT_DIR / 'garmin').exists() else []
    oura_sleep_files = list((VAULT_DIR / 'oura').glob('daily_sleep_*.json')) if (VAULT_DIR / 'oura').exists() else []
    oura_readiness_files = list((VAULT_DIR / 'oura').glob('daily_readiness_*.json')) if (VAULT_DIR / 'oura').exists() else []
    oura_activity_files = list((VAULT_DIR / 'oura').glob('daily_activity_*.json')) if (VAULT_DIR / 'oura').exists() else []

    def load_files(files):
        data = []
        for f in files:
            with open(f) as fh:
                d = json.load(fh)
                if isinstance(d, list):
                    data.extend(d)
        return data

    # Extract structured data from each source
    garmin_sleep = extract_garmin_sleep(load_files(garmin_sleep_files))
    garmin_activity = extract_garmin_activity(load_files(garmin_stats_files))
    garmin_workouts = extract_garmin_workouts(load_files(garmin_workout_files))
    oura_sleep = extract_oura_sleep(load_files(oura_sleep_files))
    oura_readiness = extract_oura_readiness(load_files(oura_readiness_files))
    oura_activity = extract_oura_activity(load_files(oura_activity_files))
    apple_health = extract_apple_health(apple_raw)

    # Merge: collect all dates
    all_dates = set()
    for source in [garmin_sleep, garmin_activity, oura_sleep, oura_readiness,
                   oura_activity, apple_health]:
        all_dates.update(source.keys())

    # Build unified daily entries (Garmin priority, then Oura, then Apple)
    unified = {}
    for date in sorted(all_dates):
        if cutoff and date < cutoff:
            continue

        entry = {'date': date, 'sources': []}

        # Layer data - later sources fill in gaps, don't overwrite
        for source_data, source_name in [
            (apple_health.get(date, {}), 'apple-health'),
            (oura_activity.get(date, {}), 'oura'),
            (oura_readiness.get(date, {}), 'oura'),
            (oura_sleep.get(date, {}), 'oura'),
            (garmin_activity.get(date, {}), 'garmin'),
            (garmin_sleep.get(date, {}), 'garmin'),
        ]:
            for key, val in source_data.items():
                if key == 'source':
                    if source_name not in entry['sources']:
                        entry['sources'].append(source_name)
                    continue
                if key not in entry or entry[key] is None:
                    entry[key] = val

        unified[date] = entry

    return {'daily': unified, 'workouts': garmin_workouts}


# ── Output ───────────────────────────────────────────────────────────────────

def write_health_log(merged: dict):
    """Write unified health data to life/health/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    daily = merged['daily']
    workouts = merged['workouts']

    # ── Daily health log ──
    log_path = OUTPUT_DIR / "daily-data.yaml"
    lines = [
        "# Unified Health Data (auto-generated from vault)\n",
        f"# Sources: Garmin, Oura, Apple Health\n",
        f"# Last processed: {datetime.now().isoformat()}\n",
        f"# Days: {len(daily)}\n\n",
        "daily:\n",
    ]

    for date in sorted(daily.keys(), reverse=True)[:90]:  # Last 90 days
        entry = daily[date]
        lines.append(f"  - date: \"{date}\"\n")
        lines.append(f"    sources: {json.dumps(entry.get('sources', []))}\n")

        # Sleep
        if entry.get('sleep_hours'):
            lines.append(f"    sleep_hours: {entry['sleep_hours']}\n")
        if entry.get('sleep_score'):
            lines.append(f"    sleep_score: {entry['sleep_score']}\n")
        if entry.get('deep_sleep_hours'):
            lines.append(f"    deep_sleep: {entry['deep_sleep_hours']}h\n")

        # Activity
        if entry.get('steps'):
            lines.append(f"    steps: {entry['steps']}\n")
        if entry.get('active_calories'):
            lines.append(f"    active_calories: {entry['active_calories']}\n")

        # Heart
        if entry.get('resting_hr'):
            lines.append(f"    resting_hr: {entry['resting_hr']}\n")

        # Garmin-specific
        if entry.get('stress_avg'):
            lines.append(f"    stress_avg: {entry['stress_avg']}\n")
        if entry.get('body_battery_high'):
            lines.append(f"    body_battery: {entry.get('body_battery_low', '?')}-{entry['body_battery_high']}\n")

        # Oura-specific
        if entry.get('readiness_score'):
            lines.append(f"    readiness_score: {entry['readiness_score']}\n")
        if entry.get('hrv_balance'):
            lines.append(f"    hrv_balance: {entry['hrv_balance']}\n")

        lines.append("\n")

    log_path.write_text(''.join(lines), encoding='utf-8')
    print(f"  Daily log: {log_path} ({len(daily)} days)")

    # ── Workouts log ──
    if workouts:
        workout_path = OUTPUT_DIR / "workouts-data.yaml"
        wlines = [
            "# Workouts (auto-generated from vault)\n",
            f"# Last processed: {datetime.now().isoformat()}\n",
            f"# Workouts: {len(workouts)}\n\n",
            "workouts:\n",
        ]

        for w in workouts[:100]:  # Last 100 workouts
            wlines.append(f"  - date: \"{w['date']}\"\n")
            wlines.append(f"    name: \"{w['name']}\"\n")
            wlines.append(f"    type: \"{w['type']}\"\n")
            wlines.append(f"    duration_min: {w['duration_min']}\n")
            if w['distance_km']:
                wlines.append(f"    distance_km: {w['distance_km']}\n")
            if w['calories']:
                wlines.append(f"    calories: {w['calories']}\n")
            if w['avg_hr']:
                wlines.append(f"    avg_hr: {w['avg_hr']}\n")
            wlines.append("\n")

        workout_path.write_text(''.join(wlines), encoding='utf-8')
        print(f"  Workouts: {workout_path} ({len(workouts)} entries)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Process vault health data → life/health/")
    parser.add_argument('--days', type=int, help='Only process last N days')
    parser.add_argument('--source', choices=['garmin', 'oura', 'apple-health', 'all'],
                        default='all')
    args = parser.parse_args()

    print("Processing health data from vault...")
    merged = merge_health_data(cutoff_days=args.days)
    write_health_log(merged)
    print("\nHealth processing complete!")


if __name__ == '__main__':
    main()
