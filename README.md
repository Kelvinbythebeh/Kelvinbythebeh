# Kelvin's Life OS

A centralized AI-powered system that pulls Apple Notes and OneNote into one place,
then helps manage work, finances, health, and life.

## Architecture

```
┌─────────────┐     ┌─────────────┐
│ Apple Notes  │     │   OneNote   │
│  (iPhone/    │     │ (Microsoft  │
│   Mac/iPad)  │     │  365/Web)   │
└──────┬───────┘     └──────┬──────┘
       │                     │
       │  Shortcuts/         │  Graph API /
       │  AppleScript        │  HTML Export
       │                     │
       ▼                     ▼
┌─────────────────────────────────────┐
│        Sync Layer (Python)          │
│  sync_apple_notes.py │ sync_onenote│
│         sync_all.py (orchestrator)  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     Unified Notes (Markdown)        │
│  notes/unified/ - all notes merged  │
│  with frontmatter for AI parsing    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│       Claude AI Assistant           │
│  Reads CLAUDE.md for instructions   │
│  Searches notes for context         │
│  Updates trackers automatically     │
└──────────────┬──────────────────────┘
               │
       ┌───────┼───────┐
       ▼       ▼       ▼
   ┌───────┐ ┌─────┐ ┌──────┐
   │Finance│ │Health│ │ Work │
   │Tracker│ │Track │ │Mgmt  │
   └───────┘ └─────┘ └──────┘
```

## What It Tracks

### Finance
- Monthly budgets and spending by category
- Transactions extracted from notes
- Subscriptions and recurring bills
- Savings goals and net worth
- Investment tracking

### Health
- Sleep, exercise, nutrition logging
- Mood and energy tracking
- Supplement/medication reminders
- Fitness plans and streaks
- Health checkup scheduling

### Work
- Projects and milestones
- Task inbox (captured from notes) → prioritized lists
- Meeting notes and action items
- OKRs and quarterly goals
- Learning and development

## Quick Start

### 1. Install Dependencies

```bash
pip install requests beautifulsoup4
```

### 2. Sync Apple Notes

**Option A: Apple Shortcuts (Recommended for iPhone/iPad)**
1. Create a Shortcut that exports all notes as JSON
2. Save/AirDrop the file to your computer
3. Run: `python sync/apple/sync_apple_notes.py --method shortcut --input path/to/export.json`

**Option B: AppleScript (Mac only)**
```bash
python sync/apple/sync_apple_notes.py --method applescript
```

**Option C: HTML Export**
```bash
python sync/apple/sync_apple_notes.py --method html --input path/to/html_folder/
```

### 3. Sync OneNote

**Option A: Microsoft Graph API (Recommended)**
1. Register an app at [Azure Portal](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps)
2. Add permissions: `Notes.Read`, `Notes.Read.All`
3. Set redirect URI: `http://localhost:8400/callback`
4. Create `.config/onenote_config.json`:
   ```json
   {
     "client_id": "YOUR_CLIENT_ID",
     "tenant_id": "common"
   }
   ```
5. Run: `python sync/onenote/sync_onenote.py`

**Option B: HTML Export (Offline)**
1. In OneNote desktop: File → Export → HTML
2. Run: `python sync/onenote/sync_onenote.py --method export --input path/to/export/`

### 4. Sync Everything

```bash
python sync/sync_all.py --analyze --report
```

### 5. Use with Claude

Open Claude Code in this directory and ask things like:
- "What tasks did I capture in my notes this week?"
- "Log these expenses from my grocery note"
- "How much did I spend on food this month?"
- "Update my health log - slept 7 hours, did 45 min gym"
- "What are my upcoming deadlines?"
- "Summarize my meeting notes from this week"

## How AI Access Works

The `CLAUDE.md` file at the root instructs Claude on how to navigate and use this system.
When you open Claude Code in this directory, it automatically reads `CLAUDE.md` and understands:

- Where to find your notes (`notes/unified/`)
- How to update trackers (YAML files in `life/` and `work/`)
- How to extract and categorize information from your notes
- How to help with financial, health, and work management

All data is in plain text (Markdown + YAML) so Claude can read, search, and modify it directly.

## Privacy & Security

- `.config/` contains API tokens and is gitignored
- `.env` files are gitignored
- **Do not commit sensitive financial data to a public repo**
- Consider making this repo private if it contains personal information

## File Formats

| Type | Format | Why |
|------|--------|-----|
| Notes | Markdown with YAML frontmatter | Human readable, AI parseable, version controlled |
| Trackers | YAML | Structured but readable, easy for AI to update |
| Transactions | YAML | Structured financial data with categories |
| Reports | Markdown / JSON | Dashboards for quick overview |
