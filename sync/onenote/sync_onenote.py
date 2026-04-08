#!/usr/bin/env python3
"""
OneNote → Centralized Markdown Sync via Microsoft Graph API

Setup:
1. Register an app at https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps
2. Add permissions: Notes.Read, Notes.Read.All
3. Set redirect URI: http://localhost:8400/callback
4. Copy your Client ID and Tenant ID into .env or config

Usage:
    # First time - will open browser for auth:
    python sync_onenote.py --setup

    # Regular sync:
    python sync_onenote.py

    # Sync specific notebook:
    python sync_onenote.py --notebook "Work Notes"

    # Import from OneNote HTML export (offline):
    python sync_onenote.py --method export --input ~/Downloads/onenote_export/
"""

import argparse
import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NOTES_DIR = BASE_DIR / "notes" / "onenote"
UNIFIED_DIR = BASE_DIR / "notes" / "unified"
CONFIG_DIR = BASE_DIR / ".config"
TOKEN_FILE = CONFIG_DIR / "onenote_token.json"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTH_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
REDIRECT_URI = "http://localhost:8400/callback"
SCOPES = "Notes.Read Notes.Read.All offline_access"


def load_config() -> dict:
    """Load Microsoft Graph API config from .env or config file."""
    config_file = CONFIG_DIR / "onenote_config.json"
    env_file = BASE_DIR / ".env"

    # Try config file first
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)

    # Try .env file
    config = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"').strip("'")

    return {
        'client_id': config.get('ONENOTE_CLIENT_ID', os.environ.get('ONENOTE_CLIENT_ID', '')),
        'tenant_id': config.get('ONENOTE_TENANT_ID', os.environ.get('ONENOTE_TENANT_ID', 'common')),
        'client_secret': config.get('ONENOTE_CLIENT_SECRET', os.environ.get('ONENOTE_CLIENT_SECRET', '')),
    }


def sanitize_filename(name: str) -> str:
    """Convert a note title to a safe filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    return name.lower()[:80]


def extract_tags(content: str) -> list[str]:
    """Extract #tags from note content."""
    return re.findall(r'#(\w+)', content)


def categorize_note(title: str, content: str, tags: list[str]) -> str:
    """Auto-categorize notes into life domains."""
    text = (title + " " + content).lower()

    categories = {
        'finance': ['budget', 'expense', 'income', 'salary', 'investment',
                     'bank', 'payment', 'tax', 'money', 'bill', 'subscription'],
        'health': ['health', 'workout', 'exercise', 'gym', 'diet', 'sleep',
                    'weight', 'doctor', 'medicine', 'calories', 'meditation'],
        'work': ['meeting', 'project', 'deadline', 'client', 'task',
                 'sprint', 'review', 'standup', 'roadmap'],
    }

    for category, keywords in categories.items():
        if any(kw in text for kw in keywords) or category in tags:
            return category
    return 'general'


def html_to_markdown(html: str) -> str:
    """Basic HTML to Markdown conversion for OneNote content."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Convert common elements
        for tag in soup.find_all('b'):
            tag.replace_with(f"**{tag.get_text()}**")
        for tag in soup.find_all('strong'):
            tag.replace_with(f"**{tag.get_text()}**")
        for tag in soup.find_all('i'):
            tag.replace_with(f"*{tag.get_text()}*")
        for tag in soup.find_all('em'):
            tag.replace_with(f"*{tag.get_text()}*")
        for tag in soup.find_all('h1'):
            tag.replace_with(f"\n# {tag.get_text()}\n")
        for tag in soup.find_all('h2'):
            tag.replace_with(f"\n## {tag.get_text()}\n")
        for tag in soup.find_all('h3'):
            tag.replace_with(f"\n### {tag.get_text()}\n")
        for tag in soup.find_all('li'):
            tag.replace_with(f"\n- {tag.get_text()}")
        for tag in soup.find_all('br'):
            tag.replace_with('\n')

        return soup.get_text(separator='\n').strip()
    except ImportError:
        # Fallback: strip HTML tags with regex
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()


def write_note_markdown(title: str, content: str, notebook: str = "",
                        section: str = "", created: str = None,
                        modified: str = None) -> Path:
    """Write a OneNote page as a structured markdown file."""
    tags = extract_tags(content)
    category = categorize_note(title, content, tags)
    filename = sanitize_filename(title) + ".md"
    now = datetime.now().isoformat()

    frontmatter = f"""---
title: "{title}"
source: onenote
notebook: "{notebook}"
section: "{section}"
category: {category}
tags: {json.dumps(tags)}
synced_at: "{now}"
created: "{created or now}"
modified: "{modified or now}"
---

"""
    filepath = NOTES_DIR / filename
    filepath.write_text(frontmatter + content, encoding='utf-8')

    # Also write to unified directory
    unified_path = UNIFIED_DIR / f"onenote-{filename}"
    unified_path.write_text(frontmatter + content, encoding='utf-8')

    return filepath


# ── OAuth2 Authentication ────────────────────────────────────────────────────

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth2 redirect callback."""
    auth_code = None

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if 'code' in query:
            OAuthCallbackHandler.auth_code = query['code'][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this window.</p>")
        else:
            self.send_response(400)
            self.end_headers()
            error = query.get('error_description', ['Unknown error'])[0]
            self.wfile.write(f"<h1>Error</h1><p>{error}</p>".encode())

    def log_message(self, format, *args):
        pass  # Suppress server logs


def authenticate(config: dict) -> str:
    """Get a valid access token, refreshing if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Try existing token
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)

        if time.time() < token_data.get('expires_at', 0):
            return token_data['access_token']

        # Try refresh
        if 'refresh_token' in token_data:
            print("Refreshing access token...")
            resp = requests.post(
                TOKEN_URL.format(tenant=config['tenant_id']),
                data={
                    'client_id': config['client_id'],
                    'grant_type': 'refresh_token',
                    'refresh_token': token_data['refresh_token'],
                    'scope': SCOPES,
                }
            )
            if resp.status_code == 200:
                new_token = resp.json()
                new_token['expires_at'] = time.time() + new_token.get('expires_in', 3600)
                with open(TOKEN_FILE, 'w') as f:
                    json.dump(new_token, f)
                return new_token['access_token']

    # Need fresh auth
    if not config.get('client_id'):
        print("ERROR: No Microsoft app credentials configured.")
        print("\nSetup steps:")
        print("1. Go to https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps")
        print("2. Register a new app")
        print("3. Add redirect URI: http://localhost:8400/callback")
        print("4. Add API permissions: Notes.Read, Notes.Read.All")
        print("5. Create .config/onenote_config.json with:")
        print('   {"client_id": "YOUR_ID", "tenant_id": "common"}')
        sys.exit(1)

    auth_params = {
        'client_id': config['client_id'],
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'response_mode': 'query',
    }

    auth_url = AUTH_URL.format(tenant=config['tenant_id']) + '?' + urlencode(auth_params)
    print(f"Opening browser for authorization...")
    webbrowser.open(auth_url)

    # Start local server to receive callback
    server = HTTPServer(('localhost', 8400), OAuthCallbackHandler)
    server.handle_request()

    if not OAuthCallbackHandler.auth_code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    # Exchange code for token
    resp = requests.post(
        TOKEN_URL.format(tenant=config['tenant_id']),
        data={
            'client_id': config['client_id'],
            'grant_type': 'authorization_code',
            'code': OAuthCallbackHandler.auth_code,
            'redirect_uri': REDIRECT_URI,
            'scope': SCOPES,
        }
    )
    resp.raise_for_status()
    token_data = resp.json()
    token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)

    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f)

    return token_data['access_token']


# ── Microsoft Graph API Sync ────────────────────────────────────────────────

def sync_via_graph_api(notebook_filter: str = None):
    """Sync all OneNote pages via Microsoft Graph API."""
    config = load_config()
    token = authenticate(config)
    headers = {'Authorization': f'Bearer {token}'}

    # Get all notebooks
    print("Fetching notebooks...")
    resp = requests.get(f"{GRAPH_BASE}/me/onenote/notebooks", headers=headers)
    resp.raise_for_status()
    notebooks = resp.json().get('value', [])

    total_synced = 0

    for nb in notebooks:
        nb_name = nb['displayName']
        if notebook_filter and notebook_filter.lower() not in nb_name.lower():
            continue

        print(f"\nNotebook: {nb_name}")

        # Get sections in this notebook
        resp = requests.get(
            f"{GRAPH_BASE}/me/onenote/notebooks/{nb['id']}/sections",
            headers=headers
        )
        resp.raise_for_status()
        sections = resp.json().get('value', [])

        for section in sections:
            sec_name = section['displayName']
            print(f"  Section: {sec_name}")

            # Get pages in this section
            resp = requests.get(
                f"{GRAPH_BASE}/me/onenote/sections/{section['id']}/pages",
                headers=headers
            )
            resp.raise_for_status()
            pages = resp.json().get('value', [])

            for page in pages:
                page_title = page.get('title', 'Untitled')

                # Get page content
                content_resp = requests.get(
                    f"{GRAPH_BASE}/me/onenote/pages/{page['id']}/content",
                    headers=headers
                )
                content_resp.raise_for_status()
                content_md = html_to_markdown(content_resp.text)

                path = write_note_markdown(
                    title=page_title,
                    content=content_md,
                    notebook=nb_name,
                    section=sec_name,
                    created=page.get('createdDateTime'),
                    modified=page.get('lastModifiedDateTime')
                )
                print(f"    ✓ {page_title} → {path.name}")
                total_synced += 1

    print(f"\nSynced {total_synced} pages to {NOTES_DIR}")


# ── Offline HTML Export Import ───────────────────────────────────────────────

def sync_via_export(input_path: str):
    """Import from OneNote HTML export (File → Export in OneNote desktop)."""
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
        with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
            content = html_to_markdown(f.read())

        # Derive notebook/section from directory structure
        rel_path = html_file.relative_to(input_dir)
        parts = rel_path.parts
        notebook = parts[0] if len(parts) > 1 else ""
        section = parts[1] if len(parts) > 2 else ""
        title = html_file.stem

        path = write_note_markdown(
            title=title, content=content,
            notebook=notebook, section=section
        )
        print(f"  ✓ {title} → {path.name}")

    print(f"\nSynced {len(html_files)} pages to {NOTES_DIR}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync OneNote to centralized markdown")
    parser.add_argument('--method', choices=['api', 'export'], default='api',
                        help='Sync method: api (Graph API) or export (HTML files)')
    parser.add_argument('--notebook', '-n', help='Filter to specific notebook name')
    parser.add_argument('--input', '-i', help='Path to exported HTML directory')
    parser.add_argument('--setup', action='store_true', help='Run initial auth setup')
    args = parser.parse_args()

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)

    if args.method == 'export':
        if not args.input:
            print("ERROR: --input required for export method")
            print("Export from OneNote desktop: File → Export → HTML")
            sys.exit(1)
        sync_via_export(args.input)
    else:
        sync_via_graph_api(notebook_filter=args.notebook)


if __name__ == '__main__':
    main()
