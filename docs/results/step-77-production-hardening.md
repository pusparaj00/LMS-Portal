# Step 77: security headers and off-server backup copy (G-8, TR-O-01, TR-O-06, TR-O-07)

Date: 2026-10-26. Branch `step-77-production-hardening`. This is still a local rehearsal: nothing was run on a real
server, so the real host, its firewall and a browser on another machine are untested.

## Headers

`Caddyfile` now sends `Strict-Transport-Security: max-age=31536000` (no `includeSubDomains` or `preload`: the site is an IP
address) and a `Content-Security-Policy` that allows only this origin (`script-src 'self'`; `style-src` also
`'unsafe-inline'` because React sets style attributes; `worker-src 'self' blob:` for the code editor; `frame-ancestors
'none'`; `object-src 'none'`).

Checked with `docker compose -p lmsprod -f docker-compose.yml -f compose.prod.yml up -d --build --wait` (Caddy on ports
18088/18443, fresh seed, removed afterwards with `down -v`) and Chromium through Playwright 1.64.1, signed in as the demo
instructor. `curl -skI https://127.0.0.1:18443/` shows both headers. The browser opened five pages and listened for
`securitypolicyviolation` events, console errors, page errors and failed requests:

| Page | Heading | Code editor | CSP violations |
| --- | --- | --- | --- |
| `#/` | My courses | - | 0 |
| `#/courses` | My courses | - | 0 |
| `#/course/1` | Python Fundamentals | - | 0 |
| `#/problem/1` | Bank account | 1 Monaco editor rendered | 0 |
| `#/course/1/problem/1/edit` | Edit the problem | none on this page | 0 |

Also 0 console errors, 0 page errors, 0 failed requests; the public landing page rendered with 0 violations. Not covered:
the other roles' pages, the student placement page and the admin pages.

## Off-server copy

`scripts/offsite-copy.sh` copies the newest dump in `backup/scheduled` to `OFFSITE_TARGET` (a folder, or `user@host:folder`
through scp) and keeps the copy only if its sha256 matches the original. Tested on this machine with a folder as the target:
a good copy is kept and reported with its checksum; no dump, or no target, stops with a message and exit status 1; a copy
made by a `cp` that truncates the file is rejected, exits 1 and leaves no file behind. The `scp` branch was **not** run (no
second host here); it follows the same compare-then-rename order but is untested.

## Not done

Memory limits are still caps, not measured peaks (needs the pilot); the real server and its certificate (G-8).
