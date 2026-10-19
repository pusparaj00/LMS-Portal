# Step 54: the cold-start placement test and the learner model

Date: 2026-10-19. Branch `step-54-placement-core`. Plan: `docs/cold-start-implementation-plan.md`.

## What changed

- The test is built from the course's own live, concept-tagged problems (not assignment problems, not worked examples the
  student has seen), so any course with tagged problems can run it, including a teacher-made course with only coding
  problems (F-25). 16 to 20 questions, at most 14 tracing, 6 coding, 2 hard coding; tracing first (4 warm-up questions).
- Each next question is scored by concept coverage, Fisher information at the current ability estimate and expected
  information gain; one of the questions within 10% of the best is chosen by a generator seeded from the session, so
  students meet different questions in a different order (F-20, TR-M-13). The answers move the next question up or down.
- Optional background answer (new, some, comfortable) sets the starting ability only (F-26); "I don't know" and an
  optional confidence rating on tracing questions change how an answer counts (F-27, TR-M-14).
- Concepts the test never asked about get one low-weight estimate row from the student's overall ability, replayable and
  marked as an estimate (TR-M-15). Only the mastery service writes it.
- The learner model gives, per concept, mastery, confidence, number of answers, last assessed, and status
  assessed / estimated / not assessed (F-28, TR-M-16); the result page and the dashboard show it, and the "why" view
  explains the new ledger rows.
- Placement prompts only show when the course has usable questions. Privacy notice is now v6 (everyone is asked again).
- Migration 0031: `enrollments.background`, `mastery_events.evidence_value`.

## Measured

- `docker compose --profile test run --rm --build test`: 943 passed, lint clean (2026-10-19).
- Live probe on course 409 (demo bank), three students: strong ability +2.00, weak -1.90, mixed -0.45; 18 questions each,
  three different question orders, all three difficulty bands used, all 12 concepts assessed (command: `placement_probe2.py`
  run inside the api container).
- Phone width 390 px: no horizontal overflow on the intro, question and result pages; no difficulty shown; no correct
  answers shown; 18 answers completed in the browser; 12 evidence notes on the result.
- Simulation: see `docs/results/step-54-placement-simulation.md`. Coverage and ranking improved; the 30% saving (TR-V-05) and
  the persona 5-question test (TR-V-06) are still not met.

## Open issues

- The demo bank has 1 easy tracing question and 12 tracing questions in all, so a weak student gets few easy tracing
  questions; more easy questions need authoring.
- Bank statements contain markdown code fences that show as literal backticks in the question.
- An all-wrong student ends with several concepts at 0.00; the update rule is unchanged from earlier steps.
- Rates for confidence and "I don't know" are starting values and are not covered by the simulation.
