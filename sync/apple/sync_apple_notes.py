#!/usr/bin/env python3
"""
Apple Notes → Centralized Markdown Sync

Two methods supported:
1. macOS: Uses AppleScript to export notes directly (requires Mac)
2. Cross-platform: Reads from exported .zip/.html files from iCloud.com
   or from Apple Shortcuts JSON export

Usage:
    python sync_apple_notes.py --method applescript   # On Mac
    python sync_apple_notes.py --method shortcut --input ~/Downloads/apple_notes_export.json
    python sync_apple_notes.py --method html --input ~/Downloads/apple_notes_export/
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Where synced notes land
NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "notes" / "apple-notes"
UNIFIED_DIR = Path(__file__).resolve().parent.parent.parent / "notes" / "unified"


def sanitize_filename(name: str) -> str:
    """Convert a note title to a safe filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    return name.lower()[:80]


def extract_tags(content: str) -> list[str]:
    """Extract #tags from note content for categorization."""
    return re.findall(r'#(\w+)', content)


def categorize_note(title: str, content: str, tags: list[str]) -> str:
    """Auto-categorize notes into life domains based on content analysis."""
    text = (title + " " + content).lower()

    finance_keywords = ['budget', 'expense', 'income', 'salary', 'investment',
                        'savings', 'bank', 'payment', 'receipt', 'tax', 'money',
                        'cost', 'price', 'bill', 'subscription', 'rent', 'loan']
    health_keywords = ['health', 'workout', 'exercise', 'gym', 'diet', 'meal',
                       'sleep', 'weight', 'doctor', 'medicine', 'symptom',
                       'calories', 'steps', 'run', 'meditation', 'mental']
    work_keywords = ['meeting', 'project', 'deadline', 'client', 'task',
                     'sprint', 'review', 'standup', 'roadmap', 'OKR', 'KPI']

    if any(kw in text for kw in finance_keywords) or 'finance' in tags:
        return 'finance'
    if any(kw in text for kw in health_keywords) or 'health' in tags:
        return 'health'
    if any(kw in text for kw in work_keywords) or 'work' in tags:
        return 'work'
    return 'general'


def write_note_markdown(title: str, content: str, folder: str = "",
                        source: str = "apple-notes",
                        created: str = None, modified: str = None) -> Path:
    """Write a note as a structured markdown file with frontmatter."""
    tags = extract_tags(content)
    category = categorize_note(title, content, tags)
    filename = sanitize_filename(title) + ".md"
    now = datetime.now().isoformat()

    frontmatter = f"""---
title: "{title}"
source: {source}
folder: "{folder}"
category: {category}
tags: {json.dumps(tags)}
synced_at: "{now}"
created: "{created or now}"
modified: "{modified or now}"
---

"""
    filepath = NOTES_DIR / filename
    filepath.write_text(frontmatter + content, encoding='utf-8')

    # Also write to unified directory with source prefix
    unified_path = UNIFIED_DIR / f"apple-{filename}"
    unified_path.write_text(frontmatter + content, encoding='utf-8')

    return filepath


# ── Method 1: AppleScript (macOS only) ──────────────────────────────────────

APPLESCRIPT = '''
tell application "Notes"
    set output to "["
    set noteCount to count of notes
    repeat with i from 1 to noteCount
        set n to note i
        set noteTitle to name of n
        set noteBody to plaintext of n
        set noteFolder to name of container of n
        set noteCreated to creation date of n as string
        set noteModified to modification date of n as string

        -- Escape quotes in content
        set noteBody to my replaceText(noteBody, "\\"", "\\\\\\"")
        set noteTitle to my replaceText(noteTitle, "\\"", "\\\\\\"")
        set noteBody to my replaceText(noteBody, return, "\\\\n")

        set output to output & "{\\"title\\": \\"" & noteTitle & "\\", "
        set output to output & "\\"body\\": \\"" & noteBody & "\\", "
        set output to output & "\\"folder\\": \\"" & noteFolder & "\\", "
        set output to output & "\\"created\\": \\"" & noteCreated & "\\", "
        set output to output & "\\"modified\\": \\"" & noteModified & "\\"}"

        if i < noteCount then
            set output to output & ","
        end if
    end repeat
    set output to output & "]"
    return output
end tell

on replaceText(theText, searchString, replacementString)
    set AppleScript's text item delimiters to searchString
    set theItems to text items of theText
    set AppleScript's text item delimiters to replacementString
    set theText to theItems as text
    set AppleScript's text item delimiters to ""
    return theText
end replaceText
'''


def sync_via_applescript():
    """Export all Apple Notes via AppleScript (macOS only)."""
    if sys.platform != 'darwin':
        print("ERROR: AppleScript method only works on macOS.")
        print("Use --method shortcut or --method html instead.")
        sys.exit(1)

    print("Exporting Apple Notes via AppleScript...")
    result = subprocess.run(
        ['osascript', '-e', APPLESCRIPT],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        print(f"AppleScript error: {result.stderr}")
        sys.exit(1)

    notes = json.loads(result.stdout)
    print(f"Found {len(notes)} notes. Syncing...")

    for note in notes:
        path = write_note_markdown(
            title=note['title'],
            content=note['body'],
            folder=note.get('folder', ''),
            created=note.get('created'),
            modified=note.get('modified')
        )
        print(f"  ✓ {note['title']} → {path.name}")

    print(f"\nSynced {len(notes)} notes to {NOTES_DIR}")


# ── Method 2: Apple Shortcuts JSON Export ────────────────────────────────────

def sync_via_shortcut(input_path: str):
    """
    Import notes from Apple Shortcuts JSON export.

    Create a Shortcut that:
    1. Find All Notes
    2. For each note → build a dictionary with title, body, folder, dates
    3. Export as JSON to Files app or share via AirDrop
    """
    path = Path(input_path)
    if not path.exists():
        print(f"ERROR: File not found: {input_path}")
        print("\nTo create the export, build an Apple Shortcut:")
        print("  1. 'Find All Notes' action")
        print("  2. 'Repeat with Each' → build JSON dict per note")
        print("  3. 'Save File' as JSON")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        notes = json.load(f)

    if isinstance(notes, dict):
        notes = notes.get('notes', [notes])

    print(f"Found {len(notes)} notes in export. Syncing...")

    for note in notes:
        title = note.get('title', note.get('name', 'Untitled'))
        body = note.get('body', note.get('content', note.get('text', '')))
        folder = note.get('folder', '')
        created = note.get('created', note.get('creationDate', ''))
        modified = note.get('modified', note.get('modificationDate', ''))

        path = write_note_markdown(
            title=title, content=body, folder=folder,
            created=created, modified=modified
        )
        print(f"  ✓ {title} → {path.name}")

    print(f"\nSynced {len(notes)} notes to {NOTES_DIR}")


# ── Method 3: HTML export from iCloud.com ────────────────────────────────────

def sync_via_html(input_path: str):
    """Import notes from HTML files exported from iCloud.com or other tools."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Install beautifulsoup4: pip install beautifulsoup4")
        sys.exit(1)

    input_dir = Path(input_path)
    if not input_dir.exists():
        print(f"ERROR: Directory not found: {input_path}")
        sys.exit(1)

    html_files = list(input_dir.glob('**/*.html')) + list(input_dir.glob('**/*.htm'))
    print(f"Found {len(html_files)} HTML files. Converting...")

    for html_file in html_files:
        with open(html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        title = soup.title.string if soup.title else html_file.stem
        body = soup.get_text(separator='\n').strip()
        folder = html_file.parent.name if html_file.parent != input_dir else ''

        path = write_note_markdown(
            title=title, content=body, folder=folder,
            source="apple-notes-html"
        )
        print(f"  ✓ {title} → {path.name}")

    print(f"\nSynced {len(html_files)} notes to {NOTES_DIR}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync Apple Notes to centralized markdown")
    parser.add_argument('--method', choices=['applescript', 'shortcut', 'html'],
                        default='shortcut', help='Export method to use')
    parser.add_argument('--input', '-i', help='Path to exported file/directory')
    args = parser.parse_args()

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)

    if args.method == 'applescript':
        sync_via_applescript()
    elif args.method == 'shortcut':
        if not args.input:
            print("ERROR: --input required for shortcut method")
            print("Export your notes using the Apple Shortcut first.")
            sys.exit(1)
        sync_via_shortcut(args.input)
    elif args.method == 'html':
        if not args.input:
            print("ERROR: --input required for html method")
            sys.exit(1)
        sync_via_html(args.input)


if __name__ == '__main__':
    main()
