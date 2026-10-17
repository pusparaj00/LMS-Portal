# Step 31: provider order changed, chat speed measured again (TR-A-04, TR-P-03)

Date: 2026-10-17. Local Docker stack (4 CPUs, 3.7 GB for Docker; host had 0.58 GB of 7.7 GB free).

## What changed

The `gemini_pro` key has been refused (HTTP 403 and 429) since Step 28, so every model call first failed on it.
On the key owner's instruction, the order in the git-ignored `.env` is now:

- `LLM_PROVIDER=gemini`
- `LLM_FALLBACK=groq,openrouter,mistral,openai` (`gemini_pro` removed)

No code changed. Checked with `docker compose exec -T api python -c "from app.config import Settings; s=Settings(); print(s.llm_provider, s.llm_fallback)"`.

## Measurements

Command, run three times one after the other: `docker compose exec -T api python -m evaluation.load concurrent 10`.
Every run: 210 steps, 0 failed, 10 of 10 flows complete. Median / 95th percentile in seconds.

| Step | Step 30 | Run 1 (03:39 UTC) | Run 2 (03:41 UTC) | Run 3 (03:43 UTC) |
| --- | --- | --- | --- | --- |
| explanation (live, uncached) | 1.27 / 1.56 | 1.95 / 2.61 | 17.28 / 18.08 | 1.37 / 2.29 |
| hint | 0.46 / 0.80 | 15.93 / 16.66 | 0.62 / 1.28 | 0.04 / 0.07 |
| probe answer | 2.57 / 3.50 | 1.76 / 2.55 | 3.82 / 4.94 | 1.10 / 1.46 |
| chat: hint | 9.31 / 12.33 | 1.39 / 5.96 | 3.52 / 6.04 | 1.29 / 1.57 |
| chat: progress | 1.94 / 10.56 | 1.34 / 1.52 | 3.18 / 6.04 | 1.15 / 1.54 |
| wall time, all 10 students | not recorded | 36.9 | 40.9 | 16.7 |

## Reading

- **Chat is faster.** In run 3, "chat: hint" has a median of 1.29 s against 9.31 s in Step 30. The logs show calls answered by
  `gemini-3.5-flash-lite`. Two of them got a 429 and went to `groq` (`openai/gpt-oss-20b`) after a 4 s cooldown.
- **Run 1 hint, 15.9 s:** the API had just been restarted. Hints search the course notes, and the embedding model loads on first use.
  All 10 hint requests ended within 0.1 s of each other (03:39:46) and made no model call. In runs 2 and 3 the hint median was 0.62 s and 0.04 s.
  So this is a first-request warm-up cost, not something that keeps happening.
- **Run 2 explanation, 17.3 s: cause not proven.** All 10 requests ended within 1.1 s of each other and made no model call.
  The sandbox ran no jobs from 03:41:05 to 03:41:17, and the API logged nothing in that gap. Dashboard (0.59 s against 0.02 s) and heatmap
  were slow in the same run, which points to the host stalling (0.58 GB free) rather than to the explanation code. Run 3 did not repeat it.
