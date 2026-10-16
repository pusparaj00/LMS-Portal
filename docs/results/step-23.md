# Step 23 results: the assistant's recommend and lms routes (F-52, P0)

All runs on 2026-10-16, branch `step-23-chat-routes`.

## Why this step

F-52 is a P0 feature: "each route calls its own tool or agent and returns a response with its sources". Four of its six
routes worked; `recommend` and `lms` were recognised but answered "not available". The DRD's router table specifies
them:
- recommend: "mastery service, problem bank, giving the next problem or note, with the reason";
- lms: "LMS database (read only, scoped to the user), giving a direct answer from records".

The lms route had nothing to read until assignments, grades and announcements arrived (Steps 14 and 17).

## What was built

- **recommend** gives the easiest unsolved problem on the weakest concept, with the reason and the mastery value,
  plus the first section of course notes tagged with that concept, cited as its source. When everything is solved, it
  says so.
- **lms** answers from the student's own records, in the open problem's course or all of their courses:
  - deadlines: what is due, with status and points so far, and what was missed;
  - grades: on-time scores and the total, mentioning late work that is not counted;
  - announcements: the latest three;
  - anything else: the enrolled courses with the deadlines and announcements.
- **No model writes these replies.** They are fixed sentences filled from records, so a date or score cannot be
  misstated. The model only picks the route, and the keyword fallback picks it when the model is down.
- **One rule each, shared.** The score rule and the next-problem rule are now database functions (migration 0017):
  - `assignment_scores` is used by the gradebook and the lms route;
  - `next_problem` is used by the dashboard and the recommend route;

  so the assistant cannot disagree with what the student sees elsewhere.
- **Least privilege kept (TR-A-02).** The assistant reads through its read-only role, which since Step 5 may not read
  submissions, run results or users (every student's code, and password hashes). The plan said to grant it the tables
  it needed; that would have broken this guarantee, so instead the two functions run as their owner and return only
  numbers, titles and dates. The role was granted only the course-level tables with no personal data: assignments,
  announcements, documents, chunks. It still cannot read problems, so reference solutions stay out of its reach.

## Tests

`docker compose --profile test run --rm --build test`: **639 passed**, ruff clean. `backend/tests/test_chat_routes.py`
has 8 tests; the old "not built, says so" test now only checks the routing.
- **recommend:** gives the dashboard's own recommendation, with the reason and the notes section as a source, and no
  model call; says when everything is solved.
- **grades:** equal the gradebook's numbers for this student, and another student's score does not appear.
- **deadlines:** upcoming work is listed with status, missed work as "Missed".
- **announcements:** only from the student's courses.
- **Model off:** with the model failing, both routes still answer, routed by keywords.
- **No course:** a student with no course is told so.
- **The chat role:** can read the course-level tables and call both functions; still cannot read submissions, run
  results, users, problems or code, and cannot write.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, a throwaway student asked the live stack (real model doing the routing):

| Question | Route | Reply |
| --- | --- | --- |
| What should I do next? | What next | Try "Count to n" next: loops is your weakest area (50% mastery). It may help to read "Loops > Counting with range" in the course notes first. |
| When is my assignment due? | Course info | "Week 1" (Routes course ...) is due 19 Oct 2026, 15:12 UTC: not started, 0 of 2 points so far. |
| What are my grades? | Course info | Your on-time scores: "Week 1": 0 of 2. Total 0 of 2. |
| Any announcements? | Course info | Latest announcements: "Lab moved to Friday" (Routes course ..., 16 Oct 2026, 15:12 UTC). |

No page errors, no 5xx responses, no horizontal overflow.

## Limits

- Times in replies are in UTC, because the server does not know the student's time zone; the course pages show local
  time.
- Which part of the lms route answers is chosen by keywords in the message (grades, announcements, deadlines), not by
  the model.
