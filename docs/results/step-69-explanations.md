# Step 69: explanations that fall back to the template (G-1; TR-L-04, TR-L-12, TR-P-03)

Measured on 2026-10-25 on the live stack, through the real provider chain. Command, inside the api container:
`python -m evaluation.explain_rate` (28 wrong submissions by a throwaway `@eval.local` student: the 21 mistakes of the
rating sheet plus 7 other failures: syntax error, name error, time limit, value error, index error, empty program,
printing a word). Generation and verification run directly, so a stored explanation cannot stand in for the model.

## What the 20 October simulation said, and what is true now

G-1 said JSON validity was the main problem (`json_valid` failed 10 of 19 checks). That is no longer so: in the baseline
below `json_valid` failed once in 28 runs. The failures now are the verifier rejecting what the model says, a retry that
did not help, and one slow provider using up the whole time budget.

## Changes

1. Prompt `explain-v3`: the rules now say to quote only an expression that appears exactly in the student's code, to
   describe a change in words, and never to state a specific input or output value that the run does not show.
2. A rejected reply is retried with an instruction for each failed check (`prompt.FIXES`), for example "do not state any
   specific input or output value, describe the kind of input in words". The instructions carry no hidden test data:
   a check says that something was wrong, never what the hidden value was (tested).
3. A slow provider cannot starve the chain. The primary provider is `local` (`qwen2.5:3b` through Ollama, now running);
   on this PC it needs longer than the whole 14-second budget, so before this change every explanation ended as a
   template without a hosted provider ever being tried. Each provider now gets at most a third of the remaining budget
   (the last one gets all that is left), and one that uses its whole share goes behind the others for 30 seconds.
4. A 400 or 404 from a provider now logs the provider's own short reason (never for other statuses, because a rejected
   key's message can echo part of the key).

## Results (same 28 submissions, stored explanations bypassed)

| Run | Time (UTC) | Verified | Verified on 1st attempt | Verified when a provider answered | Retried attempts that recovered |
| --- | --- | --- | --- | --- | --- |
| Before: prompt `explain-v2` | 17:48 | 20 of 28 (71%) | 20 (71%) | 20 of 27 (74%) | 0 of 8 |
| Prompt `explain-v3` + retry instructions, slow local model still first | 17:53 | 0 of 28 | 0 | not meaningful | n/a |
| After: v3 + instructions + time shares | 18:05 | 24 of 28 (86%) | 21 (75%) | 24 of 25 (96%) | 3 of 7 |

The middle row is a real result, not a failed run: with the slow local model first, every request spent its whole
budget on it and fell back (28 of 28), which is how the slow-provider problem was found.

Failed checks, all attempts: before: `claimed_input` x6, `no_hidden_test_leak` x4, `sources_real` x2, `llm_call` x1,
`time_budget` x1, `json_valid` x1, `quoted_code_is_theirs` x1. After: `no_hidden_test_leak` x3, `llm_call` x3,
`quoted_code_is_theirs` x3, `no_code_leak` x1, `time_budget` x1; `claimed_input` and `json_valid` no longer failed.
Median 2.2 s per explanation after, 2.4 s before; the slowest were provider rate limits (12.6 s).

## What this does and does not show

- One run each on 28 cases. A difference of four verified explanations can be partly chance; the model is not
  deterministic. The most direct evidence is that retries now recover (3 of 7; 0 of 8 before).
- The verifier is unchanged: every check still has to pass. Where the model keeps quoting suggested code
  (`quoted_code_is_theirs`, 2 problems) or naming a classic edge value (`no_hidden_test_leak`, "Even or odd"), the
  student still gets the template, as designed.
- Provider health is a separate limit. In the "after" run Groq returned HTTP 429 (rate limit) three times, Mistral and
  OpenAI also 429, and OpenRouter's configured free model returns 404 ("Provider returned error"); the setting
  `LLM_MODEL_OPENROUTER` needs a model that exists. These need your decision and keys, not code.
- Measured with synthetic wrong submissions written by me, not by students.
