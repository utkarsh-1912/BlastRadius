# Report Generator & Scheduled Reviews

`scripts/generate_report.py` runs a full Blast Radius review on every role matching a prefix (or all roles), writes an aggregate Markdown report, and persists every individual run to the same audit-history store the dashboard's `/reviews` page reads — so a scheduled report and the interactive app share one history, not two separate systems.

This is the README's "scheduled/recurring review mode" roadmap item, implemented deliberately as a script rather than an in-app scheduler: the project doesn't run a background process, so recurrence is the OS's job (cron / Windows Task Scheduler), which is simpler to audit than a scheduler embedded in the app.

**It never writes to AWS IAM.** Every review it runs stops at `orchestrator.run()` — the same read-only analysis the dashboard does before showing you the approve/reject screen. Nothing is ever auto-approved; a finding this script surfaces still needs a human to open `/reviews/{id}` and click Approve.

## Usage

```bash
python scripts/generate_report.py                              # every role in the account
python scripts/generate_report.py --role-prefix data-pipeline   # only roles starting with this
python scripts/generate_report.py --output reports/weekly.md    # explicit output path
python scripts/generate_report.py --lookback-days 60            # override the window (still capped at 90)
```

Default output: `reports/report-<timestamp>.md` (the `reports/` directory is gitignored — these are runtime artifacts, not source).

Each run also prints a live ✓/!/✗ summary per role as it goes, and confirms at the end how many runs were saved to the audit history.

## Scheduling it

### Linux / WSL / macOS — cron

```bash
crontab -e
```
Add a line (this example: every Monday at 9am):
```
0 9 * * 1 cd /path/to/BlastRadius && /usr/bin/python3 scripts/generate_report.py --output reports/weekly.md >> logs/report-cron.log 2>&1
```

### Windows — Task Scheduler

From PowerShell (creates a weekly Monday 9am task):
```powershell
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "scripts\generate_report.py --output reports\weekly.md" -WorkingDirectory "C:\path\to\BlastRadius"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -TaskName "BlastRadiusWeeklyReport" -Action $action -Trigger $trigger
```
Or via the GUI: Task Scheduler → Create Task → set the trigger to weekly, and the action to run `python.exe` with the script path as an argument and the repo root as "Start in."

### If TrueForge/WSL is in the picture

This script doesn't touch TrueForge at all — it's pure Python against `server/agent/orchestrator.py`, the same deterministic pipeline the sandbox replay uses. Schedule it from wherever your Python environment and AWS credentials live; it has no dependency on TrueForge being up.

## Reading the report

A Markdown file with:
- A summary table: role, status, safe-to-remove count, flagged count, which validator ran
- Per-role detail sections listing every safe and flagged action by name, with its severity and the specific reason (grounded in a real replay result, never invented — same rule as everywhere else in this project)
- A link back to each role's full detail page in the dashboard (`/reviews/{run_id}`) for the actual approve/reject decision

## Testing

`server/tests/test_generate_report.py` covers: the report file gets written with real findings, every run is persisted to the audit-history store (`agent/store.py`), it never writes to IAM regardless of what it finds, and a prefix matching no roles is a clean no-op rather than an error.
