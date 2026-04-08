# Architecture - The Full Data Pipeline

## How Everything Connects

```
╔═══════════════════════════════════════════════════════════════╗
║                    DATA SOURCES (your life)                   ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  NOTES           HEALTH          FINANCE        WORK/LIFE     ║
║  ┌───────────┐   ┌───────────┐   ┌──────────┐  ┌──────────┐  ║
║  │Apple Notes│   │ Oura Ring │   │ Bank CSV │  │Google Cal│  ║
║  │  OneNote  │   │Apple Healh│   │   Wise   │  │ Todoist  │  ║
║  └─────┬─────┘   │  Strava   │   └────┬─────┘  │ Spotify  │  ║
║        │         └─────┬─────┘        │        │Screen Tm │  ║
║        │               │              │        └────┬─────┘  ║
║        │               │              │             │         ║
╠════════╪═══════════════╪══════════════╪═════════════╪═════════╣
║        │               │              │             │         ║
║        ▼               ▼              ▼             ▼         ║
║  ┌─────────────────────────────────────────────────────────┐  ║
║  │              GOOGLE DRIVE  (cloud storage)              │  ║
║  │                                                         │  ║
║  │  Life OS/                                               │  ║
║  │  ├── raw/              ← API dumps land here            │  ║
║  │  │   ├── oura/         ← sleep, readiness, activity     │  ║
║  │  │   ├── apple-health/ ← steps, HR, workouts            │  ║
║  │  │   ├── banking/      ← transaction CSVs               │  ║
║  │  │   ├── strava/       ← activities                     │  ║
║  │  │   ├── google-calendar/                               │  ║
║  │  │   ├── todoist/                                       │  ║
║  │  │   ├── spotify/                                       │  ║
║  │  │   └── screen-time/                                   │  ║
║  │  ├── notes/            ← exported notes                 │  ║
║  │  │   ├── apple-notes/                                   │  ║
║  │  │   └── onenote/                                       │  ║
║  │  └── processed/        ← AI summaries pushed back       │  ║
║  └──────────────────────────┬──────────────────────────────┘  ║
║                             │                                 ║
║                    drive_bridge.py                             ║
║                      (pull/push)                              ║
║                             │                                 ║
╠═════════════════════════════╪═════════════════════════════════╣
║                             ▼                                 ║
║  ┌─────────────────────────────────────────────────────────┐  ║
║  │            THIS REPO  (the AI brain)                    │  ║
║  │                                                         │  ║
║  │  data/raw/          ← local copy of Drive raw data      │  ║
║  │  notes/unified/     ← merged notes with frontmatter     │  ║
║  │                                                         │  ║
║  │  sync/              ← Python connectors per source      │  ║
║  │  ├── sync_all.py    ← master orchestrator               │  ║
║  │  ├── google-drive/  ← Drive bridge (pull/push)          │  ║
║  │  ├── oura/          ← Oura API → raw JSON → YAML       │  ║
║  │  ├── apple-health/  ← Health export → YAML              │  ║
║  │  ├── banking/       ← CSV parse → categorized YAML      │  ║
║  │  ├── strava/        ← Strava API → activities YAML      │  ║
║  │  ├── google-calendar/ ← Cal API → events YAML           │  ║
║  │  ├── todoist/       ← Todoist API → tasks YAML          │  ║
║  │  ├── spotify/       ← Spotify API → listening YAML      │  ║
║  │  ├── screen-time/   ← Export → YAML                     │  ║
║  │  ├── apple/         ← Apple Notes export                │  ║
║  │  ├── onenote/       ← OneNote Graph API                 │  ║
║  │  └── utils/         ← shared parsing                    │  ║
║  │                                                         │  ║
║  │  ┌──── TRANSFORMED DATA (Claude reads these) ───────┐  ║
║  │  │                                                   │  ║
║  │  │  life/me.yaml              ← your profile         │  ║
║  │  │  life/goals.yaml           ← what you're after    │  ║
║  │  │  life/tasks.yaml           ← task management      │  ║
║  │  │  life/inbox.md             ← raw dump             │  ║
║  │  │                                                   │  ║
║  │  │  life/health/                                     │  ║
║  │  │  ├── log.yaml              ← manual health log    │  ║
║  │  │  ├── oura-data.yaml        ← auto from Oura       │  ║
║  │  │  └── apple-health-data.yaml← auto from Apple      │  ║
║  │  │                                                   │  ║
║  │  │  life/fitness/                                    │  ║
║  │  │  └── strava-data.yaml      ← auto from Strava     │  ║
║  │  │                                                   │  ║
║  │  │  life/finance/                                    │  ║
║  │  │  ├── log.yaml              ← manual + budget       │  ║
║  │  │  └── bank-*-data.yaml      ← auto from bank CSV   │  ║
║  │  │                                                   │  ║
║  │  │  work/                                            │  ║
║  │  │  ├── calendar-data.yaml    ← auto from Google Cal  │  ║
║  │  │  └── todoist-data.yaml     ← auto from Todoist     │  ║
║  │  │                                                   │  ║
║  │  │  life/mental-wellness/                            │  ║
║  │  │  ├── spotify-data.yaml     ← auto from Spotify     │  ║
║  │  │  └── screen-time-data.yaml ← auto from export      │  ║
║  │  │                                                   │  ║
║  │  └───────────────────────────────────────────────────┘  ║
║  │                                                         │  ║
║  │              ┌──────────────┐                           │  ║
║  │              │  CLAUDE AI   │                           │  ║
║  │              │  Reads all   │                           │  ║
║  │              │  YAML + MD   │                           │  ║
║  │              │  Gives you   │                           │  ║
║  │              │  insights    │                           │  ║
║  │              └──────────────┘                           │  ║
║  └─────────────────────────────────────────────────────────┘  ║
╚═══════════════════════════════════════════════════════════════╝
```

## Source-by-Source Setup

### Health Sources

| Source | API? | How Data Flows | Setup |
|--------|------|----------------|-------|
| **Oura Ring** | Yes (v2) | Oura API → `sync_oura.py` → `life/health/oura-data.yaml` | Get token from cloud.ouraring.com |
| **Apple Health** | No | iPhone Shortcuts/XML export → `sync_apple_health.py` → `life/health/apple-health-data.yaml` | Build iOS Shortcut or manual export |
| **Strava** | Yes (OAuth2) | Strava API → `sync_strava.py` → `life/fitness/strava-data.yaml` | Create app at strava.com/settings/api |

### Finance Sources

| Source | API? | How Data Flows | Setup |
|--------|------|----------------|-------|
| **Bank (Maybank/CIMB/etc)** | No | Download CSV → `sync_banking.py` → `life/finance/bank-*-data.yaml` | Download statement from bank app |
| **Wise** | Yes | Wise API → `sync_banking.py --bank wise` → `life/finance/bank-wise-data.yaml` | Get API token from wise.com |
| **Manual (Google Sheets)** | Export | Export CSV → `sync_banking.py --bank sheets` | Track in a Google Sheet, export monthly |

### Work Sources

| Source | API? | How Data Flows | Setup |
|--------|------|----------------|-------|
| **Google Calendar** | Yes (OAuth2) | Calendar API → `sync_calendar.py` → `work/calendar-data.yaml` | Uses same Google creds as Drive |
| **Todoist** | Yes | Todoist API → `sync_todoist.py` → `work/todoist-data.yaml` | Get token from todoist.com settings |

### Notes Sources

| Source | API? | How Data Flows | Setup |
|--------|------|----------------|-------|
| **Apple Notes** | No | Shortcuts export → `sync_apple_notes.py` → `notes/apple-notes/` | Build iOS Shortcut |
| **OneNote** | Yes (Graph) | Microsoft Graph API → `sync_onenote.py` → `notes/onenote/` | Register Azure app |

### Lifestyle Sources

| Source | API? | How Data Flows | Setup |
|--------|------|----------------|-------|
| **Spotify** | Yes (OAuth2) | Spotify API → `sync_spotify.py` → `life/mental-wellness/spotify-data.yaml` | Create app at developer.spotify.com |
| **Screen Time** | No | Shortcuts/manual → `sync_screen_time.py` → `life/mental-wellness/screen-time-data.yaml` | Build iOS Shortcut or screenshot to Claude |

## Commands Cheat Sheet

```bash
# ── Full sync ──────────────────────────
python sync/sync_all.py                    # Sync all configured sources
python sync/sync_all.py --drive            # Pull from Google Drive first
python sync/sync_all.py --analyze --report # Sync + analyze + dashboard

# ── By category ────────────────────────
python sync/sync_all.py --category health  # Oura + Apple Health + Strava
python sync/sync_all.py --category finance # Banking
python sync/sync_all.py --category work    # Calendar + Todoist

# ── Individual sources ─────────────────
python sync/oura/sync_oura.py --days 30
python sync/strava/sync_strava.py --days 90
python sync/banking/sync_banking.py --input statement.csv --bank maybank
python sync/google-calendar/sync_calendar.py --days-ahead 30
python sync/todoist/sync_todoist.py
python sync/spotify/sync_spotify.py

# ── Google Drive ───────────────────────
python sync/google-drive/drive_bridge.py --setup  # First time
python sync/google-drive/drive_bridge.py --pull   # Pull raw data
python sync/google-drive/drive_bridge.py --push   # Push summaries back
python sync/google-drive/drive_bridge.py --list   # See what's there

# ── Check status ───────────────────────
python sync/sync_all.py --status           # What's configured?
```

## Adding a New Data Source

1. Create `sync/new-source/sync_new_source.py`
2. It should:
   - Fetch data from API or parse export file
   - Save raw JSON to `data/raw/new-source/`
   - Save transformed YAML to the right `life/` folder
3. Add entry to `SOURCES` dict in `sync/sync_all.py`
4. Add folder to `drive_bridge.py` SOURCE_MAP
5. Done - Claude can now read it
