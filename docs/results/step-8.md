# Step 8 results: closing the P0 and P1 gaps from the gap report

All runs on 2026-10-15 on the local Docker Compose stack; browser checks use Chromium through Playwright 1.55. Commands are
run from the repository root; the Python ones as `docker compose exec -T api python -m ...`.

## TR-P-08: model calls per 100 failed submissions

`python -m evaluation.llm_usage`, run 2026-10-15 18:25 UTC. These are development-database numbers: they include my
evaluation runs, the load tests and the demo runs, so they describe the dev data, not a class.

| Measure | Value |
| --- | --- |
| Failed submissions explained | 175 |
| Live model calls (attempts) | 150 |
| **Model calls per 100 failed submissions** | **85.7** |
| Most calls for one submission (limit: 2) | 2 |
| Served from the failure-signature cache | 5 |
| Served from the prepared demo explanations | 31 |
| **Share served without a model call** | **21%** |
| Ended as a template hint (verifier rejected twice or the model failed) | 6 |

The limit of two calls per failed submission holds. Attempts that failed because the provider failed still count as calls.

## TR-P-05: a full sandbox queue

The runner takes one job at a time. The API now refuses to queue a job when 20 are already waiting, waits up to 3 s for
room, and otherwise answers HTTP 503 with `Retry-After: 2` and "The sandbox is busy right now". Nothing is stored for a
refused request. The interface retries automatically, up to 3 times, and says so.

- Tests (`tests/test_sandbox_busy.py`, 6): a full queue raises busy after the short wait and starts nothing; a queue that
  drains inside the wait is used; the API answers 503 with Retry-After for a run and for a submission; a busy submission is
  not stored; a retry after the queue drains succeeds; a runner that is down is not called busy and gets no Retry-After.
- Browser check against the real stack: the sandbox container was stopped, 20 placeholder job files put in its queue, and
  "Run examples" clicked as the demo student. The page showed "The sandbox is busy, trying again (1 of 3)…". The sandbox was
  then started; the next retry went through and the result ("2 of 2 tests failed" for the empty starter code) appeared.

## TR-A-04: a local model without code changes

`LLM_PROVIDER=local` (or `local` in `LLM_FALLBACK`) with `LOCAL_LLM_BASE_URL` and `LLM_MODEL_LOCAL` sends the same requests
to any OpenAI-compatible server (Ollama, vLLM, LM Studio), with no key needed. Tested against a real HTTP server on
localhost (the chain answers from it and sends no Authorization header), an unreachable server (the chain moves on to the
next provider), and a missing URL (skipped). **Not run:** the demo on an actual local model (TR-V-12), which needs a model
installed on this machine.

## TR-D-07: export

`GET /courses/{id}/export/mastery` and `/export/mastery-events`, `?format=csv` (default) or `json`, for the instructor of
the course or an admin. Columns are the student's numeric ID and a `synthetic` flag, never an email address; text that a
spreadsheet would run as a formula is prefixed with an apostrophe. Tests check the row counts against the database, that CSV
and JSON agree, that the last event of every student and concept equals the current mastery (the ledger replays to today's
vector), and the access rules. The tests also caught a leak in my first version: the JSON export included the email column.
It was fixed before the commit.

## F-02 and F-03: instructor screens, notes from PDF

- New screens: create a course (courses page), add a coding problem (statement, concept weights, reference solution, tests
  with category and hidden flag), and course notes (paste text, upload `.md`, `.txt` or `.pdf`, see each note's status).
- `GET /courses/{id}/concepts` lists a course's concepts for the forms.
- PDF text is read by `pypdf` 6.20.1 in a **separate child process** with no environment variables, a 1 GiB memory limit, a
  15 s CPU limit and a 20 s timeout. Limits: 4 MB, 100 pages, 50,000 characters (longer text is refused, not cut), no
  password protection, text pages only. The body limit is raised to 6 MB for the notes upload only (and in nginx for `/api/`).
- Tests (`tests/test_notes_upload.py`, 16): a real PDF becomes the note; corrupt, scanned (no text), 101-page, encrypted,
  oversized and non-PDF files are refused with a reason and nothing is stored; invalid base64; too much text; only the notes
  route accepts a large body; the reader gets an empty environment and a time limit; a decompression bomb (400 MB once
  unpacked) is refused in a few seconds and the API stays healthy. A 1.5 GB bomb was also tried by hand: refused after 3.4 s.
- The reference-solution failure message now reads, for example, "reference solution fails test 1 (basic): it printed '6'
  but the test expects '7'" (it said "test 0 ... : ok" before).
- Browser run on a fresh, separate stack seeded from scratch (so the dev data was not touched): created a course; the empty
  course's form explained that concepts are needed; a problem whose expected output was wrong was refused with the message
  above, and saved once corrected (the reference solution had passed in the sandbox); a Markdown file and a PDF were
  uploaded and both reached "ready" (the page polled until the worker finished); a corrupt PDF was refused with "the PDF
  could not be read"; at 390 px width the problem form had no horizontal scroll.
- **Limit:** a new course has no concepts, and concepts cannot be created in the browser, so the problem form works for
  courses that came with concepts (the question bank import). This is the one F-02 gap left.

## TR-P-09: 1366 px

Every screen was loaded at 1366 x 768 in Chromium (the engine Chrome and Edge share) as the demo student or instructor: login,
courses, course problems, problem with editor, placement start, mastery dashboard, "why did my mastery change", the same
courses and problems as instructor, class overview with stored explanations, add a problem, course notes. For all 12: no
horizontal scroll and no browser console errors. Microsoft Edge 155.0.4283.45 (headless, on this machine) rendered the login
page correctly. **Not done:** the other screens in Edge itself and in Chrome itself (scripted login needs a driver for them),
and a look at the placement test question screens beyond the start page.
