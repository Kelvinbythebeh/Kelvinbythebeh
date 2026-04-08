#!/usr/bin/env python3
"""
Note Parser Utilities
Common functions for parsing, categorizing, and extracting data from notes.
Used by sync scripts and the AI assistant context.
"""

import json
import re
from datetime import datetime
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file. Returns (metadata, body)."""
    if not content.startswith('---'):
        return {}, content

    end = content.find('---', 3)
    if end < 0:
        return {}, content

    fm_text = content[3:end]
    metadata = {}
    for line in fm_text.strip().split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            val = val.strip().strip('"')
            # Try to parse JSON values (lists, etc.)
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass
            metadata[key.strip()] = val

    body = content[end + 3:].strip()
    return metadata, body


def extract_action_items(text: str) -> list[dict]:
    """Extract TODO items, checkboxes, and action items from text."""
    items = []

    # Markdown checkboxes
    for match in re.finditer(r'^(\s*)-\s*\[([ xX])\]\s*(.*)', text, re.MULTILINE):
        items.append({
            'text': match.group(3).strip(),
            'done': match.group(2).lower() == 'x',
            'type': 'checkbox',
        })

    # TODO/FIXME/ACTION keywords
    for match in re.finditer(
        r'(?:TODO|FIXME|ACTION|FOLLOW.?UP)[:\s]+(.*?)(?:\n|$)',
        text, re.IGNORECASE
    ):
        items.append({
            'text': match.group(1).strip(),
            'done': False,
            'type': 'keyword',
        })

    return items


def extract_dates(text: str) -> list[dict]:
    """Extract date references from text for calendar/deadline tracking."""
    dates = []

    # ISO format: 2026-04-08
    for match in re.finditer(r'\b(\d{4}-\d{2}-\d{2})\b', text):
        try:
            dt = datetime.strptime(match.group(1), '%Y-%m-%d')
            dates.append({'date': match.group(1), 'parsed': dt})
        except ValueError:
            pass

    # Common formats: April 8, 2026 / 8 April 2026
    for match in re.finditer(
        r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})\b',
        text, re.IGNORECASE
    ):
        try:
            date_str = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            dt = datetime.strptime(date_str, '%d %b %Y')
            dates.append({'date': dt.strftime('%Y-%m-%d'), 'parsed': dt})
        except ValueError:
            pass

    return dates


def extract_monetary_amounts(text: str) -> list[dict]:
    """Extract money amounts from text for finance tracking."""
    amounts = []

    # Match various currency formats
    for match in re.finditer(
        r'(RM|MYR|USD|\$|£|€|SGD|GBP)\s*([\d,]+\.?\d*)',
        text, re.IGNORECASE
    ):
        currency = match.group(1).upper()
        amount = float(match.group(2).replace(',', ''))
        amounts.append({'currency': currency, 'amount': amount, 'raw': match.group(0)})

    return amounts


def extract_contacts(text: str) -> list[str]:
    """Extract @mentions and email addresses."""
    mentions = re.findall(r'@(\w+)', text)
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    return list(set(mentions + emails))


def build_note_index(notes_dir: Path) -> list[dict]:
    """Build a searchable index of all notes in a directory."""
    index = []

    for md_file in notes_dir.glob('**/*.md'):
        content = md_file.read_text(encoding='utf-8')
        metadata, body = parse_frontmatter(content)

        entry = {
            'file': str(md_file),
            'filename': md_file.name,
            'title': metadata.get('title', md_file.stem),
            'source': metadata.get('source', 'unknown'),
            'category': metadata.get('category', 'general'),
            'tags': metadata.get('tags', []),
            'synced_at': metadata.get('synced_at', ''),
            'action_items': extract_action_items(body),
            'has_amounts': bool(extract_monetary_amounts(body)),
            'word_count': len(body.split()),
        }
        index.append(entry)

    return index
