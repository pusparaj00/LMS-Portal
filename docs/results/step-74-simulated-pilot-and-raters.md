# Step 74: MiroFish agent run and a stand-in LLM rater panel (2026-10-26)

Neither part involves a real person. The students are LLM personas (`qwen2.5:3b` through Ollama) and the raters are LLM
models. **G-5 (two human raters, TR-V-03) and G-6 (a pilot with real students) stay open.**

## A. Agent run against a throwaway stack

Command (docker project `lmssim`, ports 18080/18000, empty database, `python -m app.seed`; never the live stack):
`docker run --rm -v MiroFish:/mirofish:ro -v LMS-Portal:/lms:ro -v out:/out -v MiroFish/student_eval:/work:ro lms-sim python lms_agents.py --base http://host.docker.internal:18080 --students 16 --steps 22 --seed 11 --out /out/run-2026-10-26.json`
(the same parameters as step 60). Started 11:19:39 UTC, 238 s, model `qwen2.5:3b`, 471 LLM calls of which 0 failed.

| Measured | Result |
| --- | --- |
| HTTP calls | 1799: 1632 answered 2xx, 167 answered 4xx (the refusals the abuse personas provoke), 0 answered 5xx |
| Latency | median 19 ms, 95th percentile 327 ms, maximum 11,589 ms; 9 calls over 5 s (7 chat, 1 custom run, 1 never-ending reference solution) |
| Chat spam | 180 sent, 121 rate-limited |
| Explanations | 6 requested: 5 verified, 1 template fallback; none cached |
| Issues raised by the oracles | 1, severity "high", see below |
| Placement against each persona's hidden skill | mean absolute error 0.151, against 0.162 for always guessing 0.5; better than the flat guess for 6 of 16 personas; mean rank correlation 0.241 |

The one issue: a hint to a cheater persona contained fenced code (`d["z"]` raises a `KeyError`, `d.get("z")` returns `None`).
The same example is in a note chunk of the course (found in the throwaway database), so it is the course's generic dictionary
example, not the problem's solution. This is the same flag as in steps 60 and 62; the harness counts any fenced code as a
leak. I could not recover the full reply text (the harness stores 150 characters).

Reading: the persona placement result is weak (6 of 16 beat the flat guess) and agrees with step 68's finding that personas
barely vary in mastery; it says nothing about real learners. Nothing here replaces the pilot.

## B. Stand-in LLM rater panel (TR-V-03, not a human review)

`python -m evaluation.rating_sheet generate` (20 failing submissions; verified flow against a plain call to the same model,
Gemini first, order hidden) then `llm-rate` with two raters on Groq: `openai/gpt-oss-20b` (r1) and `qwen/qwen3.8-27b` (r2).
The raters see only the blinded sheet columns, never the key; Mistral and OpenAI answered 429 and OpenRouter 404, so both
raters are served by one provider (different model families, same host). Rate limits left gaps, which were filled by
re-running on the output (4 passes); no cell was guessed. Compute: `python -m evaluation.rating_sheet compute`.

| Flow | r1 correct | r2 correct | Both raters say correct |
| --- | --- | --- | --- |
| Verified flow, all 20 | 18 of 20 | 12 of 20 | 12 of 20 |
| Verified flow, the 16 where the verified explanation was shown | 14 of 16 | 12 of 16 | 12 of 16 |
| Plain LLM, 20 | 18 of 20 | 17 of 20 | 17 of 20 |

Raters agreed on 82% of the 40 explanations (kappa 0.45). Four of the 20 verified answers were the template fallback
(submissions 13, 14, 16, 20); the 20 submissions are 20 of the 21 in the sheet's list (the plain call for "Word frequency"
failed with a 429).

What this does and does not show:
- It does **not** support "the verified flow is more often correct than a plain call": on this panel the plain flow scored
  the same or higher. With n = 20, one family of generator and raters that may favour the generator's style, this is
  directional at best, and it is the opposite of what the project expects, so it is reported as found.
- The verified flow fell back to a template for 4 of 20 (20%), so a student sees a fixed text instead.
- Most verified explanations show "0 attempts" because the sheet was generated twice (the first write failed on a path error)
  and the second run was served from the stored-explanation cache; they are real verified-flow outputs from minutes earlier,
  cached, not produced in the second run.
- LLM raters could not run the code; they judged claims from the code and the run result, as the sheet asks human raters to.
