# Step 90: synthetic data against the first pilot data (2026-10-28)

All numbers come from read-only queries on the live database (`lms-db-1`) on 2026-10-28. "Synthetic" is the 20-student class
that `app.synthetic` creates. "Pilot" is the five accounts that registered from outside the project. Account ownership
was not verified, and some of the five may belong to the same person. **Nothing here is evidence about learning.** The pilot
has too few people for a comparison to be more than a description (G-6 stays open).

## What each group is

| | Synthetic class | Pilot |
| --- | --- | --- |
| Source | 20 accounts `synthetic-NN@synthetic.local`; simulated placement answers drawn from an ability model (`backend/app/synthetic.py`, `simulation/model.py`) | 5 accounts registered through the public link: 4 with activity, 1 without any |
| Created | 2026-10-15 to 2026-10-16 | 2026-10-18 to 2026-10-28 |
| Software version | the build of 2026-10-15 | builds of 2026-10-18 to 2026-10-28 (placement changed in between, steps 68 to 71) |
| Placement sessions | none stored; mastery was written directly as simulated answers | 5 sessions, 4 students, 4 completed |
| Code submissions | none | 6 |

Excluded from both: 6 evaluation accounts (`eval.local`), the demo student, all instructors, and 4 more accounts on the
reserved synthetic domain that are tooling (`rating-*` and 3 `demo-cache-*`). Those 4 hold all 30 hand-written wrong
submissions and 56 mastery events from the rating sheet and demo-cache runs; they are not a simulated class.

## Measured side by side

| Measure | Synthetic class (20) | Pilot (5 accounts, 4 active) |
| --- | --- | --- |
| Students with a code submission | 0 | 4 |
| Code submissions: passed / failed / error | 0 | 2 / 4 / 0 |
| Mastery events | 552 | 140 |
| Events per active student | 27.6 | 35.0 |
| Mean change in mastery per event (`p_after - p_before`) | -0.057 | -0.138 |
| Mean mastery after an event | 0.366 | 0.263 |
| Events with `correct` set | 175 of 552 (32%) | 19 of 140 (14%) |
| Evidence types, largest first | diagnostic MCQ 260, propagation 172, diagnostic code 120 | diagnostic MCQ 55, propagation 52, pooled 12, full fail 7, code "don't know" 6, diagnostic code 6, all pass 2 |
| Placement items per session | n/a | mean 12.5, range 10 to 20 |
| Correct share on placement MCQs | n/a | 0.42 |
| Code placement items answered "don't know" | n/a | 6 |
| Placement ability estimate, 4 completed sessions | n/a | -0.20, -0.79, -1.28, -1.40 (mean -0.92) |
| Explanations with stored checks | n/a | 2, both passed `final` |
| Chat message rows | 0 | 36 |
| Consent records | 0 | 6 |

## Findings

1. **The groups differ in kind, not only in size.** The synthetic class never used the interface: it has no submissions,
   no chat, no consent record, and its answers come from a model. The pilot's 2 passes in 6 submissions is how real people
   behaved.
2. **Real users scored lower than the simulation.** Mean mastery after an event was 0.263 against 0.366, and 14% of events
   had `correct` set against 32%. All 4 completed pilot placements ended below zero ability. With 4 active students this is a
   direction to check, not a result.
3. **Real students used paths the synthetic class cannot.** They answered "don't know" on code items 6 times, used chat and
   gave consent. A dashboard built on the synthetic class therefore shows a smoother and easier class than a real one.
4. **The explanation flow passed on the 2 real explanations stored.** Both passed every stored check, including
   `no_code_leak` and `no_hidden_test_leak`. Two cases is not a rate. The earlier tooling runs (30 hand-written wrong
   submissions) are covered in `step-69-explanations.md`.
5. **Mastery moved down on average in both groups** (-0.057 and -0.138 per event). I did not investigate why; the events
   include propagation events, which may lower related concepts after a miss. The sign is unexplained.

## Limits

- **n.** 4 active pilot students and 6 submissions. No interval is given because none would be informative.
- **Identity.** Some pilot accounts have similar addresses and may be one person, so distinct people could be fewer.
- **Time and version.** The groups were created under different builds, so a difference may come from the software.
- **Meaning of `correct`.** It is the flag stored on a mastery event, not the same as a passed submission.
- **No test of significance and no learning gain.** There is no post-test and no repeat session.

## What would make this a real comparison

A pilot of at least 30 students on a fixed build, placement and recheck sessions recorded, a short feedback form, and ethics
approval and privacy paperwork (G-12). The synthetic class can then be regenerated on the same build and compared on
placement items, correct share and fallback share. Earlier machine-made evidence (LLM personas, public datasets) is in
`step-74-simulated-pilot-and-raters.md` and `step-87-research-baselines.md`.

Reproduction: aggregate counts over `users`, `submissions`, `run_results`, `mastery_events`, `diagnostic_sessions`,
`explanation_checks`, `chat_messages` and `consents`, grouped by account type, through `docker exec lms-db-1 psql` on
2026-10-28. Pilot ids 10313, 10315, 10319, 10386, 10395.
