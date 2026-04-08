#!/usr/bin/env python3
"""
Master Sync Orchestrator - Pulls ALL data sources into the vault.

Data Flow:
    Step 1 (PULL):  External Services → vault/ (raw JSON/CSV)
    Step 2 (PUSH):  vault/ → Google Drive (backup + cloud access)
    Step 3 (PROCESS): vault/ → life/ (structured YAML for Claude)

Usage:
    python sync/sync_all.py                          # Pull all configured sources → vault
    python sync/sync_all.py --source garmin           # Pull only Garmin
    python sync/sync_all.py --source oura             # Pull only Oura
    python sync/sync_all.py --category health          # Pull all health sources
    python sync/sync_all.py --process                  # Also run processors after pull
    python sync/sync_all.py --drive                    # Sync vault ↔ Google Drive
    python sync/sync_all.py --status                   # Show what's configured

Kelvin's Stack:
    Health:   garmin, oura, apple-health
    Time:     toggl, google-calendar
    Finance:  banking (CSV)
    Notes:    apple-notes, onenote
    Life:     spotify, screen-time
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SYNC_DIR = BASE_DIR / "sync"
NOTES_DIR = BASE_DIR / "notes"
DATA_DIR = BASE_DIR / "data" / "raw"
DASHBOARDS_DIR = BASE_DIR / "dashboards"
UNIFIED_DIR = NOTES_DIR / "unified"


# ── Source Registry ──────────────────────────────────────────────────────────

SOURCES = {
    # Notes
    'apple-notes': {
        'script': 'apple/sync_apple_notes.py',
        'category': 'notes',
        'needs_input': True,
        'description': 'Apple Notes via Shortcuts/AppleScript/HTML',
    },
    'onenote': {
        'script': 'onenote/sync_onenote.py',
        'category': 'notes',
        'needs_input': False,
        'description': 'OneNote via Microsoft Graph API',
    },

    # Health
    'garmin': {
        'script': 'garmin/sync_garmin.py',
        'category': 'health',
        'needs_input': False,
        'description': 'Garmin Connect - sleep, steps, HR, stress, body battery, workouts',
    },
    'oura': {
        'script': 'oura/sync_oura.py',
        'category': 'health',
        'needs_input': False,
        'description': 'Oura Ring - sleep score, readiness, HRV, activity',
    },
    'apple-health': {
        'script': 'apple-health/sync_apple_health.py',
        'category': 'health',
        'needs_input': True,
        'description': 'Apple Health - steps, HR, workouts, sleep (Shortcuts export)',
    },

    # Finance
    'banking': {
        'script': 'banking/sync_banking.py',
        'category': 'finance',
        'needs_input': True,
        'description': 'Bank statements - transactions, spending (CSV)',
    },

    # Time & Work
    'toggl': {
        'script': 'toggl/sync_toggl.py',
        'category': 'work',
        'needs_input': False,
        'description': 'Toggl Track - time entries, projects, productivity',
    },
    'google-calendar': {
        'script': 'google-calendar/sync_calendar.py',
        'category': 'work',
        'needs_input': False,
        'description': 'Google Calendar - meetings, events',
    },
    'todoist': {
        'script': 'todoist/sync_todoist.py',
        'category': 'work',
        'needs_input': False,
        'description': 'Todoist - tasks, projects',
    },

    # Life
    'spotify': {
        'script': 'spotify/sync_spotify.py',
        'category': 'life',
        'needs_input': False,
        'description': 'Spotify - listening history for mood tracking',
    },
    'screen-time': {
        'script': 'screen-time/sync_screen_time.py',
        'category': 'life',
        'needs_input': True,
        'description': 'Screen Time - digital wellness',
    },
}


# ── Runner ───────────────────────────────────────────────────────────────────

def run_source(name: str, extra_args: list = None) -> bool:
    """Run a single sync source."""
    source = SOURCES.get(name)
    if not source:
        print(f"Unknown source: {name}")
        return False

    script = SYNC_DIR / source['script']
    if not script.exists():
        print(f"  Script not found: {script}")
        return False

    cmd = [sys.executable, str(script)] + (extra_args or [])

    print(f"\n{'=' * 60}")
    print(f"  {name.upper()} - {source['description']}")
    print(f"{'=' * 60}")

    try:
        result = subprocess.run(cmd, cwd=str(BASE_DIR), timeout=120)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {name} took too long")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def run_drive_sync():
    """Pull from Google Drive first."""
    script = SYNC_DIR / "google-drive" / "drive_bridge.py"
    if not script.exists():
        print("Google Drive bridge not found")
        return False

    print(f"\n{'=' * 60}")
    print("  GOOGLE DRIVE - Pulling raw data")
    print(f"{'=' * 60}")

    result = subprocess.run(
        [sys.executable, str(script), '--pull'],
        cwd=str(BASE_DIR), timeout=120
    )
    return result.returncode == 0


def check_configured(name: str) -> bool:
    """Check if a source has its credentials configured."""
    config_dir = BASE_DIR / ".config"
    config_checks = {
        'garmin': config_dir / "garmin_config.json",
        'oura': config_dir / "oura_config.json",
        'toggl': config_dir / "toggl_config.json",
        'onenote': config_dir / "onenote_config.json",
        'strava': config_dir / "strava_config.json",
        'todoist': config_dir / "todoist_config.json",
        'spotify': config_dir / "spotify_config.json",
        'google-calendar': config_dir / "google_token.json",
        'banking': None,  # Uses CSV input, always "ready"
        'apple-notes': None,
        'apple-health': None,
        'screen-time': None,
    }

    check = config_checks.get(name)
    if check is None:
        return True  # No config needed or input-based
    return check.exists()


# ── Analysis ─────────────────────────────────────────────────────────────────

def analyze_all():
    """Analyze all synced data and produce summary."""
    print(f"\n{'=' * 60}")
    print("  ANALYZING ALL DATA")
    print(f"{'=' * 60}")

    summary = {
        'generated_at': datetime.now().isoformat(),
        'sources': {},
    }

    # Count files per raw source
    if DATA_DIR.exists():
        for source_dir in DATA_DIR.iterdir():
            if source_dir.is_dir():
                files = list(source_dir.glob('*'))
                summary['sources'][source_dir.name] = {
                    'files': len(files),
                    'latest': max((f.stat().st_mtime for f in files), default=0),
                }

    # Count notes
    for notes_sub in ['apple-notes', 'onenote', 'unified']:
        notes_path = NOTES_DIR / notes_sub
        if notes_path.exists():
            count = len(list(notes_path.glob('*.md')))
            summary['sources'][f'notes-{notes_sub}'] = {'files': count}

    # Analyze notes content
    if UNIFIED_DIR.exists():
        all_notes = list(UNIFIED_DIR.glob("*.md"))
        finance_count = health_count = work_count = 0

        for note_path in all_notes:
            content = note_path.read_text(encoding='utf-8').lower()
            if any(w in content for w in ['budget', 'expense', 'payment', 'salary']):
                finance_count += 1
            if any(w in content for w in ['sleep', 'workout', 'health', 'gym']):
                health_count += 1
            if any(w in content for w in ['meeting', 'project', 'deadline', 'task']):
                work_count += 1

        summary['notes_analysis'] = {
            'total': len(all_notes),
            'finance_related': finance_count,
            'health_related': health_count,
            'work_related': work_count,
        }

    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DASHBOARDS_DIR / "latest_analysis.json"
    with open(report_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n  Data sources: {len(summary['sources'])}")
    for name, info in summary['sources'].items():
        print(f"    {name}: {info.get('files', 0)} files")
    print(f"\n  Report: {report_path}")

    return summary


def generate_dashboard(summary: dict = None):
    """Generate a comprehensive markdown dashboard."""
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    # Check what's configured
    status_lines = []
    for name, source in SOURCES.items():
        configured = check_configured(name)
        icon = "ready" if configured else "needs setup"
        status_lines.append(f"| {name} | {source['category']} | {icon} |")

    # Check for synced data files
    data_lines = []
    life_files = {
        'Garmin health': 'life/health/daily-data.yaml',
        'Garmin workouts': 'life/health/workouts-data.yaml',
        'Oura sleep': 'life/health/oura-data.yaml',
        'Apple Health': 'life/health/apple-health-data.yaml',
        'Toggl time': 'work/time-tracking.yaml',
        'Bank transactions': 'life/finance/transactions-*.yaml',
        'Calendar events': 'work/calendar-data.yaml',
        'Todoist tasks': 'work/todoist-data.yaml',
        'Spotify listening': 'life/mental-wellness/spotify-data.yaml',
        'Screen time': 'life/mental-wellness/screen-time-data.yaml',
    }

    for label, pattern in life_files.items():
        files = list(BASE_DIR.glob(pattern))
        if files:
            latest = max(f.stat().st_mtime for f in files)
            last_sync = datetime.fromtimestamp(latest).strftime('%Y-%m-%d %H:%M')
            data_lines.append(f"| {label} | synced | {last_sync} |")
        else:
            data_lines.append(f"| {label} | no data | - |")

    dashboard = f"""# Life OS Dashboard
> Last updated: {now.strftime('%Y-%m-%d %H:%M')}

## Data Sources Status
| Source | Category | Status |
|--------|----------|--------|
{chr(10).join(status_lines)}

## Synced Data
| Data | Status | Last Sync |
|------|--------|-----------|
{chr(10).join(data_lines)}

## Quick Commands
```bash
python sync/sync_all.py                    # Sync everything
python sync/sync_all.py --source oura      # Just Oura
python sync/sync_all.py --drive            # Pull from Google Drive first
python sync/sync_all.py --analyze --report # Full analysis
```

## For Claude
Ask me things like:
- "How did I sleep this week?" (reads Oura data)
- "How much did I spend on food?" (reads banking data)
- "What meetings do I have tomorrow?" (reads calendar)
- "Log my workout: bench press 70kg x 8, 45 min" (updates health log)
- "Weekly review" (aggregates everything)

---
*Generated by sync_all.py*
"""

    path = DASHBOARDS_DIR / "dashboard.md"
    path.write_text(dashboard)
    print(f"\n  Dashboard: {path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Life OS - Master Sync")
    parser.add_argument('--source', '-s', help='Sync specific source (or "all")')
    parser.add_argument('--category', '-c',
                        choices=['notes', 'health', 'finance', 'work', 'life'],
                        help='Sync all sources in a category')
    parser.add_argument('--drive', action='store_true',
                        help='Sync vault ↔ Google Drive')
    parser.add_argument('--process', action='store_true',
                        help='Run processors after sync (vault → life/ brain)')
    parser.add_argument('--analyze', action='store_true', help='Analyze all data')
    parser.add_argument('--report', action='store_true', help='Generate dashboard')
    parser.add_argument('--status', action='store_true', help='Show what is configured')
    parser.add_argument('--days', type=int, default=7, help='Days back for API syncs')
    args = parser.parse_args()

    # Ensure dirs
    for d in [NOTES_DIR / "unified", DATA_DIR, DASHBOARDS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Status check
    if args.status:
        print("\nSource Status:")
        print(f"{'Source':<20} {'Category':<10} {'Status':<15}")
        print("-" * 45)
        for name, source in SOURCES.items():
            configured = check_configured(name)
            status = "ready" if configured else "needs setup"
            print(f"{name:<20} {source['category']:<10} {status:<15}")
        return

    # Drive pull first
    if args.drive:
        run_drive_sync()

    # Determine what to sync
    results = {}

    if args.source:
        if args.source == 'all':
            sources_to_run = list(SOURCES.keys())
        else:
            sources_to_run = [args.source]
    elif args.category:
        sources_to_run = [
            name for name, s in SOURCES.items()
            if s['category'] == args.category
        ]
    else:
        # Default: sync everything that's configured and doesn't need input
        sources_to_run = [
            name for name, s in SOURCES.items()
            if not s['needs_input'] and check_configured(name)
        ]

    for name in sources_to_run:
        extra_args = []
        if name in ('garmin', 'oura', 'toggl', 'strava') and args.days:
            extra_args = ['--days', str(args.days)]
        results[name] = run_source(name, extra_args)

    # Summary
    if results:
        print(f"\n{'=' * 60}")
        print("  SYNC SUMMARY")
        print(f"{'=' * 60}")
        for name, success in results.items():
            icon = "OK" if success else "FAILED"
            print(f"  {name:<20} {icon}")

    # Run processors (vault → brain)
    if args.process:
        print(f"\n{'=' * 60}")
        print("  PROCESSING: vault → life/ brain")
        print(f"{'=' * 60}")
        processor = BASE_DIR / "processors" / "process_all.py"
        extra = ['--days', str(args.days)] if args.days else []
        subprocess.run([sys.executable, str(processor)] + extra, cwd=str(BASE_DIR))

    # Analyze and report
    summary = None
    if args.analyze:
        summary = analyze_all()

    if args.report or args.analyze:
        generate_dashboard(summary)

    failed = [n for n, s in results.items() if not s]
    if failed:
        print(f"\nFailed: {', '.join(failed)}")
        sys.exit(1)

    print("\nSync complete!")


if __name__ == '__main__':
    main()
