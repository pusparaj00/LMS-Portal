# Step 9 results: concepts in the browser, consent, claimed-input check

All runs on 2026-10-16 (browser checks on throwaway stacks, so the dev data was not touched).

## F-02: creating concepts in the browser

`POST /courses/{id}/concepts` (instructor of the course only) and a "New concept" field inside the problem form. A name
is tidied into the question bank's form (`Number doubling` becomes `number_doubling`); an invalid or repeated name is refused
with a reason. A new concept needs nothing else: mastery starts at the population prior and uses the default slip and guess
rates, and a failed test links to the problem's own concepts when the evidence map has no row for it.

- Tests (`tests/test_concepts.py`, 14 cases, plus the access matrix): empty course, tidy-up of names, duplicates (and the
  same name allowed in another course), unusable names, who may add, and one end-to-end test: new concept, then a problem
  that passes the sandbox check, a note tied to it, a student's mastery starting at 0.5 and rising after a pass.
- Browser run (fresh stack, Chromium 1366 x 768): created a course; its form said a concept is needed; "9 bad name!" was
  refused with the reason and the problem form was not submitted; "Number doubling" was added with Enter and appeared
  ticked; adding it again was refused; a problem was saved for it (reference solution passed in the sandbox); the notes
  page offered the new concept; a new student solved the problem and mastery of the new concept went from 0.5 to 0.818;
  at 390 px the form had no horizontal scroll.

## TR-S-05 (and the test for TR-S-06): privacy notice and consent

A student's code, answers and messages are processed only after they agree to the current privacy notice; withdrawing stops
the processing at once.

- **Notice** (`GET /consent/notice`): what is collected, why, who receives it, how long it is kept, how to withdraw, and its
  own status ("a draft, not yet reviewed by the institution's data protection contact"). The list of model providers is read
  from the live configuration (only providers with a key or URL, in the order they are tried, Google once), so it cannot name
  a provider the system does not use. With no provider configured it says nothing is sent outside.
- **Record** (`consents` table, migration 0008): version, `accepted_at`, `withdrawn_at`; the newest row is the current state;
  withdrawing keeps the record; agreeing again adds a new one. A new notice version asks everyone again, and an acceptance of
  an old version is refused (409).
- **Enforcement:** run, submit, placement test, explain, hint, probe answer and chat answer 403 for a student without current
  agreement. Enrolling, reading the notice and reading their own mastery stay available. Instructors and admins have no
  consent state.
- Tests (`tests/test_consent.py`, 12; plus the access matrix): all seven processing endpoints blocked for a newcomer;
  agreeing is idempotent and timestamped; withdrawing blocks at once and keeps the record; a changed version; the provider
  list for several configurations; and, for TR-S-06, that the prompts actually sent for an explanation and for a chat
  message contain neither the student's email address nor its local part.
- Browser run (fresh stack, logging in through the real login form): the first login showed the notice before anything else
  (provider list: Google first, then Groq, OpenRouter, Mistral AI, OpenAI, the keys actually configured); the assistant button
  was hidden; going to `#/courses` still showed the notice; a direct API call answered 403; "I agree" opened the courses page;
  an exercise ran in the sandbox; the Privacy page showed the agreement time and the withdrawal confirmation; after
  withdrawing the notice blocked the app again and the chat API answered 403; agreeing again restored access; an instructor
  could read the notice but had nothing to agree to; at 390 px there was no horizontal scroll.
- The evaluation and load scripts agree to the notice for the test students they create (`evaluation/consent.py`); a demo
  run (2 flows, 0 of 42 steps failed) and the cache measurement still pass with the gate on.
- **Limits:** the notice text is a draft for the institution's data protection contact to review. Deleting data on request,
  scheduled erasure and retention settings (TR-S-07) are not built, and the notice says so. The demo student account is
  created without agreement on purpose, so the first login shows the notice.
