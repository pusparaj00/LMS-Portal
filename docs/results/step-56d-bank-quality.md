# Step 56d: question bank and explanation quality

Date: 2026-10-19. Branch `step-56d-bank-quality` (from `step-56-pooled-model`).

## What changed

- **Tracing questions: 12 to 26.** 14 new questions, each validated in the sandbox (the marked answer is what the code
  prints; `python -m app.bank_import data/bank --dry-run`: 61 of 61 validated). Every wrong option names a misconception;
  14 new misconceptions were added (27 in all).
  - Easy (b below -0.5): 1 to 9. Medium: 9 to 14. Hard (b above 0.5): 2 to 3.
  - Concepts with a tracing question: 10 to all 12 (classes and comprehensions now have two each).
  - Two questions touch two concepts (largest-so-far: loops and conditionals; counting letters: loops and strings).
  - These are my own authored questions with prior difficulties, not measured ones; they need the human review every
    bank item carries (all 61 are "needs human review").
- **Code fences.** Statements keep the markdown fences for the model; the placement, problem and probe screens now show the
  code without them (`frontend/src/statement.ts`). Checked in the browser at 390 px: no backticks, no overflow.
- **Explanation wording check (verifier, F-43).** A new check `quoted_code_is_theirs`: code a claim quotes in backticks must
  be in the student's own program, or be a plain Python name (len, range, ValueError) or a literal. This stops a claim that
  names code the student never wrote, or spells out a fix.
  - Measured on the 21 stored explanations: 9 quote code, 1 would fail (it suggests `s[::-1]`). Stored explanations are
    verified again when they are served, so that one is simply no longer served.
  - It tightens an old rule: a claim that quotes solution code is now rejected even where the similarity guard let it
    through. The leak-policy test now uses a student program that contains the quoted lines.
  - It does not cover free-form assistant chat. A mistake such as describing `print('hello')` as "a function, not a
    class" is not checkable by a deterministic rule, so chat answers remain unverified in that respect.
- **Persona simulation** now uses only the tracing questions the persona file has answers for (the first 12), so new
  questions cannot be counted as wrong answers. Rerun on the same data it reproduces the step-56 table exactly.

## Measured (2026-10-19)

- Live placement probe on course 409 (`placement_probe2.py`), 20 questions each. Weak student: 8 easy tracing + 5 easy
  coding + 6 medium tracing + 1 medium coding (before the new bank: one easy question). Strong student: 11 medium and 3 hard
  tracing, 4 medium and 2 hard coding. Mixed student: 6 easy tracing, 8 medium tracing, 1 easy and 5 medium coding.
  Abilities +2.13, -2.52, -0.03.
- Circular simulation on the 61-item bank (`python -m simulation.run --students 500 --seed S`, test length 20): pooled
  error at 20 questions 0.222 / 0.219 / 0.222 / 0.222 (seeds 2026 to 2029, adaptive; random 0.228 to 0.231); questions saved
  against random 15% / 30% / 20% / 30%, mean 24%, the same as with 47 items. More questions of this kind change little, as the
  step-56 floor measurement predicted.
- `docker compose --profile test run --rm --build test`: 956 passed, lint clean.
- Course 19 (a second copy of the demo bank under `instructor@lms.local`) reported 13 "updated" problems on import: its
  content was older than the bank file. Both courses held only "needs human review" problems before, so no review was
  lost (checked in `backup/pre-step-56d.sql`).

## Not done

- Concept values already cannot reach 0.00 after placement (the pooled estimate, step 56); evidence from submissions still
  uses the earlier update rule, which was left alone.
