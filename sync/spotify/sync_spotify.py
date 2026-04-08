#!/usr/bin/env python3
"""
Spotify → Life OS Sync

Tracks listening habits for mood/productivity correlation.

Setup:
    1. Create app at https://developer.spotify.com/dashboard
    2. Set redirect URI: http://localhost:8403/callback
    3. Save to .config/spotify_config.json:
       {"client_id": "ID", "client_secret": "SECRET"}

Usage:
    python sync_spotify.py                 # Recent listening history
    python sync_spotify.py --top-tracks    # Top tracks this month
"""

import argparse
import json
import os
import sys
import time
import webbrowser
import base64
from datetime import datetime
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
TOKEN_FILE = CONFIG_DIR / "spotify_token.json"
RAW_DIR = BASE_DIR / "data" / "raw" / "spotify"

REDIRECT_URI = "http://localhost:8403/callback"
SCOPES = "user-read-recently-played user-top-read user-read-currently-playing"


def load_config() -> dict:
    config_file = CONFIG_DIR / "spotify_config.json"
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {
        'client_id': os.environ.get('SPOTIFY_CLIENT_ID', ''),
        'client_secret': os.environ.get('SPOTIFY_CLIENT_SECRET', ''),
    }


class CallbackHandler(BaseHTTPRequestHandler):
    code = None
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        CallbackHandler.code = query.get('code', [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h1>Spotify connected!</h1>")
    def log_message(self, *args): pass


def authenticate(config: dict) -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            token = json.load(f)
        if time.time() < token.get('expires_at', 0):
            return token['access_token']
        if 'refresh_token' in token:
            auth_header = base64.b64encode(
                f"{config['client_id']}:{config['client_secret']}".encode()
            ).decode()
            resp = requests.post('https://accounts.spotify.com/api/token',
                headers={'Authorization': f'Basic {auth_header}'},
                data={'grant_type': 'refresh_token', 'refresh_token': token['refresh_token']})
            if resp.status_code == 200:
                new_token = resp.json()
                new_token['expires_at'] = time.time() + new_token.get('expires_in', 3600)
                new_token['refresh_token'] = token['refresh_token']
                with open(TOKEN_FILE, 'w') as f:
                    json.dump(new_token, f)
                return new_token['access_token']

    auth_url = f"https://accounts.spotify.com/authorize?{urlencode({'client_id': config['client_id'], 'response_type': 'code', 'redirect_uri': REDIRECT_URI, 'scope': SCOPES})}"
    webbrowser.open(auth_url)
    server = HTTPServer(('localhost', 8403), CallbackHandler)
    server.handle_request()

    auth_header = base64.b64encode(
        f"{config['client_id']}:{config['client_secret']}".encode()
    ).decode()
    resp = requests.post('https://accounts.spotify.com/api/token',
        headers={'Authorization': f'Basic {auth_header}'},
        data={'grant_type': 'authorization_code', 'code': CallbackHandler.code, 'redirect_uri': REDIRECT_URI})
    resp.raise_for_status()
    token = resp.json()
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token, f)
    return token['access_token']


def fetch_recent(token: str) -> list:
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get('https://api.spotify.com/v1/me/player/recently-played',
                        headers=headers, params={'limit': 50})
    resp.raise_for_status()
    return resp.json().get('items', [])


def save_listening(items: list):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"recent_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_path, 'w') as f:
        json.dump(items, f, indent=2)

    log_path = BASE_DIR / "life" / "mental-wellness" / "spotify-data.yaml"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Spotify Listening - Auto-synced\n",
        f"# Last sync: {datetime.now().isoformat()}\n",
        f"# Tracks: {len(items)}\n\n",
        "recent:\n",
    ]

    for item in items:
        track = item.get('track', {})
        artists = ', '.join(a['name'] for a in track.get('artists', []))
        played_at = item.get('played_at', '')[:16].replace('T', ' ')
        lines.append(f"  - track: \"{track.get('name', '')}\"\n")
        lines.append(f"    artist: \"{artists}\"\n")
        lines.append(f"    played_at: \"{played_at}\"\n")
        lines.append(f"    duration_min: {round(track.get('duration_ms', 0) / 60000, 1)}\n")
        lines.append("\n")

    log_path.write_text(''.join(lines), encoding='utf-8')
    print(f"  Tracks: {len(items)}")
    print(f"  Saved: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Sync Spotify → Life OS")
    parser.add_argument('--setup', action='store_true')
    args = parser.parse_args()

    config = load_config()
    token = authenticate(config)

    if args.setup:
        print("Spotify connected!")
        return

    print("Fetching recent listening...")
    items = fetch_recent(token)
    save_listening(items)
    print("\nSpotify sync complete!")


if __name__ == '__main__':
    main()
