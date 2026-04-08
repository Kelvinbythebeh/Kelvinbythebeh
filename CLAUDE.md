# Kelvin's Centralized Life Management System

## What This Is
This repository is Kelvin's centralized life management hub. It pulls notes from Apple Notes
and OneNote into a unified markdown-based system that Claude can read, search, and act on
to help manage work, finances, health, and life.

## Repository Structure

```
├── notes/                  # All synced and unified notes
│   ├── apple-notes/        # Synced from Apple Notes
│   ├── onenote/            # Synced from OneNote
│   └── unified/            # Merged view of all notes (AI reads from here)
├── life/                   # Life management (all domains)
│   ├── overview.yaml       # Life dashboard & scores across all domains
│   ├── goals/              # Annual & quarterly goals
│   │   └── 2026.yaml       # This year's goals by domain
│   ├── finance/            # Budget, transactions, goals, net worth
│   │   ├── tracker.yaml    # Central finance config & overview
│   │   ├── transactions/   # Monthly transaction logs
│   │   ├── budgets/        # Budget plans
│   │   └── reports/        # Generated reports
│   ├── health/             # Health & wellness tracking
│   │   ├── tracker.yaml    # Health goals, metrics, plans
│   │   └── logs/           # Daily/monthly health logs
│   ├── fitness/            # Workout plans, PRs, streaks
│   │   ├── tracker.yaml
│   │   ├── workouts/       # Workout logs
│   │   └── progress/       # Progress photos/measurements
│   ├── mental-wellness/    # Meditation, journaling, mood, stress
│   │   └── tracker.yaml
│   ├── career/             # Role, skills, compensation, wins
│   │   ├── tracker.yaml
│   │   ├── resume/
│   │   └── skills/
│   ├── relationships/      # Inner circle, friends, network, important dates
│   │   └── tracker.yaml
│   ├── learning/           # Courses, books, certifications
│   │   ├── tracker.yaml
│   │   └── books/
│   ├── personal-growth/    # Habits, routines, experiments, reflections
│   │   ├── tracker.yaml
│   │   ├── habits/
│   │   └── journal/
│   ├── travel/             # Trips, bucket list, travel budget
│   │   └── tracker.yaml
│   ├── side-projects/      # Ideas, active builds, shipped projects
│   │   └── tracker.yaml
│   ├── home/               # Maintenance, bills, inventory, documents
│   │   └── tracker.yaml
│   └── legal/              # Insurance, tax, warranties, key documents
│       └── tracker.yaml
├── work/                   # Work management
│   ├── tracker.yaml        # Projects, tasks, OKRs, meetings
│   ├── tasks/              # Task details
│   ├── projects/           # Project files
│   └── meetings/           # Meeting notes
├── sync/                   # Sync scripts
│   ├── sync_all.py         # Unified sync orchestrator
│   ├── apple/              # Apple Notes sync
│   ├── onenote/            # OneNote sync (Graph API)
│   └── utils/              # Shared parsing utilities
├── dashboards/             # Generated summaries and reports
└── templates/              # Templates for new entries
```

## How Claude Should Help

### When Kelvin Shares Notes or Asks Questions:
1. **Read from `notes/unified/`** to find relevant context across all note sources
2. **Check trackers** (`life/finance/tracker.yaml`, `life/health/tracker.yaml`, `work/tracker.yaml`)
   to understand current state before giving advice
3. **Extract action items** from notes and offer to add them to the work tracker
4. **Identify financial data** in notes and offer to log transactions
5. **Spot health-related info** and offer to update health logs

### Finance Help:
- Parse expenses from notes and add to `life/finance/transactions/YYYY-MM.yaml`
- Track budget vs actual spending
- Flag subscription renewals and bills coming due
- Update net worth snapshots
- Provide spending summaries and trends

### Health Help:
- Log workouts, sleep, meals from notes
- Track streaks and goal progress
- Remind about supplements/medications
- Suggest improvements based on patterns
- Flag missed health checkups

### Work Help:
- Extract tasks from meeting notes
- Prioritize the task inbox
- Track project progress
- Surface upcoming deadlines
- Summarize weekly accomplishments

### Career Help:
- Track wins and achievements for performance reviews
- Monitor skill development progress
- Salary benchmarking awareness
- Networking follow-up reminders

### Relationships Help:
- Remind about birthdays and important dates
- Flag when someone hasn't been contacted in a while
- Track reconnection intentions

### Personal Growth Help:
- Track habit streaks
- Facilitate weekly reviews using `templates/weekly-review.yaml`
- Monitor life scores across domains from `life/overview.yaml`
- Suggest experiments based on goals

### Travel Help:
- Track upcoming trips, budget, and documents needed
- Flag passport/document expiries

### Home & Legal Help:
- Remind about bill due dates, insurance renewals, warranty expiries
- Track maintenance schedules

### Weekly Review Flow:
When Kelvin asks for a weekly review:
1. Read `life/overview.yaml` for current life scores
2. Check all tracker files for progress updates
3. Review notes from the past week
4. Help fill in `templates/weekly-review.yaml`
5. Update life scores and identify focus areas

### When Updating Files:
- Use YAML format for structured data (trackers, transactions, logs)
- Use Markdown for notes and reports
- Always preserve existing data - append, don't overwrite
- Add timestamps to new entries
- Keep frontmatter consistent with the schema shown in existing files

## Important Notes
- Currency default: MYR (Malaysian Ringgit) - adjust in finance tracker if needed
- All dates in ISO format: YYYY-MM-DD
- Notes from different sources may overlap - deduplicate when merging
- Sensitive financial data should NOT be committed to a public repo
- The `.config/` directory contains API tokens - it's in .gitignore
