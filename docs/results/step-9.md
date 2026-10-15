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

## TR-L-05: the claimed input is tried in the sandbox

The reply format gained one optional field, `example_input` (prompt version `explain-v2`). When the explanation says the
program goes wrong on a specific input, the verifier runs the student's program and the reference solution on that input in
the sandbox and accepts the reply only if their outputs differ. The reply is also rejected if the example equals any hidden
test input of the problem (passed or failed), is longer than 300 characters or is not text; if the correct program cannot
read it; if no reference solution exists; or if the sandbox cannot run it (a claim that cannot be tried is never shown). All
other checks run first, so the sandbox is only used for replies that would otherwise pass.

- **What the student sees:** a "Try it yourself" block with the input and what **their own** program printed (or that it
  stopped with an error). The reference solution's output is never shown, so the field cannot be used to probe it.
- **Caches:** the example is stored with the explanation, and tried again on every later student's own code (a student whose
  program already handles it does not get the claim). An instructor's approval re-runs the check too.
- Tests (`tests/test_claimed_input.py`, 13): an example that really differs is verified and shown with the student's own
  output (two sandbox runs); an example on which the program is already right is rejected and the retry is told why; a hidden
  test input is never shown; a crash counts; an input the correct program cannot read is rejected; no example means no
  sandbox run and an unchanged flow; a non-text or over-long example is rejected before anything runs; a sandbox that is down
  means the claim is not shown; a stored example is served with a fresh run for the next student; a stored example is dropped
  for a student who already handles it; approval re-runs the check; the prompt and schema carry the field.
- **Live model** (`python -m evaluation.real_feedback ten`, `gemini-3.5-flash-lite`, 2026-10-15 19:25 UTC): 3 of the 10
  submissions were served from the caches (attempts 0), so 7 were live model calls. All 7 were verified, 6 on the first
  attempt. The one retry (Safe division) was the expected failure: the model chose an input equal to a hidden test input and
  the check rejected it. In the database, all 7 final replies named an example input and all 7 were confirmed by the sandbox.
  In a later browser run on "Leap year" the model named no example, which is allowed (the field is optional), so about 7 of 8
  live replies carried one. Eight live calls is a small sample; the earlier 10 of 10 first-attempt result was without this
  field, on a different mix of cached and live calls, so the two are not directly comparable.
- **Limit:** stored explanations made before this change have no example, and the first stored explanation for a failure
  keeps its place, so those failures keep the old form until an instructor rejects the entry.
- Browser check: with the explanation reply mocked (the optional field cannot be forced from the live model), the panel shows
  the input and the student's output, and there is no horizontal scroll at 390 px. This also found a layout flaw that was
  already there: the problem page was wider than a 390 px phone (a grid column could not shrink below its input boxes). Fixed in
  `styles.css`; the page now fits.
- Also fixed: a passing check no longer stores failure wording as its detail (`example_input_ok`).
