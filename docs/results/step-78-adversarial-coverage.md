# Step 78: a larger adversarial agent run (G-18, TR-V-04, TR-S-02)

Date: 2026-10-26, on the throwaway stack (docker project `lmssim`, ports 18080/18000, fresh seed; never the live stack),
code of branch `step-77-production-hardening`. LLM personas on `qwen2.5:3b` through Ollama, so the students are synthetic.

Command (MiroFish harness, outside this repository; started 15:49:02 UTC, 2171 s by the harness):
`docker run --rm -v MiroFish:/mirofish:ro -v LMS-Portal:/lms:ro -v out:/out -v MiroFish/student_eval:/work:ro lms-sim python lms_agents.py --base http://host.docker.internal:18080 --students 32 --steps 30 --seed 21 --out /out/run2-2026-10-26.json`

## Result

| Measured | Step 60/74 run (16 students x 22 steps) | This run (32 students x 30 steps) |
| --- | --- | --- |
| HTTP calls | 1799 (0 answered 5xx) | 3896: 3638 2xx, 258 4xx, **0 answered 5xx** |
| LLM calls / failed | 471 / 0 | 1200 / 0 |
| Escalation tries (staff routes) | 4 | 6 |
| Other students' work (IDOR) | not counted | 5 |
| Prompt-injection attempts | 1 | 7 |
| Oversized submissions | 3 | 4 |
| Chat spam bursts (messages sent / rate-limited) | 3 (180 / 121) | 5 (300 / 155) |
| Requests for the full solution counted by the harness | 0 recorded | 1 |
| Replies checked for leaked solutions (explanations / hints / chat) | 6 / 15 / 2 | 35 / 34 / 12 |
| Issues raised | 1 | 14 (below) |
| Placement error against hidden skill vs always guessing 0.5 | 0.151 vs 0.162, better for 6 of 16 | 0.152 vs 0.174, better for 18 of 32 |

No refusal that should have been allowed, no success that should have been refused, no 5xx, no mastery outside 0 to 1, and no
mastery moved by a chat message.

## The 14 issues

- **3 "high" solution-leak flags** (hints for students 16, 25 and 28). The harness flags any fenced code. Each is the course
  notes' generic example (`if`/`elif`, `for x in xs:` with `xs[a:b]`), not a problem's reference solution: the same
  category as in steps 60 and 62, now 3 of 81 replies checked. The reply texts are cut to 150 characters in the harness
  output, so I read the beginning of each only.
- **11 "low" slow chat calls.** Six took 40.0 to 51.7 s, which is two or three model calls at the 20 s budget each, with
  Gemini answering in 16 to 23 s (see below) and every provider after it failing or slow. The other five (592, 603, 807, 809,
  809 s) are not application time: this PC went into Windows Modern Standby from 21:23:39 to 21:33:25 and from 21:39:47 to
  21:53:23 local, which are the two windows in which the API log is silent (15:53:50 to 16:03:32 UTC and 16:10:11 to
  16:23:29 UTC, no `GET /health` either). The calls completed with status 200 after wake-up.

## Explanations during this run

35 explanations were requested: 6 verified, 1 served from the stored-explanation cache, **28 template fallbacks (80%)**.
The primary model took 16 to 23 s for a one-word reply, against a 1.6 s median on 2026-10-25 (checked directly:
`gemini-3.5-flash-lite` 16.4 s and 21.0 s, `gemini-3.1-flash-lite` 22.8 s, the network path 0.23 s), so most attempts ran out
of the 14 s explanation budget and fell through slow or rate-limited providers. This run therefore says nothing about the
verified rate; it does show that when the model is too slow the student gets the category template, never an unchecked text.

## What is still thin

Requests for the full solution are barely exercised (1 counted, although the cheater personas are meant to ask four ways),
the personas run on a 3B model, and every run is one seed. Longer runs with a stronger persona model remain the way to
widen this; none of it replaces the pilot.
