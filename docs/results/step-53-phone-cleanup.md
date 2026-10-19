# Step 53: Phone-width check and cleanup (TR-P-09)

Date: 2026-10-19. Branch `step-53-phone-cleanup` (from `step-52-instructor-insight`). No migration, no backend change.

## Phone width

Method: Playwright with a 390x844 phone profile (touch, device scale 2), 33 pages (15 as a student, 18 as a teacher)
over a class built through the API with a long course title, a topic, a lesson, a quiz, a rubric, a hand-in with a very
long link and a private comment. For every page it compares the page's scroll width with the real screen width and lists
every element that sticks out and is not inside its own scrolling area, and it lists controls smaller than 24x24 pixels
(the WCAG 2.2 AA minimum for a tap target).

My first sweep was wrong: in phone emulation `window.innerWidth` grows to match wide content, so I compared the page with
itself and reported every page as fitting while a screenshot showed content cut off. The sweep now measures against
`document.documentElement.clientWidth`, which is the real screen.

Found and fixed:

| Page | Cause | Fix |
| --- | --- | --- |
| Calendar (student and teacher) | the course picker grew to the width of the longest course title | selects and inputs are limited to the screen; inline labels wrap |
| Rubrics (teacher) | a level's name and points did not wrap | `.concept-pick` wraps on phones |
| Review a hand-in (teacher) | a long link and the work text forced the two-column layout wider than the screen | grid children may shrink; long words and links break anywhere |
| Classwork (student) | an assignment row (title line plus the score badge) did not wrap, 19 px too wide | rows wrap on phones |
| Analytics (teacher) | the "screen reader only" tables used a class (`sr-only`) the stylesheet did not define, and a table cannot shrink below its content, so a 674 px table extended the page | `.sr-only` is defined and the two tables sit in a hidden wrapper |
| Several forms | checkboxes and radio buttons 13 px wide, text buttons (Delete, Adjust) 24 px high | on phones: boxes and radios 24 px, buttons at least 40 px, text buttons at least 36 px |

Result after the fixes (`docker compose up -d --build frontend`, then the sweep, 2026-10-19): 0 of 33 pages wider than the
screen and 0 controls under 24x24 pixels. The code editor's own inner layers on the problem page are ignored by the
sweep (they scroll inside the editor).

Not checked: a real phone or a real touch keyboard (this is an emulated profile); the light theme at phone width;
landscape.

## Cleanup of the development database

- **Done:** `backup/cleanup-2026-10-19.sql` removed this session's throwaway accounts (every `@eval.local` account created
  on 2026-10-19) and the courses they owned. Before running it for real it was dry-run in a transaction that rolls back.
  Nine guards confirmed nothing outside the removal sets was tied to it, and the script compares the row counts of 17
  kept tables before and after and refuses to commit on any difference. Removed: 30 accounts, 26 courses, 8 problems,
  31 assignments and 10 hand-ins with everything attached. Kept totals unchanged (523 accounts, 50 courses, 204
  enrolments, 327 submissions, 1522 mastery rows, 7358 audit events, 19 erasure requests). A dump was made first:
  `backup/lms-2026-10-19-before-cleanup.dump` (git-ignored).
- **Not done, needs your decision:** about 490 older test and evaluation accounts from 15 to 17 October remain (260
  `@order.test`, 226 `@eval.local`, and a few `@lti.local`, `@test.local` and `@t.*`), against about 30 real, demo and
  synthetic accounts. A dry run of removing all of them (`backup/cleanup-2026-10-19-all-test-accounts.sql`) stopped at its
  guards, as designed: 131 of those accounts are enrolled in kept courses (the demo class), 2 kept accounts are enrolled
  in their courses, 2 kept students' submissions are on their problems, and there is 1 LTI link with 2 LTI accounts. Taking
  the accounts out of the demo class, and what to do with the LTI link and those 2 kept accounts, is your call; nothing was
  deleted by that script.
