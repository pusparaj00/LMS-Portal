# Step 29 results: one request ID into the sandbox, and concept tags on chat questions (TR-A-08, TR-M-08)

All runs on 2026-10-17, branch `step-29-request-trace`.

## TR-A-08: the request ID reaches the sandbox

**Before:** structured logs carried the request ID through the API, the router and model calls, but not into the
sandbox, which logged nothing.

**Found on the way:** the API took a caller's `X-Request-ID` as it came. A 5,000-character value sent with a failed
login, by someone not signed in, was stored as-is in the append-only audit trail.

**What was built:**
- **The API checks the ID.** It keeps a caller's ID only if it is 1 to 64 letters, digits or `._-`; otherwise it makes
  its own.
- **The ID travels with the job.** It goes into the sandbox job file.
- **The sandbox logs each job.** After answering, it writes one JSON line per job in the API's log format: the request
  ID, the job ID, how many runs, the count of each status, and the duration. It never logs the code, the input or the
  output.

**Live trace (2026-10-17).** A submission sent with `X-Request-ID: tr-a-08-live-1` appears under that ID in three
places:
- the API's request log;
- its call to the mastery service;
- the sandbox's line: `"request_id": "tr-a-08-live-1", "message": "job finished", "runs": 5, "statuses": {"ok": 5},
  "duration_ms": 144`.

The same 5,000-character login now stores a fresh 32-character ID.

## TR-M-08: chat questions carry a concept

**Before:** each chat question was stored with its route but no concept.

**What was built:**
- `chat_messages.concept_id` (migration 0019), set on the student's question.
- **The tagging rule is fixed, never the model.** The tag is the course concept the question names: whole name, name
  parts and singular forms, so `tuples_sets` matches "set" and `classes` matches "class". When several match, the
  longest name wins, so "list comprehension" is comprehensions, not lists. When no concept is named, the tag is the
  open problem's main concept; otherwise it is empty.
- **The concept-delete guard counts tagged questions.** A concept students have asked about is renamed, not deleted,
  like one with mastery history.

Nothing reads the tag yet. It is stored for later use as a mastery signal, as the requirement says. The mastery
service, the only writer of mastery, is unchanged.

## Tests

`docker compose --profile test run --rm --build test`: **662 passed**, ruff clean. That is 6 new.

`backend/tests/test_request_trace.py` (2 tests):
- a plain ID is kept, while one that is too long, contains spaces or line breaks, or is empty is replaced;
- the sandbox job carries the request ID.

`backend/tests/test_chat_concept.py` (4 tests):
- **Name forms:** name parts and singulars are recognised; "io" is too short.
- **Questions are tagged:** by the named concept, by the open problem, or left untagged.
- **Precedence:** the longest name wins, and "reset" does not count as "set".
- **The guard:** a concept asked about cannot be deleted.

The existing check that the delete guard covers every foreign key to `concepts` passes with the new column.
