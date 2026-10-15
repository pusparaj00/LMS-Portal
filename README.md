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

## First-time data

```sh
NEW_USER_PASSWORD='choose-a-password' docker compose exec -e NEW_USER_PASSWORD api   python -m app.manage create-user instructor@example.com instructor
docker compose exec api python -m app.bank_import data/bank --instructor instructor@example.com
```

Then queue the course notes for the worker to embed (about 20 seconds the first time):

```sh
docker compose exec api python -m app.notes_import data/notes --instructor instructor@example.com
```

`bank_import` runs every reference solution in the sandbox first and loads only problems that
pass; add `--dry-run` to validate without loading. Students register themselves in the browser.

## Feedback loop

A failed submission can be explained. The explanation is produced by the configured LLM
(`LLM_PROVIDER=gemini` with `GEMINI_API_KEY`, or the stub), then checked by deterministic code before the student
sees it: the cited test failed, the line exists, the concept matches, the cited notes were retrieved, and the reply
contains no solution code. After two rejected attempts the student gets a template hint. Every attempt is stored in
`explanation_checks`. Embedding model weights are baked into the Docker image at build time (this needs network
access once); running containers download nothing.

## Sandbox

Student code runs only in the `sandbox` container: no network interface, read-only root, no
listening port, explicit CPU, wall-time, memory, process and output limits, and a throwaway
unprivileged uid. The API talks to it through job files on a shared tmpfs volume.

## Lint and test

```sh
docker compose up -d --wait
docker compose --profile test run --rm test      # ruff + pytest (API contract, DB roles)
cd frontend && npm ci && npm run lint            # type check
```

CI (`.github/workflows/ci.yml`) runs the same checks on every push.

If an API change is intended, regenerate the contract:
`docker compose run --rm --no-deps migrate python -m app.export_openapi > backend/openapi.json`
