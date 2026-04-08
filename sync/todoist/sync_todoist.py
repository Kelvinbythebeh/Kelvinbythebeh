#!/usr/bin/env python3
"""
Todoist → Life OS Sync

Pulls tasks and projects from Todoist into the work/task tracker.

Setup:
    1. Get API token from https://todoist.com/app/settings/integrations/developer
    2. Save to .config/todoist_config.json: {"token": "YOUR_TOKEN"}

Usage:
    python sync_todoist.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install: pip install requests")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
RAW_DIR = BASE_DIR / "data" / "raw" / "todoist"
TODOIST_API = "https://api.todoist.com/rest/v2"


def get_token() -> str:
    config_file = CONFIG_DIR / "todoist_config.json"
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)['token']
    token = os.environ.get('TODOIST_TOKEN', '')
    if not token:
        print("ERROR: No Todoist token.")
        print("1. Go to https://todoist.com/app/settings/integrations/developer")
        print('2. Save to .config/todoist_config.json: {"token": "YOUR_TOKEN"}')
        sys.exit(1)
    return token


def fetch_all(token: str) -> dict:
    headers = {'Authorization': f'Bearer {token}'}

    tasks = requests.get(f"{TODOIST_API}/tasks", headers=headers).json()
    projects = requests.get(f"{TODOIST_API}/projects", headers=headers).json()

    project_map = {p['id']: p['name'] for p in projects}

    return {
        'tasks': tasks,
        'projects': projects,
        'project_map': project_map,
    }


def save_tasks(data: dict):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"tasks_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_path, 'w') as f:
        json.dump(data['tasks'], f, indent=2)

    log_path = BASE_DIR / "work" / "todoist-data.yaml"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Todoist Tasks - Auto-synced\n",
        f"# Last sync: {datetime.now().isoformat()}\n",
        f"# Tasks: {len(data['tasks'])}\n\n",
        "tasks:\n",
    ]

    priority_map = {4: 'urgent', 3: 'high', 2: 'medium', 1: 'low'}

    for task in sorted(data['tasks'], key=lambda x: x.get('priority', 1), reverse=True):
        project_name = data['project_map'].get(task.get('project_id', ''), 'Inbox')
        lines.append(f"  - task: \"{task['content']}\"\n")
        lines.append(f"    project: \"{project_name}\"\n")
        lines.append(f"    priority: {priority_map.get(task.get('priority', 1), 'low')}\n")
        if task.get('due'):
            lines.append(f"    due: \"{task['due'].get('date', '')}\"\n")
        if task.get('labels'):
            lines.append(f"    labels: {json.dumps(task['labels'])}\n")
        lines.append("\n")

    log_path.write_text(''.join(lines), encoding='utf-8')
    print(f"  Tasks: {len(data['tasks'])}")
    print(f"  Projects: {len(data['projects'])}")
    print(f"  Saved: {log_path}")


def main():
    token = get_token()
    print("Fetching Todoist data...")
    data = fetch_all(token)
    save_tasks(data)
    print("\nTodoist sync complete!")


if __name__ == '__main__':
    main()
