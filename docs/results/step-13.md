# Step 13 results: LTI 1.3 launch (TR-A-09, F-70)

All runs on 2026-10-16, branch `step-13-lti-launch`.

## What was built

The LTI 1.3 Core launch only. Grade passback (AGS), roster sync (NRPS), deep linking and dynamic registration are not
built.

- **Registration:** `python -m app.manage lti-add-platform` stores the issuer, client id, auth URL, key set URL and
  deployment ids (`lti_platforms`, migration 0011).
- **`/api/v1/lti/login`** (GET or POST, OIDC login initiation): checks the platform and that `target_link_uri` is this
  tool, keeps a one-time state and nonce in Redis for 10 minutes, sets a cookie bound to that state (`SameSite=None;
  Secure` over HTTPS, `Lax` on plain HTTP) and redirects to the platform.
- **`/api/v1/lti/launch`:** checks the state cookie, uses the state once, verifies the RS256 signature against the
  platform's published keys (cached for an hour; fetch timeout `LTI_KEYS_TIMEOUT_S`, default 5 s), issuer, audience and
  `azp`, expiry, nonce (once), deployment id, message type and version, target URI, context, and roles. Then it maps:
  - Instructor or Administrator (course membership) becomes instructor; Learner becomes student; anything else is refused.
  - The first teacher launch in an LMS course creates the course here, owned by that teacher. A student launch before
    that is refused, and so is a second teacher (one teacher per course). Students are enrolled on launch.
  - An LMS user maps to one account with a placeholder address `lti-<platform>-<hash>@lti.local` (domain reserved
    against self-registration) and an unusable password. No name or email from the LMS is stored.
- **Handover:** a one-time code (60 s) in the URL fragment, swapped once for a session via `POST /api/v1/lti/session`.
- **Audit:** `lti.launch` and `lti.launch_refused` (with the reason), `lti.platform_registered`.
- **Erasure** also removes the `lti_users` row.
- **New dependency:** `cryptography==50.0.2` (with `cffi` and `pycparser`), which PyJWT needs for RS256.

## Tests

`docker compose --profile test run --rm --build test`: **540 passed**, ruff clean. `backend/tests/test_lti.py` has 16
tests against a fake platform that signs with its own RSA key and serves its key set over HTTP:
- **Happy path:** teacher launch creates the course, student launch enrols, the same account is reused, no LMS name or
  email is stored, and the student still sees the privacy notice.
- **11 refused launches:** wrong key, issuer, audience, expired, nonce, deployment, message type, version, target,
  missing context, unsupported role. Each creates nothing and is audited with its reason.
- **Binding and reuse:** another browser cannot use the state, a state cannot be used twice, a code works once.
- **Login initiation** checks the platform and target, and accepts GET and POST.
- **Course rules:** student before the course exists, second teacher, and an account's role cannot switch.
- **Reserved domain:** `@lti.local` cannot self-register.

## Live run on Moodle 5.3

Moodle `5.3+ (Build: 20261013)` from `MOODLE_503_STABLE`, run with the official `moodlehq/moodle-docker` (pgsql) as a
separate compose project (`moodlelti`, port 8180) in `C:\Users\govin\moodle-lti-test`, outside this repository.
`backend/evaluation/lti_moodle_setup.php` registered the tool (LTI 1.3, new window, no name or email sent), a course
"Python 101 (Moodle)", a teacher and a student, and the activity; the platform was then registered with
`app.manage lti-add-platform`. Playwright logged in to Moodle and opened the activity:

| Who | Path | Landed on | Role shown |
| --- | --- | --- | --- |
| teacher1 | Moodle launch, our login, Moodle auth, our launch | course 1099 "Problems" | instructor |
| student1 | same | privacy notice (agreement comes first) | student |

The course here took Moodle's title, is owned by the teacher's account and has the student enrolled; both accounts carry
placeholder addresses only. Audit rows `lti.launch` were written for both.

Two things were needed only for this local Moodle:
- Its pages took 12 s each (PHP source on a Windows bind mount), so the first two launches were refused with
  `keys_unavailable` (the refusal page and audit reason worked as intended). `LTI_KEYS_TIMEOUT_S=30` was set for the run
  and then removed again.
- The API container reaches Moodle as `host.docker.internal:8180` while Moodle's address is `localhost:8180`, so the test
  Moodle's `config.php` treats that host name as `localhost:8180`. Nothing in this app depends on it.

## Not done

- Canvas not tested (same standard; no instance available).
- Launch inside the LMS iframe is not supported: the state cookie would be third-party. The tool must be set to open in a
  new window.
- One teacher per course; a co-teacher is refused.
