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
