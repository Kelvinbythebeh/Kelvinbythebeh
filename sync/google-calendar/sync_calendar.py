#!/usr/bin/env python3
"""
Google Calendar → Life OS Sync

Pulls upcoming events and past meetings into the work tracker.
Uses the same Google OAuth credentials as the Drive bridge.

Usage:
    python sync_calendar.py                    # Next 7 days + last 7 days
    python sync_calendar.py --days-ahead 30    # Next 30 days
    python sync_calendar.py --days-back 14     # Past 14 days
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    print("Install: pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
TOKEN_FILE = CONFIG_DIR / "google_token.json"
RAW_DIR = BASE_DIR / "data" / "raw" / "google-calendar"

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_calendar_service():
    """Reuse Google OAuth token from Drive bridge."""
    if not TOKEN_FILE.exists():
        print("ERROR: No Google token found. Run drive_bridge.py --setup first.")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build('calendar', 'v3', credentials=creds)


def fetch_events(service, days_back: int = 7, days_ahead: int = 7) -> list:
    """Fetch calendar events for a date range."""
    now = datetime.utcnow()
    time_min = (now - timedelta(days=days_back)).isoformat() + 'Z'
    time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'

    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min,
        timeMax=time_max,
        maxResults=200,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    return events_result.get('items', [])


def transform_events(events: list) -> dict:
    """Transform calendar events into work tracker format."""
    upcoming = []
    past = []
    now = datetime.utcnow()

    for event in events:
        start = event.get('start', {})
        end = event.get('end', {})
        start_dt = start.get('dateTime', start.get('date', ''))
        end_dt = end.get('dateTime', end.get('date', ''))

        entry = {
            'title': event.get('summary', 'No title'),
            'date': start_dt[:10] if start_dt else '',
            'time': start_dt[11:16] if 'T' in start_dt else 'all-day',
            'end_time': end_dt[11:16] if 'T' in end_dt else '',
            'location': event.get('location', ''),
            'attendees': [a.get('email', '') for a in event.get('attendees', [])[:5]],
            'status': event.get('status', ''),
            'link': event.get('hangoutLink', event.get('htmlLink', '')),
        }

        # Determine if past or upcoming
        try:
            event_dt = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
            if event_dt.replace(tzinfo=None) < now:
                past.append(entry)
            else:
                upcoming.append(entry)
        except (ValueError, TypeError):
            upcoming.append(entry)

    return {'upcoming': upcoming, 'past': past}


def save_calendar_data(data: dict):
    """Save calendar data for Claude to read."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Raw JSON
    raw_path = RAW_DIR / f"events_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_path, 'w') as f:
        json.dump(data, f, indent=2)

    # YAML for Claude
    work_dir = BASE_DIR / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    log_path = work_dir / "calendar-data.yaml"

    lines = [
        "# Google Calendar - Auto-synced\n",
        f"# Last sync: {datetime.now().isoformat()}\n\n",
    ]

    lines.append(f"# Upcoming ({len(data['upcoming'])} events)\n")
    lines.append("upcoming:\n")
    for event in data['upcoming']:
        lines.append(f"  - title: \"{event['title']}\"\n")
        lines.append(f"    date: \"{event['date']}\"\n")
        lines.append(f"    time: \"{event['time']}\"\n")
        if event['location']:
            lines.append(f"    location: \"{event['location']}\"\n")
        if event['attendees']:
            lines.append(f"    attendees: {json.dumps(event['attendees'][:3])}\n")
        lines.append("\n")

    lines.append(f"\n# Past ({len(data['past'])} events)\n")
    lines.append("past:\n")
    for event in data['past'][-20:]:  # Last 20 only
        lines.append(f"  - title: \"{event['title']}\"\n")
        lines.append(f"    date: \"{event['date']}\"\n")
        lines.append(f"    time: \"{event['time']}\"\n")
        lines.append("\n")

    log_path.write_text(''.join(lines), encoding='utf-8')

    print(f"  Upcoming: {len(data['upcoming'])} events")
    print(f"  Past: {len(data['past'])} events")
    print(f"  Saved: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Sync Google Calendar → Life OS")
    parser.add_argument('--days-ahead', type=int, default=7)
    parser.add_argument('--days-back', type=int, default=7)
    args = parser.parse_args()

    service = get_calendar_service()
    print("Fetching calendar events...")
    events = fetch_events(service, args.days_back, args.days_ahead)
    print(f"  Found {len(events)} events")

    data = transform_events(events)
    save_calendar_data(data)
    print("\nCalendar sync complete!")


if __name__ == '__main__':
    main()
