#!/usr/bin/env python3
"""
Unified Sync Orchestrator
Pulls from all note sources into the centralized system.

Usage:
    python sync_all.py                          # Sync everything
    python sync_all.py --source apple           # Sync only Apple Notes
    python sync_all.py --source onenote         # Sync only OneNote
    python sync_all.py --analyze                # Run AI categorization on synced notes
    python sync_all.py --report                 # Generate summary dashboard
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "notes"
UNIFIED_DIR = NOTES_DIR / "unified"
DASHBOARDS_DIR = BASE_DIR / "dashboards"


def run_apple_sync(args: list[str] = None):
    """Run Apple Notes sync."""
    script = BASE_DIR / "sync" / "apple" / "sync_apple_notes.py"
    cmd = [sys.executable, str(script)] + (args or [])
    print("=" * 60)
    print("SYNCING APPLE NOTES")
    print("=" * 60)
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    return result.returncode == 0


def run_onenote_sync(args: list[str] = None):
    """Run OneNote sync."""
    script = BASE_DIR / "sync" / "onenote" / "sync_onenote.py"
    cmd = [sys.executable, str(script)] + (args or [])
    print("=" * 60)
    print("SYNCING ONENOTE")
    print("=" * 60)
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    return result.returncode == 0


def analyze_notes():
    """Analyze all synced notes and extract actionable items."""
    print("\n" + "=" * 60)
    print("ANALYZING NOTES")
    print("=" * 60)

    all_notes = list(UNIFIED_DIR.glob("*.md"))
    print(f"Found {len(all_notes)} unified notes")

    finance_items = []
    health_items = []
    work_tasks = []
    general_items = []

    for note_path in all_notes:
        content = note_path.read_text(encoding='utf-8')

        # Parse frontmatter
        frontmatter = {}
        if content.startswith('---'):
            end = content.find('---', 3)
            if end > 0:
                fm_text = content[3:end]
                for line in fm_text.strip().split('\n'):
                    if ':' in line:
                        key, val = line.split(':', 1)
                        frontmatter[key.strip()] = val.strip().strip('"')
                body = content[end + 3:].strip()
            else:
                body = content
        else:
            body = content

        category = frontmatter.get('category', 'general')
        title = frontmatter.get('title', note_path.stem)
        source = frontmatter.get('source', 'unknown')

        item = {
            'title': title,
            'source': source,
            'category': category,
            'file': note_path.name,
        }

        # Extract action items (lines starting with - [ ], TODO, FIXME, ACTION)
        actions = re.findall(
            r'(?:^|\n)\s*(?:- \[ \]|TODO|FIXME|ACTION)[:\s]*(.*)',
            body, re.IGNORECASE
        )
        if actions:
            item['actions'] = actions

        # Extract monetary amounts
        amounts = re.findall(r'(?:RM|MYR|\$|USD|£|€)\s*[\d,]+\.?\d*', body)
        if amounts:
            item['amounts'] = amounts

        if category == 'finance':
            finance_items.append(item)
        elif category == 'health':
            health_items.append(item)
        elif category == 'work':
            work_tasks.append(item)
        else:
            general_items.append(item)

    # Generate analysis report
    report = {
        'generated_at': datetime.now().isoformat(),
        'total_notes': len(all_notes),
        'by_category': {
            'finance': len(finance_items),
            'health': len(health_items),
            'work': len(work_tasks),
            'general': len(general_items),
        },
        'finance_items': finance_items,
        'health_items': health_items,
        'work_tasks': work_tasks,
        'action_items_found': sum(
            len(item.get('actions', []))
            for item in finance_items + health_items + work_tasks + general_items
        ),
    }

    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DASHBOARDS_DIR / "latest_analysis.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\nAnalysis complete:")
    print(f"  Finance notes: {len(finance_items)}")
    print(f"  Health notes:  {len(health_items)}")
    print(f"  Work notes:    {len(work_tasks)}")
    print(f"  General notes: {len(general_items)}")
    print(f"  Action items:  {report['action_items_found']}")
    print(f"\nFull report: {report_path}")

    return report


def generate_dashboard():
    """Generate a markdown dashboard summarizing everything."""
    print("\n" + "=" * 60)
    print("GENERATING DASHBOARD")
    print("=" * 60)

    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    # Count notes by source
    apple_count = len(list((NOTES_DIR / "apple-notes").glob("*.md")))
    onenote_count = len(list((NOTES_DIR / "onenote").glob("*.md")))
    unified_count = len(list(UNIFIED_DIR.glob("*.md")))

    # Load finance data if available
    finance_tracker = BASE_DIR / "life" / "finance" / "tracker.yaml"
    health_tracker = BASE_DIR / "life" / "health" / "tracker.yaml"
    work_tracker = BASE_DIR / "work" / "tracker.yaml"

    dashboard = f"""# Life Dashboard
> Last updated: {now.strftime('%Y-%m-%d %H:%M')}

## Notes Overview
| Source | Count |
|--------|-------|
| Apple Notes | {apple_count} |
| OneNote | {onenote_count} |
| **Unified Total** | **{unified_count}** |

## Quick Links
- [Finance Tracker](../life/finance/tracker.yaml)
- [Health Tracker](../life/health/tracker.yaml)
- [Work Tracker](../work/tracker.yaml)
- [Latest Analysis](./latest_analysis.json)

## Status
- Last sync: {now.strftime('%Y-%m-%d %H:%M')}
- Finance tracker: {'configured' if finance_tracker.exists() else 'needs setup'}
- Health tracker: {'configured' if health_tracker.exists() else 'needs setup'}
- Work tracker: {'configured' if work_tracker.exists() else 'needs setup'}

---
*Generated by sync_all.py*
"""

    dashboard_path = DASHBOARDS_DIR / "dashboard.md"
    dashboard_path.write_text(dashboard)
    print(f"Dashboard written to {dashboard_path}")


def main():
    parser = argparse.ArgumentParser(description="Unified notes sync orchestrator")
    parser.add_argument('--source', choices=['apple', 'onenote', 'all'],
                        default='all', help='Which source to sync')
    parser.add_argument('--analyze', action='store_true',
                        help='Analyze synced notes for actionable items')
    parser.add_argument('--report', action='store_true',
                        help='Generate summary dashboard')
    parser.add_argument('--apple-method', default='shortcut',
                        help='Apple sync method (applescript/shortcut/html)')
    parser.add_argument('--apple-input', help='Input file for Apple Notes export')
    parser.add_argument('--onenote-method', default='api',
                        help='OneNote sync method (api/export)')
    parser.add_argument('--onenote-input', help='Input path for OneNote export')
    parser.add_argument('--onenote-notebook', help='Filter to specific OneNote notebook')
    args = parser.parse_args()

    # Ensure directories exist
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)

    success = True

    if args.source in ('apple', 'all'):
        apple_args = ['--method', args.apple_method]
        if args.apple_input:
            apple_args += ['--input', args.apple_input]
        if args.apple_method != 'applescript' and not args.apple_input:
            print("Skipping Apple Notes (no input file provided)")
            print("  Use: --apple-input <path> with --apple-method shortcut/html")
        else:
            success = run_apple_sync(apple_args) and success

    if args.source in ('onenote', 'all'):
        onenote_args = ['--method', args.onenote_method]
        if args.onenote_input:
            onenote_args += ['--input', args.onenote_input]
        if args.onenote_notebook:
            onenote_args += ['--notebook', args.onenote_notebook]
        if args.onenote_method == 'export' and not args.onenote_input:
            print("Skipping OneNote (no input path provided)")
            print("  Use: --onenote-input <path> with --onenote-method export")
        else:
            success = run_onenote_sync(onenote_args) and success

    if args.analyze:
        analyze_notes()

    if args.report or args.analyze:
        generate_dashboard()

    if not success:
        print("\nSome syncs failed. Check output above.")
        sys.exit(1)

    print("\nSync complete!")


if __name__ == '__main__':
    main()
