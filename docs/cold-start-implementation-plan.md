# Cold-start diagnostic: implementation plan

Written 2026-10-19 on branch `step-54-placement-core`. This plan changes requirements F-20 and F-22 and adds F-25 to F-29
and TR-M-12 to TR-M-16 (section 9). Nothing in it is built yet; the build is steps 54 and 55 (section 7), started on your "go".

## 1. The problem and what "solved" means

A new student has no history here. The system cannot know which concepts they have mastered, which prerequisites they are
missing, or where to start. The goal is not to test everything; it is to collect enough evidence to make the first useful
recommendation, say honestly how sure it is, and improve with every later interaction.

There are two cold starts. A **new student** (no history) is solved by onboarding, a diagnostic and prerequisite mapping.
A **new course** (no data from other students) is solved by an expert-tagged question bank, a concept map and transparent
rules. We have both, so the design uses no collaborative filtering and no learned model that needs past students.

"Solved" means, for a student who joins a course with tagged questions:

1. They take one test of about 15 to 20 minutes built from the course's own questions, in an order that differs from other
   students', covering every concept and mixing easy, medium and hard questions.
2. They get, per concept, a mastery estimate **and** how sure the system is, how many questions it rests on, when it was
   last assessed, and a clear "not assessed yet" where there is no evidence. Low confidence asks for more evidence; it never
   labels a student weak.
3. They get a first recommendation that respects prerequisites (revise the missing basics before the concept that needs them)
   and a prompt to re-check later.
4. Every number is reproducible: the same answers give the same learner model, and the LLM never writes mastery.

Measured targets come from the PRD and TRD (reach the random test's error with at least 30% fewer questions; mastery within
0.15 of true skill after 15 submissions; a 5-question test must beat predicting the population mean). This plan adds no new
numeric target; results are reported as measured, against the old test and the baselines.

## 2. Where we are now

| Part (from the cold-start model) | What exists | Gap |
| --- | --- | --- |
| 1. Student context | Display name, academic history and interests on the account (step 40); the course the student joined | No structured background or goal; nothing sets the starting difficulty |
| 2. Curriculum and knowledge map | Concepts per course; each problem tagged to concepts with a weight; difficulty `b` and discrimination `a` per problem with a source flag (prior or estimated, F-23); misconceptions linked to wrong options | **No prerequisite graph** (F-33 is not built) |
| 3. Diagnostic engine | Cold-start test in Redis sessions; 2PL maths; ability estimate with a prior; selection by expected information gain over concept entropy; 8 multiple-choice then 2 coding items (`MAX_ITEMS = 10`) | Only 2 of 50 courses can run it, because placement questions exist only in the imported banks; the first 7 questions were identical for a strong and a weak student in a live run (2026-10-19); no "I don't know", no confidence; fixed shape |
| 4. Learner model | One `p_known` per concept and student, a `mastery_events` ledger with weights, suspected misconceptions | No uncertainty, evidence count or last-assessed shown; concepts not asked about stay at the flat 0.5 and look assessed |
| 5. Recommendation | "Next problem" picks the weakest concept's easiest unsolved problem (a SQL function); the assistant says the same | Not prerequisite-aware; no re-check |

Measured weaknesses on record (`docs/results/diagnostic.md`, 500 synthetic students, 2026-10-15; `docs/results/step-40-noncircular.md`,
50 non-circular students): after 10 questions the mastery error is 0.270 for adaptive against 0.273 for random (one question
sooner, 10% fewer, target 30%); on the non-circular students there was no gain (0%); the 5-question ability estimate beat the mean
in the circular simulation but not on the non-circular students (RMSE 0.631 against 0.542); a single ability number predicted
held-out answers better than the 12-concept vector (AUC 0.68 against 0.61). Reading: ten questions cannot measure 12 concepts one
by one, and the model ignores what answers say about the concepts not asked.

Question bank of the demo course (counted 2026-10-19): 12 multiple-choice traces (1 easy, 9 medium, 2 hard) and 35 coding tasks
(10 easy, 19 medium, 6 hard), 12 concepts; classes and comprehensions have no multiple-choice question.

## 3. Design principles

- **Evidence over self-report.** A self-described background only sets the starting point; the first few answers override it.
- **Uncertainty is part of the answer.** Every concept shows how sure the system is. Little evidence means "ask more", never "weak".
- **Deterministic and auditable.** Selection, scoring and the learner model use fixed rules and seeded randomness, are replayable
  (TR-M-09) and are logged in the evidence ledger. The LLM never writes mastery (F-32).
- **Use what the course already has.** The test is drawn from the course's own tagged questions, so any course whose teacher
  tagged problems with concepts and difficulty can run it, with no separate authoring.
- **One shape, not a long questionnaire.** No personality survey and no single overall score.

## 4. The student's path

1. **Join** with the class code (done, step 49).
2. **Background** (new): one question, "How much have you done in this subject?" with three answers (new to it, some experience,
   comfortable). It sets the starting difficulty only. Stored per course, shown on the result page, changeable.
3. **Placement test** (about 16 to 20 questions): easy, medium and hard questions, shuffled per student; each has "I don't know"
   and an optional "how sure are you?".
4. **Result page:** per-concept mastery with uncertainty, evidence count and last assessed; "not assessed yet" concepts; suspected
   misconceptions; strengths and gaps; and the first recommendation.
5. **First path** (step 55): a starting problem, prerequisite revision first where a prerequisite is weak, and the reason in words.
6. **Learn and re-check:** ordinary submissions and quizzes update the model (already working); a short re-check (3 to 5 questions)
   is offered on concepts that are still uncertain or have not been assessed for a while.

## 5. How it works

### 5.1 The question pool

The pool is every live problem of the course that has at least one concept tag and a difficulty: multiple-choice items from
the bank and coding problems. Bands by difficulty `b`: easy below -0.5, medium -0.5 to 0.5, hard above 0.5 (these are the
cut points the demo bank already falls into). Items the student has seen the worked solution for are skipped (existing rule).
Assignment problems are excluded from the pool so the test never gives away graded work.

### 5.2 Test shape and selection

- Length: at least 16 questions, at most 20; stop at 16 only if every concept has evidence and the three most uncertain
  concepts are well determined (the existing uncertainty rule, applied after the minimum).
- Type limits: at most 12 multiple-choice and at most 6 coding tasks, at most 2 hard coding tasks. A course with no
  multiple-choice questions runs on coding tasks alone, with fewer questions (the limit is what the pool supports).
- **Start** at the difficulty set by the background answer: ability prior mean -0.7 (new), 0 (some), +0.5 (comfortable), standard
  deviation unchanged. Evidence quickly outweighs it.
- **Next question** = for each allowed item, a score made of (a) a coverage bonus if one of its concepts has no evidence yet,
  (b) Fisher information at the current ability estimate (this is what moves the test up after right answers and down after wrong
  ones, so every student meets easy, medium and hard questions), and (c) expected information gain over concept uncertainty
  (the existing term). Terms are scaled to the same range and weighted; the weights start equal and are tuned in simulation.
- **Shuffling and exposure control:** among items scoring within 10% of the best, choose by a random generator seeded from the
  session, so two students with the same answers still see different questions in a different order, and one question is not
  seen by everyone.
- Per-question time is not limited; a session lasts 2 hours (existing).

### 5.3 What an answer means (initial rules, tuned in simulation)

| Answer | Evidence |
| --- | --- |
| Right, no rating or "sure" | Standard update with the evidence type's slip and guess rates (existing) |
| Right, "just guessing" | Same update with the guess rate raised, so it earns less credit |
| Wrong, no rating | Standard update; if a tagged wrong option was chosen, the misconception rises (existing) |
| Wrong, "sure" | Standard update; the misconception rises more (a confident wrong answer is stronger evidence of a misconception) |
| "I don't know" | Counted as not known with a guess rate of 0 (someone who knows does not say this); never raises a misconception |

All of this runs inside the mastery service so it stays deterministic and logged (TR-M-01, TR-M-07). The exact modifiers are
constants in one place, listed in the TRD, and changed only with a simulation result that supports the change.

### 5.4 The estimate

- **Ability:** the existing posterior-mean estimate with a prior (TR-M-10), now with the background shift.
- **Concepts with evidence:** the existing weighted Bayesian update per question.
- **Concepts without evidence:** estimated from the student's overall ability and the concept's typical item difficulty, written
  as one low-weight "inferred" piece of evidence through the mastery service and clearly marked as an estimate on the result page
  and in the "why did my mastery change" ledger. This replaces the flat 0.5 that looked like an assessment.

### 5.5 The learner model record (per student and concept)

| Field | Source |
| --- | --- |
| Mastery | `mastery.p_known` (existing) |
| Evidence count | rows of `mastery_events` for the concept with a real answer or run (not the inferred row), and the sum of their weights |
| Uncertainty | a standard-error style figure from the effective evidence: sqrt(p(1-p)/(n_eff+2)); shown as "not assessed", "low", "moderate" or "higher" confidence at fixed cut points listed in the TRD |
| Last assessed | the newest real evidence's time |
| Status | assessed (real evidence), estimated (inferred only), not assessed |
| Suspected misconceptions | existing probabilities, shown above a fixed cut |

Nothing new is stored on the `mastery` table: the extra fields are computed from the ledger, so replay keeps them consistent.

### 5.6 Prerequisites and the first path (step 55)

- A `concept_prerequisites` table (a concept and the concepts it needs), edited by the course's teachers, with a check that the
  graph has no cycle. For the demo course the starting graph follows the order the bank already uses (variables and input,
  conditionals, loops, then lists, strings and functions, then dictionaries, tuples and sets, comprehensions, exceptions,
  recursion and classes); **you confirm it before it is used** (section 10).
- **Propagation (F-33):** strong evidence on an advanced concept nudges its prerequisites up a little; weak evidence on a
  prerequisite marks the concepts that need it as "not ready" without lowering their mastery.
- **Recommendation:** choose the concept to work on as the not-ready-free concept with the lowest mastery or the highest
  uncertainty; if its prerequisite is weak, recommend that revision first and say why ("Because loops (36%) comes before lists").
  The assistant's recommend route and the dashboard use the same rule, so they cannot disagree.
- **Re-check:** a 3 to 5 question mode of the same engine, offered after ten submissions in a concept or two weeks, aimed at
  concepts that are uncertain or old; its answers update the model like any evidence.

### 5.7 Data and interface changes

- Migration: `enrollments.background` (new, some, comfortable; null until answered). Step 55 adds `concept_prerequisites`.
- API: `POST /diagnostic/start` takes the background; `POST /diagnostic/answer` takes `dont_know` and an optional `confidence`
  (`guessing`, `fairly`, `sure`); the result carries the per-concept record above and the first recommendation; a re-check mode.
- Mastery service: the answer endpoint takes confidence and the "don't know" flag; a new endpoint writes the inferred evidence.
- Screens: background choice before the first question; "I don't know" and the optional confidence control on each question; a
  progress bar that does not show the difficulty; the result page with the table, the not-assessed list and the first path.
- Students never see the answer key or which band a question is in. After the test they see the misconceptions their wrong
  picks suggest and which concepts to revisit, not the correct options (the same questions are reused).

### 5.8 Privacy and fairness

The background answer is self-reported course-level data about the student, so the privacy notice gets a new version and every
student is asked to accept again. It is used only to start the test and is shown back to the student. Nothing about it goes to a
language model. A question bank that is thin or badly tagged gives uncertain results; the result page says so, and the teacher's
class view shows which concepts had little evidence.

## 6. What stays as it is

The 2PL maths, the Bayesian update, the misconception links, the ledger, the idempotent replay, the Redis sessions, the rate
limits, the verifier and explanation rules, the hint ladder and the quiz and assignment features are unchanged.

## 7. Build order

**Step 54: the placement test and the learner model** (F-20, F-22, F-25 to F-28, TR-M-12 to TR-M-15)

| Part | Work | Done when |
| --- | --- | --- |
| 54a | PRD and TRD rows; migration for `background` | the documents and schema agree |
| 54b | Pool, bands and constraints in `selection.py`; coverage, information and gain scoring; seeded shuffling; length and stop rules | unit tests: every concept gets evidence when the pool allows; easy, medium and hard all appear; two sessions with the same answers differ in order; the limits hold |
| 54c | Answer rules (don't know, confidence) in the mastery service | tests of each row of the table in 5.3, with replay giving the same vector |
| 54d | Inferred evidence for concepts without evidence | a concept never asked about is marked estimated, not assessed; replay stable |
| 54e | Per-concept record (mastery, uncertainty, evidence count, last assessed, status) in the API and the dashboard | the record matches a hand calculation on a fixed ledger |
| 54f | Screens: background, don't know, confidence, result page | a real browser run as a student, including a 390 px phone width |
| 54g | Evaluation: rerun both simulations with the new policy | the old and new numbers side by side in `docs/results/` |

Gate: tests pass; a strong student's final ability is above a weak student's in the same course on every seed tested; the test
runs in a teacher-created course with only coding problems; the numbers of 54g are reported as measured, including if a target is
still not met.

**Step 55: prerequisites, the first path and the re-check** (F-29, F-33, TR-M-16): migration, teacher editing of prerequisites,
propagation, the prerequisite-aware recommendation shared by the dashboard and the assistant, and the re-check mode.
Gate: the recommendation puts a weak prerequisite before the concept that needs it, in a test with a fixed ledger; the assistant
and the dashboard return the same recommendation; a cycle is refused.

**The review on Wed 21 Oct.** The plan's feature freeze was Mon 19 Oct. If the review needs a demo of this, the smallest
useful cut is 54a, 54b, 54c and 54f (shuffled, banded, longer test with "I don't know"), which does not need the model display
or prerequisites. Everything after that follows in order.

## 8. How we will know it works

- **Simulation** (`python -m simulation.run --students 500 --seed 2026` and the 50 non-circular students): mastery error and
  coverage at 10, 16 and 20 questions for the old test, the new test, random order, BKT and the ability-only baseline; held-out
  AUC and calibration; the 5-question sanity test; the number of distinct question orders in 500 sessions. The students are
  synthetic, so these show the engine is sound, not that real students will do better.
- **Tests:** the rows in 7, plus role and access tests for the new fields and endpoints, and the erasure test for any new rows.
- **Not measurable without people:** whether students finish the test, how long it takes them, whether teachers find the first
  recommendation sensible. Those need real students and teachers (the ratings still waiting after the review) and are listed as
  open, not claimed.

## 9. Requirements to add

PRD (F-20 and F-22 revised, F-25 to F-29 new):

- F-20: a new student gets an adaptive placement test of 16 to 20 questions of three difficulty levels.
- F-22: the test ends at 20 questions, or from 16 when every concept has evidence and the remaining uncertainty is low.
- F-25: placement is built from the course's own tagged questions, the same for every student, in a different order for each.
- F-26: a short background answer sets the starting difficulty only.
- F-27: every question allows "I don't know" and an optional confidence; both change how the answer counts.
- F-28: the learner model shows mastery, uncertainty, evidence count, last assessed and "not assessed yet"; concepts without
  evidence are estimated from the overall level and marked as estimates.
- F-29: teachers set concept prerequisites; the first recommendation revises a weak prerequisite first; a short re-check follows learning.

TRD (new): TR-M-12 selection (coverage, information, gain, seeded exposure control, type limits); TR-M-13 the answer rules
of 5.3 as constants in one place; TR-M-14 inferred evidence and its marking; TR-M-15 the learner-model record and its cut points
computed from the ledger; TR-M-16 prerequisites without cycles and prerequisite-aware recommendation.

## 10. Decisions for you

1. Test length: 16 to 20 questions (15 to 20 minutes).
2. Up to 6 coding tasks inside the test (needed because the bank has one easy multiple-choice question).
3. The optional "how sure are you?" step.
4. The starting prerequisite graph for the Python course (section 5.6), which you confirm before it is used.
5. Whether to show the correct answers after the test (I recommend not, because the questions are reused).
6. Whether this goes ahead before the review or after it (section 7).

## 11. Risks

- Coding tasks in the placement test load the sandbox (up to 6 per student); the existing queue limit and rate limits apply.
- With 16 to 20 questions on 12 concepts, many concepts rest on one or two questions; the design shows that instead of hiding it.
- A weight or modifier chosen without data can mislead; they are constants changed only against simulation results.
- Prerequisite data is a teaching judgement, not a measurement; a wrong graph gives a wrong first path, which is why a teacher
  confirms it.
- The simulations use synthetic students; a gain there is not proof of a gain with real students.
