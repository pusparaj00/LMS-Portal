# Adaptive AI-Powered LMS

Frontend, API, PostgreSQL with pgvector, Redis and an isolated Python sandbox, started by Docker Compose.
Requirements and design are in `docs/` (read `docs/plan.md` first).

## Run

Needs Docker with Compose v2.

```sh
cp .env.example .env     # fill every value; use letters and digits only; JWT_SECRET should be 32+ random characters
docker compose up --build --wait
```

- Frontend health page: http://localhost:8080
- API health: http://localhost:8000/api/v1/health
- OpenAPI docs: http://localhost:8000/docs (frozen contract: `backend/openapi.json`)

The `migrate` service creates the schema and the `lms_api` and `lms_mastery` database roles
before the API starts. The API holds no owner credentials.

## Demo data (one command, safe to run again)

```sh
docker compose exec api python -m app.seed
```

This creates `instructor@demo.local` and `student@demo.local`, imports and validates the question bank (every reference
solution runs in the sandbox first), loads and embeds the course notes, enrols the student and adds a labelled class of
20 synthetic students. Passwords come from `DEMO_INSTRUCTOR_PASSWORD` and `DEMO_STUDENT_PASSWORD` in `.env`; if either is
empty, a random password is printed once when the account is created. Running the seed again changes nothing: existing
accounts and passwords stay, unchanged problems keep their ids and review status, and embedded notes are skipped.
The synthetic students (`synthetic-NN@synthetic.local`) cannot log in, and nobody can register on that domain.

To load pieces by hand instead: `app.manage create-user`, `app.bank_import data/bank --instructor EMAIL` (add
`--dry-run` to only validate), `app.notes_import data/notes --instructor EMAIL` and `app.synthetic --students 20`.

The scripted demo submissions in `data/demo/scenarios.json` have prepared explanations (`data/demo/explanations.json`)
that work with the model switched off. They are checked again by the verifier against each submission and are labelled
as cached in the reply, the interface and `explanation_checks` (model `cached-demo`).

## Instructor screens

Instructors can do the setup in the browser (the scripts above remain for bulk loading): create a course on the courses page,
then on the course page **Add a problem** (the reference solution must pass every test in the sandbox before it is saved) and
**Course notes** (paste text or upload `.md`, `.txt` or `.pdf`; a PDF must contain text, up to 4 MB, 100 pages and 50,000
characters, and is read in a separate limited process). A new course has no concepts and they cannot yet be created in the
browser; they come with the question bank import. Instructors can export mastery vectors and the mastery ledger for a course as
CSV or JSON (`GET /api/v1/courses/<id>/export/mastery` and `/export/mastery-events`, `?format=json`), with student numbers
instead of emails.

## Privacy notice and consent

A student sees a privacy notice at first login and must agree before their code, answers or messages are processed (run,
submit, placement test, explanations, hints, probes, chat); until then those endpoints answer 403. The notice lists the model
providers that are actually configured. Students can read it again and withdraw from **Privacy** in the top bar, which stops
the processing at once and keeps the record (`consents` table). Changing `CONSENT_VERSION` in `backend/app/consent.py` asks
everyone again. The text is a draft that still needs review by the institution's data protection contact, and deleting data on
request is not built yet. The seeded demo student starts without agreement, so the first login shows the notice; scripts that
create their own students call `evaluation/consent.py`.

## Stored explanations

A verified explanation is stored under the failure's signature (problem, failed test categories, error type, error
message). A later student with the same failure gets it without a model call, but only after it is checked again against
that student's code: the cited line must read the same and every verifier check must pass, otherwise the model is asked.
Instructors review the stored explanations on the class page (`#/class/<course id>`): approve, edit (the edit must pass
the same checks) or reject (a rejected one is never shown again).

## Backup and restore

The database is the only state to back up; Redis keeps its data on the `redisdata` volume (append-only file).

```sh
mkdir -p backup
docker compose exec -T db pg_dump -U lms_owner -Fc lms > backup/lms.dump
# restore: stop the app services, recreate the database, load the dump, start again
docker compose stop api worker mastery
docker compose exec -T db dropdb -U lms_owner lms
docker compose exec -T db createdb -U lms_owner lms
docker compose exec -T db pg_restore -U lms_owner -d lms --no-owner < backup/lms.dump
docker compose up -d --wait
```

`backup/` is git-ignored: a dump holds password hashes and student data.

A dump keeps data a student has since had erased (TR-S-07), and a restore brings it back. The operator must set how long
dumps are kept, delete old ones, and after a restore erase again anyone whose erasure completed after the dump was made
(the worker's log lists each completed erasure by user number). This repository sets no backup expiry.

## Audit trail and breach procedure (TR-S-08)

Logins, failed logins, refused (401, 403) and throttled (429) requests, not-found reads of submission ids, exports,
staff accounts created, consent changes and erasures are written to the `audit_events` table with the user number, IP
address and request id; never a password, token, email address, code or message. The API role can add and read events
but not change or delete them. `AUDIT_RETENTION_DAYS` (default 0, keep) removes older events. To see what happened in a
window:

```sh
docker compose exec -T api python -m app.breach_report --since 2026-10-16T00:00
```

What to do when a breach is suspected is in [docs/breach-procedure.md](docs/breach-procedure.md) (a draft until the
data protection contact has reviewed it and the contact names are filled in).

## Launch from Moodle or Canvas (LTI 1.3, TR-A-09)

Teachers and students can open the tool from their LMS course with no separate password. Only the core launch is
supported: no grade passback, roster sync or deep linking yet.

1. Set `TOOL_BASE_URL` in `.env` to the address the LMS and the browser use for this app (over HTTPS in production).
2. In the LMS, add an external tool, LTI 1.3, opening **in a new window**, with name and email sharing off:
   tool URL `TOOL_BASE_URL/`, initiate login URL `TOOL_BASE_URL/api/v1/lti/login`, redirection URI
   `TOOL_BASE_URL/api/v1/lti/launch`. The LMS then shows its client id, deployment id and its own URLs.
3. Register the LMS here:

```sh
docker compose exec -T api python -m app.manage lti-add-platform --issuer https://moodle.example.edu   --client-id CLIENT_ID --deployment-id 1   --auth-url https://moodle.example.edu/mod/lti/auth.php --jwks-url https://moodle.example.edu/mod/lti/certs.php
```

The first teacher to open the tool in an LMS course creates the matching course here and owns it; students are enrolled
when they open it, and still see the privacy notice first. A second teacher in the same LMS course is refused for now
(one teacher per course). Accounts made by a launch store no name or email from the LMS.

## Deletion and retention (TR-S-07)

A student can delete their account, submissions, chat messages and mastery from Privacy in the top bar. It runs 48 hours
after the request and can be cancelled until then; a banner shows the date. `RETENTION_DAYS` in `.env` (default 0, off)
schedules the same erasure, with the same 48 hours, for students with no activity for that many days. The worker
checks every minute; mastery rows are removed by the mastery service.

## Feedback loop

A failed submission can be explained. The explanation is produced by the configured LLM
(`LLM_PROVIDER=gemini` with `GEMINI_API_KEY`, or the stub), then checked by deterministic code before the student
sees it: the cited test failed, the line exists, the concept matches, the cited notes were retrieved, and the reply
contains no solution code. If the explanation names an input on which the program goes wrong, the sandbox runs the student's program and the reference solution on it and the explanation is accepted only if their outputs differ (the student then sees that input and their own output). After two rejected attempts the student gets a template hint. Every attempt is stored in
`explanation_checks`. Embedding model weights are baked into the Docker image at build time (this needs network
access once); running containers download nothing.

## Assistant chat and the instructor view

A chat panel on every student page routes each message to one capability: `explain` and `hint` use the verified
feedback flow, `progress` reads the student's own mastery through a read-only database role, and `general` answers from
the course notes with sources (or says no source was found). `recommend` and `lms` are recognised but not built. If the
model is unavailable or unsure, keyword rules choose the route and the panel says so; the student can correct it.
Instructors get a class mastery heatmap and misconception counts at `#/class/<course id>`.

`LLM_FALLBACK` lets the chat and feedback flows continue on another provider when the primary one fails or is out of
quota. Entries are `provider` or `provider:model`: `gemini` and `gemini_pro` (two Google AI Studio keys, so one key can
serve several models), `groq`, `openrouter`, `mistral` and `openai`; each needs its own key in `.env` and is skipped
without one. `local` is also accepted: any OpenAI-compatible server (Ollama, vLLM, LM Studio) at `LOCAL_LLM_BASE_URL`, with
`LLM_MODEL_LOCAL`, no key needed; from the containers the host machine is `host.docker.internal`, and local models need a
larger `LLM_TIMEOUT_S` and `LLM_BUDGET_S`. A provider that rejects its key (401, 403, 404) or reports exhausted quota is moved to the end of the chain
for a while, so a dead key costs no time on every request. The labelled synthetic class is part of the demo seed above.

## Sandbox queue and model usage

The sandbox runs one job at a time. When 20 jobs are already waiting, a new run waits up to 3 s, then gets "The sandbox is
busy" (HTTP 503 with `Retry-After`) and the interface retries on its own. `python -m evaluation.llm_usage` (in the api
container) reports model calls per 100 failed submissions and the share served from the caches.

## Sandbox

Student code runs only in the `sandbox` container: no network interface, read-only root, no
listening port, explicit CPU, wall-time, memory, process and output limits, and a throwaway
unprivileged uid. The API talks to it through job files on a shared tmpfs volume.

## Lint and test

```sh
docker compose up -d --wait
docker compose --profile test run --rm test      # ruff + pytest (API contract, DB roles)
cd frontend && npm ci && npm run lint            # type check
python backend/evaluation/secret_scan.py         # no key from .env or known key pattern in any file or commit
```

The tests use the same database as the app and remove the synthetic class while they run, so run
`python -m app.seed` again after the tests and before a demo. Enable the secret scan before every push with
`git config core.hooksPath .githooks`.

CI (`.github/workflows/ci.yml`) runs the same checks on every push.

If an API change is intended, regenerate the contract:
`docker compose run --rm --no-deps migrate python -m app.export_openapi > backend/openapi.json`
