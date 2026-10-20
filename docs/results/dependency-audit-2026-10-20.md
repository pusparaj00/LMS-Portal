# Dependency audit, 2026-10-20

| Check | Command | Result |
|---|---|---|
| Python | `pip-audit -r requirements.txt` (pip-audit installed into a temporary directory in the test container, not added to the repo) | No known vulnerabilities found |
| Frontend | `npm audit` in `frontend/` | found 0 vulnerabilities |
| Test suite | `docker compose --profile test run --rm test pytest -q` | 971 passed, 2 warnings, 486 s |

Commit audited: 5a85a57. Audit databases are as of the run date; results change as new advisories are published.
