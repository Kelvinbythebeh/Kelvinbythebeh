# Kelvin's Life OS

## What This Is
Kelvin's AI-powered life hub. He captures notes naturally (Apple Notes, OneNote, or just
telling Claude). Claude reads everything here and helps manage finances, health, work, and life.

## How It Works
See `FLOW.md` for the full workflow. The short version:
1. Kelvin dumps raw notes/thoughts into `life/inbox.md` or just tells Claude
2. Claude sorts everything into the right log files
3. Claude gives summaries, reminders, and insights on demand

## Simplified Structure

```
├── life/                       # Everything about Kelvin's life
│   ├── me.yaml                 # Profile, values, life scores, key people
│   ├── inbox.md                # Raw dump - Claude processes this
│   ├── goals.yaml              # Active goals + someday list
│   ├── tasks.yaml              # Inbox → active → done task flow
│   ├── finance/
│   │   ├── log.yaml            # Budget + monthly transactions (Claude fills)
│   │   └── tracker.yaml        # Detailed: net worth, debts, subscriptions
│   ├── health/
│   │   ├── log.yaml            # Daily: sleep, workout, mood (Claude fills)
│   │   └── tracker.yaml        # Detailed: supplements, fitness plan, goals
│   ├── weekly-reviews/         # Claude generates these every Sunday
│   ├── [domain trackers]       # Detailed trackers for career, relationships,
│   │                           # learning, travel, etc. (expand when needed)
├── notes/                      # Synced notes from external sources
│   ├── apple-notes/            # Raw sync from Apple Notes
│   ├── onenote/                # Raw sync from OneNote
│   └── unified/                # Merged + tagged view
├── sync/                       # Python sync scripts
│   ├── sync_all.py             # Run this to pull from all sources
│   ├── apple/                  # Apple Notes export methods
│   └── onenote/                # OneNote Graph API sync
└── templates/                  # Templates for manual entry
```

## Core Files (Claude reads these first)

| File | Purpose | Who updates it |
|------|---------|----------------|
| `life/me.yaml` | Context about Kelvin | Kelvin sets up, Claude updates scores |
| `life/inbox.md` | Raw notes dump | Kelvin dumps, Claude processes |
| `life/goals.yaml` | What Kelvin is working toward | Both |
| `life/tasks.yaml` | Task management | Claude manages from notes |
| `life/finance/log.yaml` | Money in/out | Claude logs from notes |
| `life/health/log.yaml` | Daily health data | Claude logs from notes |

## How Claude Should Help

### When Kelvin shares notes or pastes text:
1. Read `life/me.yaml` for context
2. Extract expenses → add to `life/finance/log.yaml`
3. Extract health data → add to `life/health/log.yaml`
4. Extract tasks → add to `life/tasks.yaml`
5. Flag deadlines, birthdays, renewals

### Common requests:
- **"What's my day?"** → Read tasks, deadlines, bills due
- **"Log this: [expenses/health/tasks]"** → Parse and add to right file
- **"Weekly review"** → Generate review from all logs, save to `life/weekly-reviews/`
- **"How much did I spend on X?"** → Query finance log
- **"How's my health trending?"** → Analyze health log patterns

### Rules:
- YAML for structured data, Markdown for notes
- Always APPEND, never overwrite existing entries
- Dates in ISO format: YYYY-MM-DD
- Currency: MYR (Malaysian Ringgit) unless specified
- Don't commit secrets or sensitive data to public repos
- `.config/` is gitignored (API tokens live there)
