# Step 45: Open questions in the assistant (F-51, F-52)

Date: 2026-10-19. Branch `step-45-open-chat`.

## Problem

The `general` route answered only from retrieved course notes. With no matching note it replied "No course source was
found…", so greetings, arithmetic, general knowledge and study advice all failed.

## What changed

- `general` first tries the grounded answer from course notes (unchanged, with sources). When no note matches, or the
  grounded answer fails its checks, it now gives an open answer (`chat/handlers.py: open_answer`), labelled
  "General answer, not from your course notes." The old note-quote fallback is gone.
- Open answers keep the safety rules: student text and history are delimited data; while a problem is open the strict
  `leak.check` against its reference solution applies (no code blocks at all); with no problem open, a short fenced
  example (up to 25 lines) is allowed. A failed check shows a fixed refusal; a model outage shows a fixed message.
- Router prompt (`chat/routing.py`): "explain a topic" and general study advice go to `general`; anything not clearly
  about the student's own work goes to `general`. The six route labels are unchanged.
- Chat panel (`ReplyText.tsx`): renders paragraphs, bullet lists, bold, inline code and code blocks as text (no HTML,
  no new dependency).

## Measured (2026-10-19, live stack, model via Groq)

Command: `docker compose exec -T api python -m evaluation.open_chat` (20 everyday questions, one throwaway
`@eval.local` student; "answered" means the reply came from a real answer path, not a canned or misrouted reply).

| Version | Answered |
| --- | --- |
| Before (old API) | 0 of 20 (18 "No course source" replies, 2 misrouted to `explain` and `progress`) |
| After | 20 of 20 |

An intermediate run gave 19 of 20: one answer exceeded the 3000-character cap and was reported as unavailable. The cap
now cuts at a paragraph end and the prompt asks for shorter answers.

TR-V-08 routing after the prompt change: `python -m evaluation.router_eval routing` gave 49 of 50 (98%), target 90%.
The earlier result was 50 of 50. The miss is "Point me in the right direction please" (expected hint, got recommend).

Tests: 750 passed (`docker compose --profile test run --rm test`), ruff clean, `tsc --noEmit` clean. Browser check
(Playwright, 1280x900): code block, bullets and bold render, no raw `**` or fences, label shown.

## Not done / risks

- Open answers come from the model without sources and can be wrong; they are labelled. No topic filter or moderation
  was added (decision: any topic).
- On this PC the provider chain starts with `local` (qwen2.5:3b), which is not running and fails after ~4.5 s on each
  call before Groq answers. This is the `.env` order, left unchanged.
- Throwaway accounts `openchat-*@eval.local` and `uicheck-*@eval.local` remain in the dev database.
