#!/usr/bin/env python3
"""
Time Processor - Reads Toggl + Calendar from vault → writes to life/ & work/

Combines:
- Toggl Track: where your time actually went (deep work, meetings, admin)
- Google Calendar: what was scheduled

Usage:
    python processors/process_time.py
    python processors/process_time.py --days 30
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "vault"
WORK_DIR = BASE_DIR / "work"
LIFE_DIR = BASE_DIR / "life"


def load_vault_json(source: str) -> list:
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


# ── Toggl Processing ────────────────────────────────────────────────────────

def process_toggl(cutoff_days: int = None):
    """Process Toggl time entries from vault."""
    raw = load_vault_json('toggl')
    if not raw:
        print("  No Toggl data in vault/toggl/")
        return

    # Separate entries from summaries/projects
    entries = [r for r in raw if 'start' in r and 'duration' in r]
    summaries = [r for r in raw if 'total_hours' in r]
    projects_raw = [r for r in raw if 'id' in r and 'name' in r and 'wid' in r]

    project_map = {p['id']: p['name'] for p in projects_raw}

    cutoff = None
    if cutoff_days:
        cutoff = (datetime.now() - timedelta(days=cutoff_days)).strftime('%Y-%m-%d')

    # Process time entries
    by_date = defaultdict(lambda: {'total_hours': 0, 'entries': [], 'by_project': defaultdict(float)})

    for entry in entries:
        duration = entry.get('duration', 0)
        if duration < 0:
            continue  # Running timer

        start = entry.get('start', '')[:10]
        if not start:
            continue
        if cutoff and start < cutoff:
            continue

        hours = duration / 3600
        project = project_map.get(entry.get('project_id'), 'No Project')
        description = entry.get('description', '')
        tags = entry.get('tags', [])

        by_date[start]['total_hours'] += hours
        by_date[start]['by_project'][project] += hours
        by_date[start]['entries'].append({
            'description': description,
            'project': project,
            'hours': round(hours, 2),
            'tags': tags,
        })

    # Write to work/time-tracking.yaml
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    filepath = WORK_DIR / "time-tracking.yaml"

    lines = [
        "# Time Tracking (from Toggl Track)\n",
        f"# Processed: {datetime.now().isoformat()}\n",
        f"# Days tracked: {len(by_date)}\n\n",
    ]

    # Summary
    total_hours = sum(d['total_hours'] for d in by_date.values())
    all_projects = defaultdict(float)
    for d in by_date.values():
        for proj, hrs in d['by_project'].items():
            all_projects[proj] += hrs

    lines.append(f"total_hours: {round(total_hours, 1)}\n")
    lines.append(f"avg_per_day: {round(total_hours / max(len(by_date), 1), 1)}\n\n")

    lines.append("by_project:\n")
    for proj, hrs in sorted(all_projects.items(), key=lambda x: -x[1]):
        lines.append(f"  \"{proj}\": {round(hrs, 1)}\n")

    lines.append(f"\ndaily:\n")
    for date in sorted(by_date.keys(), reverse=True)[:30]:  # Last 30 days
        day = by_date[date]
        lines.append(f"  - date: \"{date}\"\n")
        lines.append(f"    hours: {round(day['total_hours'], 1)}\n")

        top_projects = sorted(day['by_project'].items(), key=lambda x: -x[1])[:3]
        if top_projects:
            lines.append(f"    top_projects:\n")
            for proj, hrs in top_projects:
                lines.append(f"      - \"{proj}\": {round(hrs, 1)}h\n")
        lines.append("\n")

    filepath.write_text(''.join(lines), encoding='utf-8')
    print(f"  Toggl: {filepath} ({len(by_date)} days, {round(total_hours, 1)}h total)")


# ── Calendar Processing ──────────────────────────────────────────────────────

def process_calendar():
    """Process Google Calendar events from vault."""
    raw = load_vault_json('google-calendar')
    if not raw:
        print("  No calendar data in vault/google-calendar/")
        return

    # Filter to actual events (have summary/start)
    events = [e for e in raw if e.get('summary') or e.get('start')]

    now = datetime.utcnow()
    upcoming = []
    past = []

    for event in events:
        start = event.get('start', {})
        start_dt = start.get('dateTime', start.get('date', ''))

        entry = {
            'title': event.get('summary', 'No title'),
            'date': start_dt[:10] if start_dt else '',
            'time': start_dt[11:16] if 'T' in str(start_dt) else 'all-day',
            'location': event.get('location', ''),
            'attendees': len(event.get('attendees', [])),
        }

        try:
            if start_dt and 'T' in start_dt:
                event_dt = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
                if event_dt.replace(tzinfo=None) > now:
                    upcoming.append(entry)
                else:
                    past.append(entry)
            else:
                upcoming.append(entry)
        except (ValueError, TypeError):
            upcoming.append(entry)

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    filepath = WORK_DIR / "calendar-data.yaml"

    lines = [
        "# Calendar (from Google Calendar)\n",
        f"# Processed: {datetime.now().isoformat()}\n\n",
        f"upcoming: # {len(upcoming)} events\n",
    ]

    for e in upcoming[:20]:
        lines.append(f"  - title: \"{e['title']}\"\n")
        lines.append(f"    date: \"{e['date']}\"\n")
        lines.append(f"    time: \"{e['time']}\"\n")
        if e['location']:
            loc = e['location'].replace('"', "'")
            lines.append(f"    location: \"{loc}\"\n")
        lines.append("\n")

    lines.append(f"\npast: # last {min(len(past), 20)}\n")
    for e in past[-20:]:
        lines.append(f"  - title: \"{e['title']}\"\n")
        lines.append(f"    date: \"{e['date']}\"\n")
        lines.append(f"    time: \"{e['time']}\"\n")
        lines.append("\n")

    filepath.write_text(''.join(lines), encoding='utf-8')
    print(f"  Calendar: {filepath} ({len(upcoming)} upcoming, {len(past)} past)")


def main():
    parser = argparse.ArgumentParser(description="Process time data from vault")
    parser.add_argument('--days', type=int, help='Only process last N days')
    args = parser.parse_args()

    print("Processing time data from vault...")
    process_toggl(cutoff_days=args.days)
    process_calendar()
    print("\nTime processing complete!")


if __name__ == '__main__':
    main()
