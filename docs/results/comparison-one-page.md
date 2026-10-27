# Comparison with existing tools (one page)

Date: 2026-10-27. Sources for the other tools are the ones listed in `docs/prd.md` section 11 (checked 15 Oct 2026); they are
not re-checked here, so confirm each vendor before a public claim. "Measured" means a number in `docs/results/` with its
command and date. Every measured result so far comes from simulated students or language-model raters, not from real students.

## What is not new (do not claim)

AI error explanations, adaptive difficulty, AI grading with rubrics, and mastery estimated from test results are all offered or
published elsewhere (Khanmigo, Replit, Codecademy, Gradescope, CodeHS, DataCamp, Code-DKT, KCGen-KT, TIKTOC).

## What this system adds

| Feature | Similar existing work | What differs here | Measured result | Still needed |
| --- | --- | --- | --- | --- |
| Verified explanations (F-43) | Replit, Codecademy, CodeHelp explain errors; CodeHelp warns they may be wrong | A claim about what the student's program prints is run in the sandbox and compared; a false claim is rejected, retried, or replaced by a template | 26 of 28 verified, median 2.0 s (2026-10-27, `evaluation.explain_rate`). Rated correct: verified 95%, plain call 95% (21 rows, 2 model raters) | Two human raters (G-5); a larger sheet, since one row is 5 points |
| Misconception placement test (F-24) | Most tools give a score or a level | Items tagged with misconceptions; stops when confident | 30% fewer questions met on 4 held-out simulator seeds (step 68) | Real students (G-6); the simulator comes from the same model family |
| Mastery written only by its own service (TR-A-02) | Chat tutors keep state in the app or the model | Separate service and database role; each change links to a logged test and rule | Built and tested; no learning claim | A pilot |
| Leak guard (F-44) | CodeHelp uses prompt rules | Structure checks, similarity to the reference, per-problem strictness | Guarded 0 of 50 leaked; plain model 44 of 50 | The similarity check never fired in that test, so it is unproven alone |
| Instructor control (F-62) | Rarely shown in the sources | Approval of stored explanations, hint and leak policy, local-model option, LTI launch | Built; no instructor study | Instructor trial |
| Stored verified explanations (F-46) | Not shown in the sources | Repeated failure patterns served from a cache of verified entries | Built; only entries with a tried example are served (step 75) | Hit rate on real classes |

## What this system does not do

- No outcome claim: nothing shows students learn more.
- Sandbox runs one job at a time: 7 of 30 students submitting in the same second got "sandbox busy" (step 80).
- Adaptive difficulty after placement is the least developed part and has no result.
- Screen capture and copying of test content cannot be blocked in a browser (step 82, planned).

## Claims the evidence supports today

1. Explanations are checked against execution evidence before a student sees them (26 of 28 verified; false traces are rejected).
2. A guarded reply contained no full solution in 50 adversarial requests.
3. On the simulator, the placement test needs about a third fewer questions. This is a simulator result only.
