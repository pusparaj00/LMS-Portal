# Step 59: audit after step 58 (2026-10-20)

Branch `step-59-audit` (from `step-58-production-hardening`). Every check below was run; nothing is claimed that was not.

## What was checked

| Check | How | Result |
| --- | --- | --- |
| Cross-course access (TR-S-02) | New `tests/test_cross_tenant.py`: builds a course with a real object behind every id (assignment with rubric, quiz, module, lesson item, announcement, category, handed-in work), then calls every course route as a teacher of another course and as a student who is not enrolled, with a valid body wherever the route needs one | 86 routes, 0 answered with a 2xx. Only `DELETE /courses/{id}/enroll` was excluded: leaving a course one is not in is a harmless no-op that returns 204. The existing role matrix only used the id 1, so it could not show this. |
| Erasure coverage (TR-S-07) | Listed every foreign key to `users` in the live schema and compared with the deletions in `app/erasure.py` and `erase_user_mastery` | Every table holding a student's rows is deleted; `audit_events` and `erasure_requests` are kept on purpose (TR-S-08) |
| Quiz attempt limit under concurrent submits | Read `routers/quizzes.py` | The quiz row is locked before the count (`FOR UPDATE`); no change needed |
| Handed-in work and grading | Read `routers/work.py` and `routers/grading.py` | Score bounds, rubric consistency, owner checks, audit entries and download names are all enforced; no change needed |
| Answer leaks in the placement test | Read the diagnostic and probe schemas and option ordering | Options carry only an id and text; order is shuffled per session; no change needed |
| Front end | `npx tsc --noEmit`; search for `dangerouslySetInnerHTML`, `innerHTML`, `eval`, and `target="_blank"` links | Type check clean; none of the unsafe patterns; external links carry `rel="noopener noreferrer"` and the server only stores http(s) links |

Full suite after the fixes: `docker compose --profile test run --rm test` (ruff and pytest): 1,072 passed, 2 warnings, 485 s (980 before; 86 cross-course, 4 leak, 1 chat and 1 start-up test added).

## Bugs found and fixed

1. **The leak guard let a short reference solution through whole** (`app/feedback/leak.py`, F-44, TR-L-06). The similarity rule
   skipped any code under 12 tokens, so for a problem whose solution is one line, such as `print(int(input()) + 1)`, a reply
   containing exactly that line passed (inline in backticks, or as a plain line). The 35 bank problems were all caught (0 of 35
   pasted whole got through), but instructors can create problems with tiny solutions. Now a reference shorter than 12 tokens is
   compared too, with a floor of 6 tokens (`long_enough_to_compare`). Pointers into a tiny solution, such as "convert it with
   `int(input())`", still pass. Bank evaluation unchanged (`python -m evaluation.leak_threshold`, threshold 0.7: 0 of 120
   solution fragments let through, 0 of 137 ordinary texts blocked, 61 of 2,890 other-problem fragments blocked, the same as before).
   Tests: `test_a_solution_shorter_than_the_usual_minimum_is_still_a_leak_when_pasted_whole` (2 cases, failed before),
   `test_a_pointer_into_a_tiny_solution_still_passes` (2 cases).
2. **The same blind spot in the open chat** (`app/chat/handlers.py`): with no problem open, the answer is compared with every
   solution in the student's courses, and that comparison also skipped code under 12 tokens. Closing the problem page and asking
   for the one-liner got the graded solution. Test: `test_a_very_short_course_solution_is_withheld_when_no_problem_is_open` (failed before).
3. **Weak production secrets did not stop the API from starting** (`app/main.py`, TR-O-04). The settings were read on the first
   request, so `import app.main` with a short `JWT_SECRET` and `APP_ENV=production` succeeded; the step 58 rehearsal had only
   proved the check by calling it by hand. The settings are now read at import. Test: `test_the_api_process_refuses_to_start_with_a_weak_secret_in_production`
   (starts a real process; failed before; also checks the secret is not printed).
4. **Rate limits could be shared by every user behind the proxy** (`frontend/nginx.realip.conf`, TR-O-03, a defect in step 58).
   nginx adopted the client address only from `172.16.0.0/12`. Docker also draws compose networks from `192.168.0.0/16` and
   `10.0.0.0/8` on a server with many networks; there nginx would have kept the proxy's address, and one class would have
   shared one login bucket. All three private ranges are now trusted (the port is not published in production).
   Not re-run against such a network: the change is a configuration list.

## Found and not changed

- `DELETE /courses/{id}/enroll` returns 204 for someone not enrolled (idempotent leave); harmless.
- A reference solution under 6 tokens is still not compared (a reply naming it could not be told from a pointer).
- The live stack still runs the images from before this step; the fixes apply after `docker compose up -d --build`.
