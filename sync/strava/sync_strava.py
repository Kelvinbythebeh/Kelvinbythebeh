#!/usr/bin/env python3
"""
Strava → Life OS Sync

Pulls workout/activity data from Strava API into fitness tracker.

Setup:
    1. Create app at https://www.strava.com/settings/api
    2. Save to .config/strava_config.json:
       {"client_id": "YOUR_ID", "client_secret": "YOUR_SECRET"}
    3. Run: python sync_strava.py --setup

Usage:
    python sync_strava.py                  # Last 30 activities
    python sync_strava.py --days 90        # Last 90 days
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

try:
    import requests
except ImportError:
    print("Install: pip install requests")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
TOKEN_FILE = CONFIG_DIR / "strava_token.json"
RAW_DIR = BASE_DIR / "data" / "raw" / "strava"

STRAVA_AUTH = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN = "https://www.strava.com/oauth/token"
STRAVA_API = "https://www.strava.com/api/v3"
REDIRECT_URI = "http://localhost:8402/callback"


def load_config() -> dict:
    config_file = CONFIG_DIR / "strava_config.json"
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {
        'client_id': os.environ.get('STRAVA_CLIENT_ID', ''),
        'client_secret': os.environ.get('STRAVA_CLIENT_SECRET', ''),
    }


class CallbackHandler(BaseHTTPRequestHandler):
    code = None
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        CallbackHandler.code = query.get('code', [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h1>Strava connected!</h1><p>Close this window.</p>")
    def log_message(self, *args): pass


def authenticate(config: dict) -> str:
    """OAuth2 flow for Strava."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            token = json.load(f)
        if time.time() < token.get('expires_at', 0):
            return token['access_token']
        # Refresh
        resp = requests.post(STRAVA_TOKEN, data={
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'grant_type': 'refresh_token',
            'refresh_token': token['refresh_token'],
        })
        if resp.status_code == 200:
            new_token = resp.json()
            with open(TOKEN_FILE, 'w') as f:
                json.dump(new_token, f)
            return new_token['access_token']

    if not config.get('client_id'):
        print("ERROR: No Strava credentials.")
        print("1. Go to https://www.strava.com/settings/api")
        print('2. Save to .config/strava_config.json:')
        print('   {"client_id": "ID", "client_secret": "SECRET"}')
        sys.exit(1)

    auth_url = f"{STRAVA_AUTH}?{urlencode({'client_id': config['client_id'], 'redirect_uri': REDIRECT_URI, 'response_type': 'code', 'scope': 'activity:read_all'})}"
    webbrowser.open(auth_url)
    server = HTTPServer(('localhost', 8402), CallbackHandler)
    server.handle_request()

    resp = requests.post(STRAVA_TOKEN, data={
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'code': CallbackHandler.code,
        'grant_type': 'authorization_code',
    })
    resp.raise_for_status()
    token = resp.json()
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token, f)
    return token['access_token']


def fetch_activities(token: str, days: int = 30) -> list:
    after = int((datetime.now() - timedelta(days=days)).timestamp())
    headers = {'Authorization': f'Bearer {token}'}
    activities = []
    page = 1
    while True:
        resp = requests.get(f"{STRAVA_API}/athlete/activities",
                           headers=headers, params={'after': after, 'page': page, 'per_page': 50})
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
    return activities


def save_activities(activities: list):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"activities_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_path, 'w') as f:
        json.dump(activities, f, indent=2)

    # YAML for Claude
    log_path = BASE_DIR / "life" / "fitness" / "strava-data.yaml"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Strava Activities - Auto-synced\n",
        f"# Last sync: {datetime.now().isoformat()}\n",
        f"# Activities: {len(activities)}\n\n",
        "activities:\n",
    ]

    for a in sorted(activities, key=lambda x: x.get('start_date', ''), reverse=True):
        lines.append(f"  - name: \"{a.get('name', '')}\"\n")
        lines.append(f"    type: \"{a.get('type', '')}\"\n")
        lines.append(f"    date: \"{a.get('start_date', '')[:10]}\"\n")
        lines.append(f"    duration_min: {round(a.get('moving_time', 0) / 60, 1)}\n")
        lines.append(f"    distance_km: {round(a.get('distance', 0) / 1000, 2)}\n")
        lines.append(f"    calories: {a.get('calories', 0)}\n")
        if a.get('average_heartrate'):
            lines.append(f"    avg_hr: {a['average_heartrate']}\n")
        if a.get('total_elevation_gain'):
            lines.append(f"    elevation_m: {a['total_elevation_gain']}\n")
        lines.append("\n")

    log_path.write_text(''.join(lines), encoding='utf-8')
    print(f"  Activities: {len(activities)}")
    print(f"  Saved: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Sync Strava → Life OS")
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--setup', action='store_true')
    args = parser.parse_args()

    config = load_config()
    token = authenticate(config)

    if args.setup:
        print("Strava connected!")
        return

    print(f"Fetching Strava activities (last {args.days} days)...")
    activities = fetch_activities(token, args.days)
    save_activities(activities)
    print("\nStrava sync complete!")


if __name__ == '__main__':
    main()
