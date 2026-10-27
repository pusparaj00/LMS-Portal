# Step 84: release housekeeping (TR-O-05, TR-O-06)

Date: 2026-10-27.

| Action | Result |
| --- | --- |
| Backup before touching the live stack | `scripts/backup.sh` wrote `backup/scheduled/lms-2026-10-27-115934.dump` (5.3 MB) |
| `main` fast-forwarded from step 77 (f95d3ce) to step 83 (2b1a6e4), then pushed | `origin/main` equals local `main` (2b1a6e4) |
| Live stack rebuilt (`docker compose up -d --build --wait`) | all services healthy; `alembic_version` 0034; `next_problem` has the new ordering |
| Restore check of the pre-rebuild dump against the rebuilt database | `scripts/restore-check.sh`: users 37 = 37, courses 10 = 10, problems 150 = 150, submissions 101 = 101, mastery_events 861 = 861, consents 11 = 11 |
| Live endpoints | API `/api/v1/health` 200, web 200 |

Nothing in the repository changed in this step except this file. The live stack still runs the development configuration on
localhost ports 8000 and 8080 (the production configuration is for step 81, with the tunnel).
