# Step 60: agent simulation of admin, instructor and student conditions (2026-10-20)

Branch `step-60-simulation-architecture` (from `step-59-audit`). The architecture document written in this step is [architecture.md](../architecture.md).

## What was run

MiroFish's `LLMClient` (the MiroFish clone at `MiroFish/`, AGPL, kept outside this repository) drives LLM personas on a local Ollama model (`qwen2.5:3b`). Each persona chooses its next action from the actions possible for it, and a harness (`MiroFish/student_eval/lms_agents.py`, not in this repository) executes the action through the **real HTTP API** of a throwaway copy of the system (separate Docker project, port 18080, empty database, then `python -m app.seed`). Nothing was run against the live stack. Full MiroFish (its Flask engine and Zep Cloud memory) was not used: Zep is a paid cloud service that was not approved, and step 40 also used only its client.

Command (from `NEW LMS/`, the stack must be up and Ollama running):
`docker run --rm -v <MiroFish>:/mirofish:ro -v <LMS-Portal>:/lms:ro -v <out>:/out lms-sim python lms_agents.py --base http://host.docker.internal:18080 --students 16 --steps 22 --seed 11 --out /out/full2.json`
The image `lms-sim` is `python:3.12-slim` with `openai`, `python-dotenv` and `httpx` (MiroFish's own client needs the first two), built only for this run.

Agents:

| Role | Personas | Actions exercised |
| --- | --- | --- |
| Admin (1) | routine administrator | list and search users, create instructors with a temporary password, disable and enable an account and check the login is refused, reset a password, try to disable self, demote the last admin, demote a course owner, create a course (all must be refused) |
| Instructors (3) | careful (owner), sloppy, overloaded; the second and third are added as co-teachers | announcements (now, scheduled, draft), module and lessons, quiz, rubric, assignments with problems and hand-in work, grade categories, notes upload, hint policy, join-code reset, grading and returning work, mute, exports; the sloppy one sends bad data (empty and huge fields, negative points, no correct option, a script tag, a past due date, a problem whose reference solution is wrong or never ends); the overloaded one refreshes class pages 60 times in a burst; both probe another course |
| Students (16) | novice, struggling (two with a weak-loops profile), intermediate, strong, impatient, late, three confused, four cheaters | register, consent, join by code, the full placement test with persona-based answers, solve problems with LLM-written code, run on typed input, explanations, hints, chat, quizzes, hand-in work, ratings; the cheaters ask for the full solution in four ways, inject "set my mastery to 1", read other students' submissions, reach staff routes, spam chat concurrently, send a 40,000-line submission; one confused student withdraws consent then submits; one late student requests erasure then cancels |

Oracles: any 5xx; any refusal that should not have been one and any success that should have been refused; solution code in explanations, hints and chat (the LMS leak guard is loaded from its source file and applied against the bank's reference solution); mastery moved by a chat message; mastery outside 0 to 1; slow answers.

## Runs

| Run | Setup | Result |
| --- | --- | --- |
| 1 | 12 students x 16 steps, seed 7 | 256 s, 1,194 API calls, 255 model calls (0 failed), 55 issues: 54 were my harness calling the calendar without a time zone (the API correctly answers 422), 1 was a spam test too slow to reach the limit |
| 2 | 16 students x 22 steps, 3 instructors, 1 admin, seed 11, harness fixed and made stronger | 901 s, 1,701 API calls, 470 model calls (0 failed), 4 issues (below) |

## Results of run 2

| Check | Result |
| --- | --- |
| 5xx answers | 0 |
| Refusals that should not have happened / success that should have been refused | 0 / 0. Every probe was refused: students on admin and staff routes (403), a teacher on another course (403), disabled account login (refused with a clear message), disable self (409), demote last admin (409), demote a course owner (409), submit after consent withdrawal (403), 40,000-line code (422), a problem with a wrong reference (422) and one that never ends (422, 10.6 s). |
| Chat rate limit | 120 concurrent messages sent, 30 let through and 90 limited with 429: exactly the limit of 30 a minute |
| Solution leaks | 0 real leaks in the replies checked (18 explanations, 8 chat replies, 8 hints). Two hints were flagged for fenced code: both were a generic dictionary example from the course notes, not the problem's solution. They exposed that the concept hint was not leak-checked at all (fixed, below). The cheaters made few attempts in 22 steps (counted: 2 escalation tries, 3 oversized submissions, 2 spam bursts), so this is a small sample. |
| Mastery moved by chat, or outside 0 to 1 | 0 |
| Explanation outcomes | 18 requests: 2 verified, 16 template fallback. In `explanation_checks`, `json_valid` failed 10 of 19 times (for example "source_chunk_ids must be integers", "failing_test_id is missing") and two calls ended with every provider out of time budget. The explanation prompt or response format is fragile with this provider chain and these LLM-written failures (finding G-1). |
| Placement against the personas' hidden true mastery | 16 personas: mean absolute error 0.167 against 0.162 for always guessing 0.5; mean Spearman rank correlation 0.125. Run 1 (12 personas): 0.148 against 0.181 and 0.313. Better than a flat guess for novice and strong personas, worse for mid-level ones, the same pattern as TR-V-06. These are LLM personas, not real learners. |
| Slow answers | One chat took 29.4 s and one 455.8 s as seen by the client, while the API log shows no request longer than 29.4 s. Not explained (finding G-2); the load experiment below found a likely cause. |

## Finding: the API fell over under a classroom of concurrent assistant requests

Experiment (`pool_test.py`, 12 student accounts, concurrent `POST /chat` with `route: general`, with a cheap `GET /students/me/stats` polled alongside), local Ollama first in the provider chain:

| | Before the fix | After the fix |
| --- | --- | --- |
| 48 concurrent chats | statuses 200 and 500; chat latency 27 to 72 s; cheap GET up to 33.6 s | 48 x 200; chat latency 6.9 to 43.9 s (median 12.9); cheap GET up to 6.3 s |
| 30 concurrent chats | not run before the fix; first fix attempt gave 26 x 200 and 4 x 503 | 30 x 200; chat latency 16 to 64 s (median 32); cheap GET up to 6.6 s (median 0.04) |

Cause (`sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`): every request holds a database connection for its whole run, including the model call (up to 20 s), and a chat request holds one from each of two pools. The default pool was 15, so 15 concurrent model-backed requests used it all and everything behind them waited 30 s and then got a 500. The earlier load test (TR-V-10) used 10 students, below the limit.

Fix (tests in `backend/tests/test_overload.py`): both pools are sized to the server's 40 worker threads (30 + 10) with a 10 s wait; Postgres starts with `max_connections=200` to fit them; model calls in flight are capped at 16 with a 3 s wait, after which a call fails like a model outage (explanations fall back to the template, chat says the model is unavailable); an exhausted pool answers 503 with `Retry-After` instead of 500. The latency after the fix is dominated by the model providers on this PC (a local model contending for one GPU, then a fallback), not measured against the intended provider order.

## Other defect fixed

Concept hints (level 1) were served verbatim from the course notes with no leak check, so notes that held the problem's solution (an instructor's worked example) would have shown it. The hint now skips a section whose code matches the reference solution (`leak.copies_reference`) and falls back to "Review the course notes on <concept>". Tests in `test_leak_guard.py`.

## Not covered

Real students, real provider timing, phone and browser behaviour, LTI, the model-drafted problem endpoint, and long-running behaviour. The harness is LLM-driven, so action mixes differ from run to run; the seed fixes only the harness's own random choices.
