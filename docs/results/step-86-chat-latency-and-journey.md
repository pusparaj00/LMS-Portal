# Step 86: chat routing budget, end-to-end journey, verifier fallbacks (F-50, TR-P-03, TR-L-04, F-52, F-42, F-29)

Date: 2026-10-27. Throwaway stack `lmssim` rebuilt from the working tree of branch `step-86-chat-latency`; provider chain as
configured (Gemini first, then groq, mistral, openai, local).

## 1. Routing budget (F-50, TR-P-03)

`classify` now runs the routing call under `ROUTER_BUDGET_S` (default 3 s); past it the keyword rules route.

    docker exec lmssim-api-1 python -m evaluation.chat_latency 3 12

| Message | Route | How routed | Median s | Max s |
| --- | --- | --- | --- | --- |
| hint, clear phrase | hint | shortcut | 0.02 | 0.37 |
| hint, no clear phrase | hint | keyword/llm | 3.05 | 3.18 |
| progress, clear phrase | progress | shortcut | 0.02 | 0.02 |
| progress, no clear phrase | general/progress | keyword/llm | 2.31 | 7.36 |
| explain, clear phrase | explain | shortcut | 0.02 | 0.04 |
| explain, no clear phrase | explain | llm | 1.33 | 1.91 |
| recommend, no clear phrase | general/recommend | keyword/llm | 4.62 | 12.41 |
| general (model answers) | explain/general | llm | 9.15 | 27.82 |

With 12 students at once the model-answered row had median 9.32 s and maximum 15.64 s. The slowest rows are the ones whose
answer is a model call (up to the 20 s `LLM_BUDGET_S` plus the 3 s routing budget). Cost of the budget: when routing runs
out of time the keyword rules decide, so "progress, no clear phrase" and "recommend, no clear phrase" were sometimes
routed `general`. There is no run of the same command before the change, so no before/after claim is made.

## 2. End-to-end journey (F-52, F-42, F-29)

    docker exec lmssim-api-1 python -m evaluation.journey

One new student: placement (20 questions, 12 concepts), recommendation, a failing submission with a mastery change, hints
1 to 3, explanation, probe answer with a next problem, four chat messages (including an injection attempt). All 15 steps
passed. The explanation in this run came from the stored cache (`cached=True`), so the live model path is covered by
section 3, not by this run.

## 3. Verifier fallbacks (TR-L-04, TR-L-05)

    docker exec lmssim-api-1 python -m evaluation.explain_rate

24 of 28 verified (86%), 23 on the first attempt, 0 fallbacks from provider failure, median 2.6 s, max 10.3 s (step 79:
26 of 28 on a different day). The four fallbacks: Count vowels, Palindrome check and Leap year failed
`no_hidden_test_leak`; Grade letter failed `quoted_code_is_theirs` (quoted `>=`, which is not in the student's code).
Reproducing three of them showed the model chose a hidden test input as its worked example (`Racecar`, `1900`), which the
prompt forbids. The checks are working as designed; the model ignored the instruction. `MAX_ATTEMPTS = 2` is fixed by
TR-L-04 and TR-P-08, so it was not changed.
