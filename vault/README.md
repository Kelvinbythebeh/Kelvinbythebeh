# Vault (Google Drive Mirror)

This folder mirrors the Google Drive vault structure.
Raw data from ALL sources lands here first, untouched.
Processors then read from here and write to `life/`.

## Structure (same on Google Drive)

```
vault/
├── garmin/              ← sleep, steps, HR, stress, workouts, body comp
├── oura/                ← sleep score, readiness, HRV, activity
├── apple-health/        ← steps, HR, workouts, SpO2 (Shortcuts export)
├── toggl/               ← time entries, projects, summaries
├── google-calendar/     ← events, meetings
├── banking/             ← transaction CSVs from bank apps
├── apple-notes/         ← notes JSON from Shortcuts
├── onenote/             ← notes from Graph API or HTML export
└── screen-time/         ← app usage from Shortcuts export
```

## Rules
- All files are raw JSON or CSV - never edit them
- Filenames include date range: `sleep_2026-04-01_to_2026-04-08.json`
- Processors read from here, transform, and write to `life/`
- Google Drive bridge syncs this folder ↔ Drive
