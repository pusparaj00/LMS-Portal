# Step 58: production hardening (TR-O-01 to TR-O-07)

Measured on 2026-10-20 on the development PC, on a throwaway stack: `SITE_ADDRESS=127.0.0.1 docker compose -p lmsprod -f docker-compose.yml -f compose.prod.yml up -d --build --wait`. The stack was removed afterwards (`down -v`) and the live stack restarted. This was a local rehearsal. Nothing was run on a real server, so the real host, its firewall and a browser on another machine are untested.

| ID | Check (command) | Result |
| --- | --- | --- |
| TR-O-01 | `curl -sk https://127.0.0.1/api/v1/health` and `/` | 200 and 200 |
| TR-O-01 | `curl -s http://127.0.0.1/` | 308 redirect to `https://127.0.0.1/` |
| TR-O-01 | `openssl s_client` on 127.0.0.1:443 | Issuer "Caddy Local Authority - ECC Intermediate", subject alternative name is IP 127.0.0.1. Self-signed by Caddy's own authority; a browser warns until its root is installed. |
| TR-O-02 | `docker ps` for the stack, then a TCP connect from the host to each port (live stack stopped for the check) | Only Caddy publishes ports (80, 443). 8000, 8080, 8001, 5432 and 6379 refused; 80 and 443 open. |
| TR-O-03 | Two wrong logins through Caddy, one with a forged `X-Forwarded-For: 1.2.3.4`; then the login limiter's keys in Redis | One key only: `rl:login_ip:172.19.0.1`, the host address as Docker presents it. Caddy's own container address (172.19.0.8) was not used and 1.2.3.4 was ignored. |
| TR-O-04 | `docker compose run --rm --no-deps -e JWT_SECRET=short api python -c "from app.config import get_settings; get_settings()"` | `RuntimeError: APP_ENV=production refuses weak secrets: JWT_SECRET (at least 32 characters, not a placeholder)`; the value is not printed. The API started in production mode with the real `.env`. |
| TR-O-04 | `tests/test_prod_config.py` | 9 tests pass (strong secrets, development mode, 7 weak cases, message never contains the value) |
| TR-O-05 | `docker inspect` of the API container | `restart=unless-stopped`; log driver json-file, `max-size 10m`, `max-file 3`; memory limits set |
| TR-O-06 | `scripts/backup.sh` on the seeded throwaway stack, then `scripts/restore-check.sh` | Dump restored into a scratch database, row counts equal: users 22/22, courses 1/1, problems 61/61, submissions 0/0, mastery_events 980/980, consents 0/0. Scratch database dropped afterwards. |
| TR-O-06 | A 20-day-old `lms-*.dump` and a 20-day-old `keep-me.txt` in the backup folder, then `backup.sh` | The old dump was deleted, the other file kept, the new dump written |
| TR-O-07 | `curl -skI https://127.0.0.1/` | X-Content-Type-Options nosniff, X-Frame-Options DENY, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy camera/microphone/geolocation off; no Server header |
| TR-O-07 | Container health | All services including Caddy reported healthy under `up --wait` |

Full suite after the changes: `docker compose --profile test run --rm test` (ruff and pytest): 980 passed, 2 warnings, 437 s (971 before, plus 9 new).

## Defects found while rehearsing

- A pydantic validator would have printed the rejected secret in its error text. The test caught it; the check is now a plain method that names only the setting.
- A browser sends no server name when it connects to an IP address, and the first Caddyfile gave a failed TLS handshake (curl returned 000). `default_sni` fixed it.
- On Windows, `COMPOSE_FILE` needs `COMPOSE_PATH_SEPARATOR=:` for the scripts' environment form; Linux needs nothing.

## Not measured or not done

- Memory limits are caps, not measurements of peak use. Idle use on the rehearsal stack: API 108 MiB of 1 GiB, worker 273 MiB of 512 MiB, database 69 MiB of 1 GiB. Peak use under a real class, including the first chat answer that loads the embedding model, was not measured; watch `docker stats` during the pilot.
- No Content-Security-Policy: the front end loads the editor from a CDN and a policy was not browser-tested.
- No HSTS: it would pin a self-signed certificate in browsers.
- The live `.env` must contain `SITE_ADDRESS` and a `TOOL_BASE_URL` that matches the server (needed for LTI); neither was changed here.
- The backup script does not copy dumps off the server, and the README's caveat stays: a restore brings back data erased since the dump.
