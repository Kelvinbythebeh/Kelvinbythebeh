#!/usr/bin/env python3
"""
Oura Ring → Google Drive / Local Sync

Pulls sleep, readiness, activity, and heart rate data from Oura API v2.
Saves raw JSON to Google Drive (or local), then transforms into health log entries.

Setup:
    1. Get your Personal Access Token from https://cloud.ouraring.com/personal-access-tokens
    2. Save to .config/oura_config.json: {"token": "YOUR_TOKEN"}
       Or set env: OURA_TOKEN=YOUR_TOKEN

Usage:
    python sync_oura.py                        # Sync last 7 days
    python sync_oura.py --days 30              # Sync last 30 days
    python sync_oura.py --from 2026-03-01 --to 2026-04-08
    python sync_oura.py --transform            # Also update health log
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
RAW_DIR = BASE_DIR / "data" / "raw" / "oura"
HEALTH_LOG = BASE_DIR / "life" / "health" / "log.yaml"

OURA_BASE = "https://api.ouraring.com/v2/usercollection"


def get_token() -> str:
    """Load Oura personal access token."""
    config_file = CONFIG_DIR / "oura_config.json"
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)['token']

    token = os.environ.get('OURA_TOKEN', '')
    if not token:
        print("ERROR: No Oura token found.")
        print("\nSetup:")
        print("1. Go to https://cloud.ouraring.com/personal-access-tokens")
        print("2. Create a Personal Access Token")
        print("3. Save to .config/oura_config.json:")
        print('   {"token": "YOUR_TOKEN_HERE"}')
        sys.exit(1)
    return token


def oura_get(endpoint: str, token: str, params: dict = None) -> dict:
    """Make authenticated GET request to Oura API v2."""
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(f"{OURA_BASE}/{endpoint}", headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


# ── Data Fetchers ────────────────────────────────────────────────────────────

def fetch_sleep(token: str, start: str, end: str) -> list:
    """Fetch daily sleep data."""
    data = oura_get('daily_sleep', token, {
        'start_date': start, 'end_date': end
    })
    return data.get('data', [])


def fetch_sleep_periods(token: str, start: str, end: str) -> list:
    """Fetch detailed sleep periods (stages, HR, HRV)."""
    data = oura_get('sleep', token, {
        'start_date': start, 'end_date': end
    })
    return data.get('data', [])


def fetch_readiness(token: str, start: str, end: str) -> list:
    """Fetch daily readiness scores."""
    data = oura_get('daily_readiness', token, {
        'start_date': start, 'end_date': end
    })
    return data.get('data', [])


def fetch_activity(token: str, start: str, end: str) -> list:
    """Fetch daily activity data."""
    data = oura_get('daily_activity', token, {
        'start_date': start, 'end_date': end
    })
    return data.get('data', [])


def fetch_heart_rate(token: str, start: str, end: str) -> list:
    """Fetch heart rate data."""
    data = oura_get('heartrate', token, {
        'start_datetime': f'{start}T00:00:00+00:00',
        'end_datetime': f'{end}T23:59:59+00:00',
    })
    return data.get('data', [])


def fetch_personal_info(token: str) -> dict:
    """Fetch user profile info."""
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(
        'https://api.ouraring.com/v2/usercollection/personal_info',
        headers=headers
    )
    resp.raise_for_status()
    return resp.json()


# ── Raw Data Storage ─────────────────────────────────────────────────────────

def save_raw(data: dict, data_type: str, date_range: str):
    """Save raw API response to data/raw/oura/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{data_type}_{date_range}.json"
    filepath = RAW_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Saved: {filepath.name} ({len(data)} records)")
    return filepath


# ── Transform to Health Log ──────────────────────────────────────────────────

def transform_to_health_entries(sleep_data: list, readiness_data: list,
                                 activity_data: list) -> list:
    """Transform Oura data into health log entries."""
    # Index by date
    readiness_by_date = {r['day']: r for r in readiness_data}
    activity_by_date = {a['day']: a for a in activity_data}

    entries = []
    for sleep in sleep_data:
        day = sleep['day']
        readiness = readiness_by_date.get(day, {})
        activity = activity_by_date.get(day, {})

        # Extract sleep duration (seconds → hours)
        sleep_seconds = sleep.get('contributors', {}).get('total_sleep', 0)
        sleep_hours = round(sleep_seconds / 3600, 1) if sleep_seconds > 100 else 0

        # Fallback: use the score-based estimate
        if sleep_hours == 0:
            sleep_score = sleep.get('score', 0)
            sleep_hours = round(sleep_score * 0.09, 1)  # rough estimate

        entry = {
            'date': day,
            'source': 'oura',
            'sleep': sleep_hours if sleep_hours > 0 else None,
            'sleep_score': sleep.get('score'),
            'sleep_efficiency': sleep.get('contributors', {}).get('efficiency'),
            'readiness_score': readiness.get('score'),
            'hrv_balance': readiness.get('contributors', {}).get('hrv_balance'),
            'resting_hr': readiness.get('contributors', {}).get('resting_heart_rate'),
            'active_calories': activity.get('active_calories'),
            'steps': activity.get('steps'),
            'activity_score': activity.get('score'),
        }

        # Clean out None values
        entry = {k: v for k, v in entry.items() if v is not None}
        entries.append(entry)

    return entries


def update_health_log(entries: list):
    """Append Oura data to the health log."""
    import yaml  # optional, fallback to manual if not available

    if not entries:
        return

    print(f"\n  Transformed {len(entries)} days of Oura data")
    print("  Sample entry:")
    sample = entries[-1]
    for k, v in sample.items():
        print(f"    {k}: {v}")

    # Save as a separate Oura-specific log for Claude to read
    oura_log = BASE_DIR / "life" / "health" / "oura-data.yaml"
    oura_log.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "# Oura Ring Data - Auto-synced\n"
        f"# Last sync: {datetime.now().isoformat()}\n"
        f"# Records: {len(entries)}\n\n"
        "entries:\n"
    )

    yaml_entries = ""
    for entry in sorted(entries, key=lambda x: x['date']):
        yaml_entries += f"  - date: \"{entry['date']}\"\n"
        for k, v in entry.items():
            if k == 'date':
                continue
            if isinstance(v, str):
                yaml_entries += f"    {k}: \"{v}\"\n"
            else:
                yaml_entries += f"    {k}: {v}\n"
        yaml_entries += "\n"

    oura_log.write_text(header + yaml_entries, encoding='utf-8')
    print(f"  Written to: {oura_log}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync Oura Ring → Life OS")
    parser.add_argument('--days', type=int, default=7, help='Days to look back')
    parser.add_argument('--from', dest='start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--transform', action='store_true',
                        help='Transform raw data into health log entries')
    parser.add_argument('--raw-only', action='store_true',
                        help='Only save raw data, skip transform')
    args = parser.parse_args()

    token = get_token()

    end_date = args.end or datetime.now().strftime('%Y-%m-%d')
    if args.start:
        start_date = args.start
    else:
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    date_range = f"{start_date}_to_{end_date}"
    print(f"Syncing Oura data: {start_date} → {end_date}")

    # Fetch all data types
    print("\nFetching from Oura API v2...")

    sleep_daily = fetch_sleep(token, start_date, end_date)
    save_raw(sleep_daily, 'daily_sleep', date_range)

    sleep_periods = fetch_sleep_periods(token, start_date, end_date)
    save_raw(sleep_periods, 'sleep_periods', date_range)

    readiness = fetch_readiness(token, start_date, end_date)
    save_raw(readiness, 'daily_readiness', date_range)

    activity = fetch_activity(token, start_date, end_date)
    save_raw(activity, 'daily_activity', date_range)

    # Heart rate can be large, fetch per day
    print("  Fetching heart rate (daily)...")
    all_hr = []
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    while current <= end_dt:
        day_str = current.strftime('%Y-%m-%d')
        try:
            hr = fetch_heart_rate(token, day_str, day_str)
            all_hr.extend(hr)
        except Exception:
            pass  # Some days may not have data
        current += timedelta(days=1)
    save_raw(all_hr, 'heart_rate', date_range)

    print(f"\nRaw data saved to {RAW_DIR}")

    # Transform to health entries
    if not args.raw_only:
        entries = transform_to_health_entries(sleep_daily, readiness, activity)
        update_health_log(entries)

    print("\nOura sync complete!")


if __name__ == '__main__':
    main()
