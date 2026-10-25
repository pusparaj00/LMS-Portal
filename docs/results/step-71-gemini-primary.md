# Step 71: Gemini Pro key first in the provider chain (G-1, TR-A-04)

Measured on 2026-10-25 on the live stack with `python -m evaluation.explain_rate` (the same 28 wrong submissions as
step 69, stored explanations bypassed, throwaway `@eval.local` student).

## The key

`GEMINI_PRO_API_KEY` (updated by the project owner) is valid. Checked without printing it: a direct call returns HTTP
200; through the app's own Gemini adapter with a JSON schema, `gemini-3.5-flash-lite` returned correct structured JSON in
6 of 6 realistic-sized calls (1.2 to 3.2 s, median 1.6 s; a cold first call took 7.5 s). `gemini-3.1-pro-preview` answers
HTTP 429 (no quota on this key), so the usable model is `gemini-3.5-flash-lite`.

## The configuration change

`.env` (not tracked): `LLM_PROVIDER=gemini_pro`, `LLM_MODEL=gemini-3.5-flash-lite`,
`LLM_FALLBACK=groq,openrouter,mistral,openai,local` (before: `local`, `qwen2.5:3b`, `groq,openrouter,mistral,openai`).
The local model stays as the last fallback. A backup of the old file was kept outside the repository.

## A mistake of mine, found by reading the logs

The first run after changing only the provider (19:42 UTC) gave 23 of 28 verified (82%) and looked like "Gemini first
changes nothing". It was not a test of Gemini: `LLM_MODEL` names the primary provider's model and was still
`qwen2.5:3b`, so the primary was `gemini_pro/qwen2.5:3b`, Google answered 404 "model not found" every time, and every
answer came from a fallback. After setting `LLM_MODEL` the chain printed as `gemini_pro/gemini-3.5-flash-lite > groq > ...`
and the run was repeated. The app now refuses to start when the primary is a Gemini provider and `LLM_MODEL` is not a
Gemini model name (`build_adapter`, tested), and `.env.example` says what `LLM_MODEL` means.

## Results (28 submissions)

| Chain, run at (UTC) | Verified | Verified on 1st attempt | Provider failures | Median / slowest seconds |
| --- | --- | --- | --- | --- |
| Step 69 "after": local first, then groq... (18:05) | 24 of 28 (86%) | 21 (75%) | 3 | 2.2 / 12.6 |
| Gemini first by mistake, really Groq first (19:42) | 23 of 28 (82%) | 21 (75%) | 3 | 1.7 / 12.5 |
| **Gemini Pro key first, correct model (19:47)** | **26 of 28 (93%)** | **23 (82%)** | **0** | **1.6 / 7.0** |

Failed checks with Gemini first: `no_hidden_test_leak` x5 (Count vowels, Palindrome check and Leap year recovered on the
second attempt; Even or odd did not) and `quoted_code_is_theirs` x2 (Grade letter, both attempts). No `llm_call`,
`time_budget`, `claimed_input` or `json_valid` failures.

## What this does and does not show

- One run per row on 28 synthetic submissions; the model is not deterministic, so two verified explanations
  (93% against 86%) can be chance. What is clear: no provider failures (the earlier chains had 3 of 28 from rate limits and a
  slow local model), faster answers, and no change to what the verifier accepts.
- The two remaining failure kinds are the verifier doing its job: the model names a classic edge value or suggests code.
- Gemini's free-tier limits were not reached in 28 calls plus the checks above; a class-size burst was not measured with
  this key.
