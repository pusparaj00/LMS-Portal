# Adaptive AI-Powered LMS

Step 1 foundation: frontend, API, PostgreSQL with pgvector and Redis, started by Docker Compose.
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

## Lint and test

```sh
docker compose up -d --wait
docker compose --profile test run --rm test      # ruff + pytest (API contract, DB roles)
cd frontend && npm ci && npm run lint            # type check
```

CI (`.github/workflows/ci.yml`) runs the same checks on every push.

If an API change is intended, regenerate the contract:
`docker compose run --rm --no-deps migrate python -m app.export_openapi > backend/openapi.json`
