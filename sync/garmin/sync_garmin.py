#!/usr/bin/env python3
"""
Garmin Connect → Vault (Google Drive) Sync

Pulls sleep, activity, body composition, heart rate, stress, and workout
data from Garmin Connect into the vault for processing.

Uses the garminconnect Python library (unofficial but widely used).

Setup:
    pip install garminconnect
    Save to .config/garmin_config.json:
    {"email": "your@email.com", "password": "your_password"}

    Or use environment variables:
    GARMIN_EMAIL=your@email.com
    GARMIN_PASSWORD=your_password

Usage:
    python sync_garmin.py                      # Last 7 days
    python sync_garmin.py --days 30            # Last 30 days
    python sync_garmin.py --from 2026-03-01 --to 2026-04-08
    python sync_garmin.py --what sleep         # Only sleep data
    python sync_garmin.py --what all           # Everything
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from garminconnect import Garmin
except ImportError:
    print("Install garminconnect: pip install garminconnect")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
VAULT_DIR = BASE_DIR / "vault" / "garmin"
TOKEN_FILE = CONFIG_DIR / "garmin_session.json"


def get_client() -> Garmin:
    """Authenticate with Garmin Connect."""
    config_file = CONFIG_DIR / "garmin_config.json"

    email = os.environ.get('GARMIN_EMAIL', '')
    password = os.environ.get('GARMIN_PASSWORD', '')

    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
            email = config.get('email', email)
            password = config.get('password', password)

    if not email or not password:
        print("ERROR: No Garmin credentials.")
        print("\nSetup:")
        print('  Save to .config/garmin_config.json:')
        print('  {"email": "your@email.com", "password": "your_password"}')
        sys.exit(1)

    client = Garmin(email, password)

    # Try to reuse session
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE) as f:
                session_data = json.load(f)
            client.login(session_data)
            return client
        except Exception:
            pass

    # Fresh login
    client.login()

    # Save session for reuse
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(client.session_data, f)
    except Exception:
        pass

    return client


def save_to_vault(data, data_type: str, date_str: str):
    """Save raw data to vault/garmin/ for processing."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = VAULT_DIR / f"{data_type}_{date_str}.json"
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  → vault/garmin/{filepath.name}")
    return filepath


# ── Data Fetchers ────────────────────────────────────────────────────────────

def fetch_sleep(client: Garmin, start: str, end: str):
    """Fetch daily sleep summaries."""
    print("\n  Fetching sleep data...")
    current = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_data = []

    while current <= end_dt:
        day = current.strftime('%Y-%m-%d')
        try:
            data = client.get_sleep_data(day)
            if data:
                all_data.append({'date': day, 'data': data})
        except Exception as e:
            print(f"    Sleep {day}: {e}")
        current += timedelta(days=1)

    save_to_vault(all_data, 'sleep', f"{start}_to_{end}")
    print(f"    {len(all_data)} days of sleep data")
    return all_data


def fetch_activities(client: Garmin, start: str, end: str):
    """Fetch activity summaries (daily steps, calories, etc.)."""
    print("\n  Fetching daily activities...")
    current = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_data = []

    while current <= end_dt:
        day = current.strftime('%Y-%m-%d')
        try:
            data = client.get_stats(day)
            if data:
                all_data.append({'date': day, 'data': data})
        except Exception as e:
            print(f"    Activity {day}: {e}")
        current += timedelta(days=1)

    save_to_vault(all_data, 'daily_stats', f"{start}_to_{end}")
    print(f"    {len(all_data)} days of activity data")
    return all_data


def fetch_workouts(client: Garmin, start: str, end: str):
    """Fetch logged workouts/exercises."""
    print("\n  Fetching workouts...")
    try:
        # Get recent activities (up to 100)
        activities = client.get_activities(0, 100)

        # Filter by date range
        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')

        filtered = []
        for a in activities:
            activity_date = a.get('startTimeLocal', '')[:10]
            try:
                a_dt = datetime.strptime(activity_date, '%Y-%m-%d')
                if start_dt <= a_dt <= end_dt:
                    filtered.append(a)
            except ValueError:
                pass

        save_to_vault(filtered, 'workouts', f"{start}_to_{end}")
        print(f"    {len(filtered)} workouts")
        return filtered
    except Exception as e:
        print(f"    Workouts error: {e}")
        return []


def fetch_heart_rate(client: Garmin, start: str, end: str):
    """Fetch heart rate data."""
    print("\n  Fetching heart rate...")
    current = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_data = []

    while current <= end_dt:
        day = current.strftime('%Y-%m-%d')
        try:
            data = client.get_heart_rates(day)
            if data:
                all_data.append({'date': day, 'data': data})
        except Exception as e:
            print(f"    HR {day}: {e}")
        current += timedelta(days=1)

    save_to_vault(all_data, 'heart_rate', f"{start}_to_{end}")
    print(f"    {len(all_data)} days of HR data")
    return all_data


def fetch_stress(client: Garmin, start: str, end: str):
    """Fetch stress level data."""
    print("\n  Fetching stress data...")
    current = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_data = []

    while current <= end_dt:
        day = current.strftime('%Y-%m-%d')
        try:
            data = client.get_stress_data(day)
            if data:
                all_data.append({'date': day, 'data': data})
        except Exception as e:
            print(f"    Stress {day}: {e}")
        current += timedelta(days=1)

    save_to_vault(all_data, 'stress', f"{start}_to_{end}")
    print(f"    {len(all_data)} days of stress data")
    return all_data


def fetch_body_composition(client: Garmin, start: str, end: str):
    """Fetch weight, body fat, BMI."""
    print("\n  Fetching body composition...")
    try:
        data = client.get_body_composition(start, end)
        save_to_vault(data, 'body_composition', f"{start}_to_{end}")
        weights = data.get('dateWeightList', []) if isinstance(data, dict) else []
        print(f"    {len(weights)} weight entries")
        return data
    except Exception as e:
        print(f"    Body comp error: {e}")
        return {}


def fetch_hydration(client: Garmin, start: str, end: str):
    """Fetch hydration/water intake."""
    print("\n  Fetching hydration...")
    current = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_data = []

    while current <= end_dt:
        day = current.strftime('%Y-%m-%d')
        try:
            data = client.get_hydration_data(day)
            if data:
                all_data.append({'date': day, 'data': data})
        except Exception as e:
            pass  # Hydration tracking might not be enabled
        current += timedelta(days=1)

    if all_data:
        save_to_vault(all_data, 'hydration', f"{start}_to_{end}")
        print(f"    {len(all_data)} days of hydration data")
    return all_data


def fetch_respiration(client: Garmin, start: str, end: str):
    """Fetch SpO2 and respiration data."""
    print("\n  Fetching respiration/SpO2...")
    current = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')
    all_data = []

    while current <= end_dt:
        day = current.strftime('%Y-%m-%d')
        try:
            data = client.get_respiration_data(day)
            if data:
                all_data.append({'date': day, 'data': data})
        except Exception:
            pass
        current += timedelta(days=1)

    if all_data:
        save_to_vault(all_data, 'respiration', f"{start}_to_{end}")
        print(f"    {len(all_data)} days of respiration data")
    return all_data


# ── Main ─────────────────────────────────────────────────────────────────────

FETCH_MAP = {
    'sleep': fetch_sleep,
    'activities': fetch_activities,
    'workouts': fetch_workouts,
    'heart_rate': fetch_heart_rate,
    'stress': fetch_stress,
    'body': fetch_body_composition,
    'hydration': fetch_hydration,
    'respiration': fetch_respiration,
}


def main():
    parser = argparse.ArgumentParser(description="Sync Garmin Connect → Vault")
    parser.add_argument('--days', type=int, default=7, help='Days to look back')
    parser.add_argument('--from', dest='start', help='Start date YYYY-MM-DD')
    parser.add_argument('--to', dest='end', help='End date YYYY-MM-DD')
    parser.add_argument('--what', default='all',
                        help='What to fetch: all, sleep, activities, workouts, heart_rate, stress, body, hydration, respiration')
    args = parser.parse_args()

    end_date = args.end or datetime.now().strftime('%Y-%m-%d')
    start_date = args.start or (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    print(f"Garmin Connect: {start_date} → {end_date}")

    client = get_client()
    print("  Authenticated with Garmin Connect")

    if args.what == 'all':
        fetchers = list(FETCH_MAP.values())
    else:
        fetchers = [FETCH_MAP[args.what]]

    for fetch_fn in fetchers:
        try:
            fetch_fn(client, start_date, end_date)
        except Exception as e:
            print(f"  Error in {fetch_fn.__name__}: {e}")

    print(f"\nGarmin data saved to vault/garmin/")
    print("Run processors to transform into life/ trackers.")


if __name__ == '__main__':
    main()
