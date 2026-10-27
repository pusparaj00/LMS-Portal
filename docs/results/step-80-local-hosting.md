# Step 80: hosting on the owner's PC (TR-O-01 to TR-O-07, G-8)

Date: 2026-10-27. Host: the development PC (Docker Desktop, 16 CPUs, 7.9 GB memory given to Docker). Free hosting was chosen
because paid servers are not possible; a tunnel from a domain the owner is buying carries the public traffic (step 81, not
built). Everything below ran in a throwaway Compose project `lmsprod` built with `docker-compose.yml` + `compose.prod.yml`
and `SITE_ADDRESS=localhost`; the live stack was not touched.

## What changed

| Change | Where |
| --- | --- |
| `CADDY_BIND` (default all interfaces) sets the address the proxy publishes on; `127.0.0.1` keeps it off the LAN | `compose.prod.yml`, `.env.example` (TR-O-02) |
| `scripts/windows-setup.ps1`: no sleep on mains power, daily `backup.sh` and optional `offsite-copy.sh` as scheduled tasks | TR-O-05, TR-O-06 |
| README section for hosting on a Windows PC | README |

## Measured

| Check | Command | Result |
| --- | --- | --- |
| Prod stack starts and is healthy | `docker compose -p lmsprod -f docker-compose.yml -f compose.prod.yml up -d --build --wait` | all services healthy |
| Only the proxy publishes ports | `docker ps --filter name=lmsprod` | caddy only; db, redis, api, mastery, worker, frontend, sandbox unpublished. With `CADDY_BIND=127.0.0.1`: `127.0.0.1:18081->80, 127.0.0.1:18443->443` |
| Headers | `curl -sk -D - https://localhost:18443/` | HSTS, CSP, nosniff, Permissions-Policy, Referrer-Policy present; `Server` removed |
| HTTP redirects to HTTPS | `curl http://localhost:18081/` | 308 |
| Forged client address ignored | `curl -H "X-Forwarded-For: 6.6.6.6" .../api/v1/health` | the API logged the real address (172.19.0.1, the Docker gateway), not 6.6.6.6 |
| Backup, off-disk copy, restore | `scripts/backup.sh`, `scripts/offsite-copy.sh`, `scripts/restore-check.sh` | row counts equal live: users 53, courses 1, problems 75, submissions 29, mastery_events 1948, consents 30; copy kept after checksum match |
| Memory under load | `docker stats` sampled about every 3 s during `python -m evaluation.load concurrent 30` | peak per container (MiB): api 490, db 283, worker 282, mastery 65, caddy 18, sandbox 18, frontend 14, redis 10; sum of peaks 1180 (the peaks were not all at the same moment, so this is an upper bound) |

## Found, not fixed

`evaluation.load concurrent 30` (30 students start the whole flow at the same moment): 7 of 30 flows failed with HTTP 503
"The sandbox is busy" (placement code answers and one wrong-code submit). The runner takes one job at a time and refuses a
job when 20 are already waiting for 3 seconds (`MAX_QUEUED_JOBS`, `QUEUE_WAIT_SECONDS` in `backend/app/sandbox.py`, TR-P-05).
This is the designed back-pressure, and step 30 recorded 0 failures with 10 at once; it is not a regression. A class that
submits code in the same second would see the same message and need to retry. Raising it means running jobs in parallel in
the sandbox, which touches TR-X limits and is not part of this step.

Windows paths with a colon (`C:\...`) given as `OFFSITE_TARGET` are read by `offsite-copy.sh` as `host:folder` and fail;
the README and the setup script use Git Bash paths (`/d/...`).

## Not done here

`scripts/windows-setup.ps1` was syntax-checked but not run: it changes the sleep settings and registers tasks on the
owner's PC. The tunnel (step 81) waits for the domain. The live stack still runs the development configuration on
localhost ports 8000 and 8080.
