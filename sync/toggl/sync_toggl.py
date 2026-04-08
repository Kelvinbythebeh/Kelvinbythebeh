#!/usr/bin/env python3
"""
Toggl Track → Vault (Google Drive) Sync

Pulls time entries, projects, and summaries from Toggl Track API.
Great for tracking where your time actually goes.

Setup:
    1. Get API token from https://track.toggl.com/profile (scroll to bottom)
    2. Save to .config/toggl_config.json: {"token": "YOUR_TOKEN"}
       Or set env: TOGGL_TOKEN=YOUR_TOKEN

Usage:
    python sync_toggl.py                       # Last 7 days
    python sync_toggl.py --days 30             # Last 30 days
    python sync_toggl.py --from 2026-03-01 --to 2026-04-08
    python sync_toggl.py --summary             # Weekly summary report
"""

import argparse
import base64
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install: pip install requests")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
VAULT_DIR = BASE_DIR / "vault" / "toggl"

TOGGL_API = "https://api.track.toggl.com/api/v9"


def get_auth() -> tuple[str, str]:
    """Get Toggl API token for basic auth."""
    config_file = CONFIG_DIR / "toggl_config.json"
    token = os.environ.get('TOGGL_TOKEN', '')

    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
            token = config.get('token', token)

    if not token:
        print("ERROR: No Toggl token.")
        print("\nSetup:")
        print("1. Go to https://track.toggl.com/profile")
        print("2. Scroll to 'API Token' at the bottom")
        print('3. Save to .config/toggl_config.json: {"token": "YOUR_TOKEN"}')
        sys.exit(1)

    return (token, 'api_token')


def toggl_get(endpoint: str, auth: tuple, params: dict = None) -> dict | list:
    """Make authenticated GET to Toggl API."""
    resp = requests.get(
        f"{TOGGL_API}/{endpoint}",
        auth=auth,
        params=params,
        headers={'Content-Type': 'application/json'}
    )
    resp.raise_for_status()
    return resp.json()


def save_to_vault(data, data_type: str, date_str: str):
    """Save raw data to vault/toggl/."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = VAULT_DIR / f"{data_type}_{date_str}.json"
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  → vault/toggl/{filepath.name}")
    return filepath


# ── Fetchers ─────────────────────────────────────────────────────────────────

def fetch_me(auth: tuple) -> dict:
    """Get user profile and workspace info."""
    return toggl_get('me', auth)


def fetch_workspaces(auth: tuple) -> list:
    """Get all workspaces."""
    return toggl_get('workspaces', auth)


def fetch_projects(auth: tuple, workspace_id: int) -> list:
    """Get all projects in a workspace."""
    try:
        return toggl_get(f'workspaces/{workspace_id}/projects', auth) or []
    except Exception:
        return []


def fetch_time_entries(auth: tuple, start: str, end: str) -> list:
    """Fetch all time entries in date range."""
    # Toggl API v9 uses ISO 8601
    start_iso = f"{start}T00:00:00Z"
    end_iso = f"{end}T23:59:59Z"

    entries = toggl_get('me/time_entries', auth, {
        'start_date': start_iso,
        'end_date': end_iso,
    })
    return entries or []


def fetch_clients(auth: tuple, workspace_id: int) -> list:
    """Get all clients."""
    try:
        return toggl_get(f'workspaces/{workspace_id}/clients', auth) or []
    except Exception:
        return []


def fetch_tags(auth: tuple, workspace_id: int) -> list:
    """Get all tags."""
    try:
        return toggl_get(f'workspaces/{workspace_id}/tags', auth) or []
    except Exception:
        return []


# ── Analysis ─────────────────────────────────────────────────────────────────

def analyze_entries(entries: list, projects: dict, date_range: str) -> dict:
    """Analyze time entries into useful summaries."""
    by_project = defaultdict(float)
    by_date = defaultdict(float)
    by_day_of_week = defaultdict(float)
    by_tag = defaultdict(float)
    total_seconds = 0

    for entry in entries:
        duration = entry.get('duration', 0)
        if duration < 0:
            continue  # Running timer

        total_seconds += duration
        hours = duration / 3600

        # By project
        project_id = entry.get('project_id')
        project_name = projects.get(project_id, 'No Project')
        by_project[project_name] += hours

        # By date
        start = entry.get('start', '')[:10]
        if start:
            by_date[start] += hours

            # By day of week
            try:
                dt = datetime.strptime(start, '%Y-%m-%d')
                day_name = dt.strftime('%A')
                by_day_of_week[day_name] += hours
            except ValueError:
                pass

        # By tag
        for tag in entry.get('tags', []):
            by_tag[tag] += hours

    return {
        'date_range': date_range,
        'total_hours': round(total_seconds / 3600, 1),
        'total_entries': len(entries),
        'by_project': {k: round(v, 1) for k, v in sorted(by_project.items(), key=lambda x: -x[1])},
        'by_date': {k: round(v, 1) for k, v in sorted(by_date.items())},
        'by_day_of_week': {k: round(v, 1) for k, v in sorted(by_day_of_week.items())},
        'by_tag': {k: round(v, 1) for k, v in sorted(by_tag.items(), key=lambda x: -x[1])},
        'avg_hours_per_day': round(total_seconds / 3600 / max(len(by_date), 1), 1),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync Toggl Track → Vault")
    parser.add_argument('--days', type=int, default=7, help='Days to look back')
    parser.add_argument('--from', dest='start', help='Start date YYYY-MM-DD')
    parser.add_argument('--to', dest='end', help='End date YYYY-MM-DD')
    parser.add_argument('--summary', action='store_true', help='Generate time summary')
    args = parser.parse_args()

    end_date = args.end or datetime.now().strftime('%Y-%m-%d')
    start_date = args.start or (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    date_range = f"{start_date}_to_{end_date}"

    print(f"Toggl Track: {start_date} → {end_date}")

    auth = get_auth()

    # Get profile and workspace
    me = fetch_me(auth)
    workspace_id = me.get('default_workspace_id')
    print(f"  User: {me.get('fullname', me.get('email', 'unknown'))}")
    print(f"  Workspace: {workspace_id}")

    # Fetch projects for name mapping
    projects_list = fetch_projects(auth, workspace_id)
    project_map = {p['id']: p['name'] for p in projects_list}
    save_to_vault(projects_list, 'projects', date_range)

    # Fetch clients and tags
    clients = fetch_clients(auth, workspace_id)
    tags = fetch_tags(auth, workspace_id)
    save_to_vault(clients, 'clients', date_range)
    save_to_vault(tags, 'tags', date_range)

    # Fetch time entries
    print("\n  Fetching time entries...")
    entries = fetch_time_entries(auth, start_date, end_date)
    save_to_vault(entries, 'time_entries', date_range)
    print(f"    {len(entries)} time entries")

    # Analyze
    summary = analyze_entries(entries, project_map, date_range)
    save_to_vault(summary, 'summary', date_range)

    # Print summary
    print(f"\n  Total tracked: {summary['total_hours']}h across {summary['total_entries']} entries")
    print(f"  Avg per day: {summary['avg_hours_per_day']}h")
    print(f"\n  By project:")
    for project, hours in list(summary['by_project'].items())[:10]:
        print(f"    {project}: {hours}h")

    if summary['by_tag']:
        print(f"\n  By tag:")
        for tag, hours in list(summary['by_tag'].items())[:10]:
            print(f"    #{tag}: {hours}h")

    print(f"\nToggl data saved to vault/toggl/")


if __name__ == '__main__':
    main()
