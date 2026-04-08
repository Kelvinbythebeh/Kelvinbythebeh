#!/usr/bin/env python3
"""
Google Drive Bridge - The central hub for all data flow.

All data sources sync TO Google Drive (the cloud storage layer).
This script syncs FROM Google Drive INTO this repo (the AI brain).

Google Drive Structure:
    Life OS/
    ├── raw/                    # Raw API dumps from all sources
    │   ├── oura/               # Sleep, readiness, activity JSON
    │   ├── apple-health/       # Health export XML/JSON
    │   ├── banking/            # Transaction CSVs/JSONs
    │   ├── google-calendar/    # Events JSON
    │   └── .../                # Any new source goes here
    ├── notes/                  # Notes from capture apps
    │   ├── apple-notes/        # Exported from Shortcuts
    │   └── onenote/            # Exported from OneNote
    └── processed/              # AI-processed summaries (written back)

Usage:
    python drive_bridge.py --setup              # First-time OAuth setup
    python drive_bridge.py --pull               # Pull all raw data to local repo
    python drive_bridge.py --pull --folder oura # Pull specific source
    python drive_bridge.py --push               # Push processed data back to Drive
    python drive_bridge.py --list               # List what's in Drive
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
except ImportError:
    print("Install Google API client:")
    print("  pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

import argparse
import io

# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
TOKEN_FILE = CONFIG_DIR / "google_token.json"
CREDENTIALS_FILE = CONFIG_DIR / "google_credentials.json"
NOTES_DIR = BASE_DIR / "notes"
RAW_DATA_DIR = BASE_DIR / "data" / "raw"

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.file',
]

DRIVE_ROOT_FOLDER = "Life OS"  # Top-level folder in Google Drive


# ── Auth ─────────────────────────────────────────────────────────────────────

def authenticate() -> Credentials:
    """Get valid Google OAuth2 credentials."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not CREDENTIALS_FILE.exists():
            print("ERROR: Google credentials not found.")
            print("\nSetup steps:")
            print("1. Go to https://console.cloud.google.com/apis/credentials")
            print("2. Create OAuth 2.0 Client ID (Desktop app)")
            print("3. Download JSON → save as .config/google_credentials.json")
            print("4. Enable Google Drive API in your project")
            print("5. Run: python drive_bridge.py --setup")
            sys.exit(1)

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=8401)

    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())

    return creds


def get_service():
    """Build the Google Drive API service."""
    creds = authenticate()
    return build('drive', 'v3', credentials=creds)


# ── Drive Operations ─────────────────────────────────────────────────────────

def find_folder(service, name: str, parent_id: str = None) -> str | None:
    """Find a folder by name in Drive."""
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def find_or_create_folder(service, name: str, parent_id: str = None) -> str:
    """Find or create a folder in Drive."""
    folder_id = find_folder(service, name, parent_id)
    if folder_id:
        return folder_id

    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if parent_id:
        metadata['parents'] = [parent_id]

    folder = service.files().create(body=metadata, fields='id').execute()
    print(f"  Created folder: {name}")
    return folder['id']


def ensure_drive_structure(service) -> dict:
    """Ensure the Life OS folder structure exists in Google Drive."""
    root_id = find_or_create_folder(service, DRIVE_ROOT_FOLDER)

    folders = {
        'root': root_id,
        'raw': find_or_create_folder(service, 'raw', root_id),
        'notes': find_or_create_folder(service, 'notes', root_id),
        'processed': find_or_create_folder(service, 'processed', root_id),
    }

    raw_id = folders['raw']
    folders['raw_oura'] = find_or_create_folder(service, 'oura', raw_id)
    folders['raw_apple_health'] = find_or_create_folder(service, 'apple-health', raw_id)
    folders['raw_banking'] = find_or_create_folder(service, 'banking', raw_id)
    folders['raw_calendar'] = find_or_create_folder(service, 'google-calendar', raw_id)
    folders['raw_strava'] = find_or_create_folder(service, 'strava', raw_id)
    folders['raw_spotify'] = find_or_create_folder(service, 'spotify', raw_id)
    folders['raw_screen_time'] = find_or_create_folder(service, 'screen-time', raw_id)
    folders['raw_todoist'] = find_or_create_folder(service, 'todoist', raw_id)

    notes_id = folders['notes']
    folders['notes_apple'] = find_or_create_folder(service, 'apple-notes', notes_id)
    folders['notes_onenote'] = find_or_create_folder(service, 'onenote', notes_id)

    return folders


def list_files_in_folder(service, folder_id: str, max_results: int = 100) -> list:
    """List all files in a Drive folder."""
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, modifiedTime, size)",
        pageSize=max_results,
        orderBy="modifiedTime desc"
    ).execute()
    return results.get('files', [])


def download_file(service, file_id: str, dest_path: Path):
    """Download a file from Drive to local path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def upload_file(service, local_path: Path, folder_id: str, mime_type: str = None):
    """Upload a local file to a Drive folder."""
    if not mime_type:
        ext = local_path.suffix.lower()
        mime_map = {
            '.json': 'application/json',
            '.yaml': 'text/yaml',
            '.yml': 'text/yaml',
            '.md': 'text/markdown',
            '.csv': 'text/csv',
            '.txt': 'text/plain',
        }
        mime_type = mime_map.get(ext, 'application/octet-stream')

    # Check if file already exists
    existing = service.files().list(
        q=f"name = '{local_path.name}' and '{folder_id}' in parents and trashed = false",
        fields="files(id)"
    ).execute().get('files', [])

    media = MediaFileUpload(str(local_path), mimetype=mime_type)

    if existing:
        service.files().update(
            fileId=existing[0]['id'], media_body=media
        ).execute()
    else:
        metadata = {'name': local_path.name, 'parents': [folder_id]}
        service.files().create(
            body=metadata, media_body=media, fields='id'
        ).execute()


# ── Pull: Drive → Local Repo ────────────────────────────────────────────────

SOURCE_MAP = {
    'oura': ('raw_oura', 'data/raw/oura'),
    'apple-health': ('raw_apple_health', 'data/raw/apple-health'),
    'banking': ('raw_banking', 'data/raw/banking'),
    'calendar': ('raw_calendar', 'data/raw/google-calendar'),
    'strava': ('raw_strava', 'data/raw/strava'),
    'spotify': ('raw_spotify', 'data/raw/spotify'),
    'screen-time': ('raw_screen_time', 'data/raw/screen-time'),
    'todoist': ('raw_todoist', 'data/raw/todoist'),
    'apple-notes': ('notes_apple', 'notes/apple-notes'),
    'onenote': ('notes_onenote', 'notes/onenote'),
}


def pull_from_drive(service, folders: dict, source_filter: str = None):
    """Pull raw data from Google Drive into local repo."""
    print("\n" + "=" * 60)
    print("PULLING FROM GOOGLE DRIVE → LOCAL REPO")
    print("=" * 60)

    total = 0

    for source_name, (folder_key, local_path) in SOURCE_MAP.items():
        if source_filter and source_filter != source_name:
            continue

        folder_id = folders.get(folder_key)
        if not folder_id:
            continue

        files = list_files_in_folder(service, folder_id)
        if not files:
            continue

        dest_dir = BASE_DIR / local_path
        dest_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n  {source_name}: {len(files)} files")
        for f in files:
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                continue
            dest = dest_dir / f['name']
            download_file(service, f['id'], dest)
            print(f"    ↓ {f['name']}")
            total += 1

    print(f"\nPulled {total} files total.")


def push_to_drive(service, folders: dict):
    """Push processed data back to Google Drive."""
    print("\n" + "=" * 60)
    print("PUSHING PROCESSED DATA → GOOGLE DRIVE")
    print("=" * 60)

    processed_id = folders['processed']
    processed_dir = BASE_DIR / "dashboards"

    if not processed_dir.exists():
        print("No processed data to push.")
        return

    total = 0
    for f in processed_dir.iterdir():
        if f.is_file():
            upload_file(service, f, processed_id)
            print(f"  ↑ {f.name}")
            total += 1

    # Also push the life tracker summaries
    for tracker in ['life/me.yaml', 'life/goals.yaml', 'life/finance/log.yaml',
                     'life/health/log.yaml', 'life/tasks.yaml']:
        path = BASE_DIR / tracker
        if path.exists():
            upload_file(service, path, processed_id)
            print(f"  ↑ {tracker}")
            total += 1

    print(f"\nPushed {total} files.")


def list_drive_contents(service, folders: dict):
    """Show what's in each Drive folder."""
    print("\n" + "=" * 60)
    print(f"GOOGLE DRIVE: {DRIVE_ROOT_FOLDER}")
    print("=" * 60)

    for source_name, (folder_key, _) in SOURCE_MAP.items():
        folder_id = folders.get(folder_key)
        if not folder_id:
            continue

        files = list_files_in_folder(service, folder_id, max_results=10)
        print(f"\n  {source_name}/ ({len(files)} files)")
        for f in files:
            size = f.get('size', '?')
            modified = f.get('modifiedTime', '')[:10]
            print(f"    {f['name']}  ({size} bytes, {modified})")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Google Drive ↔ Life OS bridge")
    parser.add_argument('--setup', action='store_true', help='Initial auth setup')
    parser.add_argument('--pull', action='store_true', help='Pull raw data from Drive')
    parser.add_argument('--push', action='store_true', help='Push processed data to Drive')
    parser.add_argument('--list', action='store_true', help='List Drive contents')
    parser.add_argument('--folder', '-f', help='Filter to specific source folder')
    args = parser.parse_args()

    service = get_service()
    print("Ensuring Drive folder structure...")
    folders = ensure_drive_structure(service)
    print("Drive structure ready.")

    if args.setup:
        print("\nSetup complete! Google Drive is connected.")
        list_drive_contents(service, folders)

    if args.list:
        list_drive_contents(service, folders)

    if args.pull:
        pull_from_drive(service, folders, source_filter=args.folder)

    if args.push:
        push_to_drive(service, folders)

    if not any([args.setup, args.pull, args.push, args.list]):
        pull_from_drive(service, folders)
        push_to_drive(service, folders)


if __name__ == '__main__':
    main()
