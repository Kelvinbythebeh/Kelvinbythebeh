#!/usr/bin/env python3
"""
Notes Processor - Reads Apple Notes + OneNote from vault → notes/unified/

Converts raw note exports into tagged markdown with frontmatter
that Claude can search and analyze.

Usage:
    python processors/process_notes.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "vault"
OUTPUT_DIR = BASE_DIR / "notes" / "unified"

sys.path.insert(0, str(BASE_DIR / "sync" / "utils"))
try:
    from note_parser import extract_action_items, extract_monetary_amounts, extract_dates
except ImportError:
    def extract_action_items(t): return []
    def extract_monetary_amounts(t): return []
    def extract_dates(t): return []


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    return name.lower()[:80]


def categorize(title: str, content: str) -> str:
    text = (title + " " + content).lower()
    categories = {
        'finance': ['budget', 'expense', 'income', 'salary', 'investment', 'bank', 'payment', 'tax', 'money', 'bill'],
        'health': ['health', 'workout', 'exercise', 'gym', 'diet', 'sleep', 'weight', 'doctor', 'medicine'],
        'work': ['meeting', 'project', 'deadline', 'client', 'task', 'sprint', 'review'],
    }
    for cat, keywords in categories.items():
        if any(kw in text for kw in keywords):
            return cat
    return 'general'


def process_apple_notes():
    """Process Apple Notes JSON exports from vault."""
    vault_dir = VAULT_DIR / "apple-notes"
    if not vault_dir.exists():
        return 0

    count = 0
    for f in vault_dir.glob('*.json'):
        with open(f) as fh:
            try:
                notes = json.load(fh)
            except json.JSONDecodeError:
                continue

        if isinstance(notes, dict):
            notes = notes.get('notes', [notes])

        for note in notes:
            title = note.get('title', note.get('name', 'Untitled'))
            body = note.get('body', note.get('content', note.get('text', '')))
            folder = note.get('folder', '')
            created = note.get('created', note.get('creationDate', ''))
            modified = note.get('modified', note.get('modificationDate', ''))

            category = categorize(title, body)
            tags = re.findall(r'#(\w+)', body)
            filename = f"apple-{sanitize_filename(title)}.md"

            frontmatter = f"""---
title: "{title}"
source: apple-notes
folder: "{folder}"
category: {category}
tags: {json.dumps(tags)}
created: "{created}"
modified: "{modified}"
processed: "{datetime.now().isoformat()}"
---

"""
            (OUTPUT_DIR / filename).write_text(frontmatter + body, encoding='utf-8')
            count += 1

    return count


def process_onenote():
    """Process OneNote exports from vault."""
    vault_dir = VAULT_DIR / "onenote"
    if not vault_dir.exists():
        return 0

    count = 0

    # JSON exports
    for f in vault_dir.glob('*.json'):
        with open(f) as fh:
            try:
                pages = json.load(fh)
            except json.JSONDecodeError:
                continue

        if isinstance(pages, dict):
            pages = pages.get('pages', pages.get('value', [pages]))

        for page in pages:
            title = page.get('title', page.get('displayName', 'Untitled'))
            body = page.get('body', page.get('content', ''))
            notebook = page.get('notebook', '')
            section = page.get('section', '')

            category = categorize(title, body)
            tags = re.findall(r'#(\w+)', body)
            filename = f"onenote-{sanitize_filename(title)}.md"

            frontmatter = f"""---
title: "{title}"
source: onenote
notebook: "{notebook}"
section: "{section}"
category: {category}
tags: {json.dumps(tags)}
processed: "{datetime.now().isoformat()}"
---

"""
            (OUTPUT_DIR / filename).write_text(frontmatter + body, encoding='utf-8')
            count += 1

    # HTML exports
    try:
        from bs4 import BeautifulSoup
        for html_file in vault_dir.glob('**/*.html'):
            with open(html_file, 'r', encoding='utf-8', errors='replace') as fh:
                soup = BeautifulSoup(fh.read(), 'html.parser')
            title = soup.title.string if soup.title else html_file.stem
            body = soup.get_text(separator='\n').strip()
            category = categorize(title, body)
            filename = f"onenote-{sanitize_filename(title)}.md"

            frontmatter = f"""---
title: "{title}"
source: onenote-html
category: {category}
processed: "{datetime.now().isoformat()}"
---

"""
            (OUTPUT_DIR / filename).write_text(frontmatter + body, encoding='utf-8')
            count += 1
    except ImportError:
        pass

    return count


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Processing notes from vault...")
    apple_count = process_apple_notes()
    onenote_count = process_onenote()

    total = apple_count + onenote_count
    print(f"  Apple Notes: {apple_count}")
    print(f"  OneNote: {onenote_count}")
    print(f"  Total: {total} notes → {OUTPUT_DIR}")
    print("\nNotes processing complete!")


if __name__ == '__main__':
    main()
