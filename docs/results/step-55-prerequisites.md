# Step 55: prerequisites, the first path and the re-check (F-29, F-33, TR-M-17)

Date: 2026-10-19. Branch `step-55-prerequisites` (from `step-56d-bank-quality`).

## What changed

- **Teachers edit prerequisites.** `PUT /courses/{id}/concepts/{concept_id}/prerequisites` sets the concepts a concept
  builds on (`concepts.parent_ids`, already filled for the demo course). It refuses a concept of another course (422), a
  self-link (422) and any circle, direct or through other concepts (409, `app/concept_graph.py`); only the course's
  teachers may call it; the change is written to the audit log. The settings page has a "Builds on" list per concept.
  Deleting a concept already removed it from other concepts' prerequisites.
- **One recommendation rule.** The database function `next_step` (migration 0032) walks the student's concepts from the
  weakest. If the concept builds on a prerequisite, at any depth, that the student has not mastered (below 0.5), the weakest
  such prerequisite that still has an unsolved coding problem is recommended instead, and the reason names the concept that
  needs it. The dashboard and the assistant both call it, so they cannot disagree (`app/recommend.py`). With no weak
  prerequisite the answer is the earlier "weakest area" rule.
- **Re-check.** `POST /diagnostic/start` with `mode: "recheck"` asks 4 questions on the concepts with the oldest or least
  evidence, from the same bank and the same selection engine. Its answers are ordinary ledger evidence; it does not write a
  new placement estimate and does not count as taking the placement. The dashboard offers it (`recheck_due`) 14 days after the
  last placement or re-check answers, or after 10 submissions since then.
- F-33 (drops in a concept are passed back to its prerequisites) was already built in the mastery service and is unchanged;
  the extra idea in the plan, that strong evidence nudges prerequisites up, was not built.

## Measured (2026-10-19)

- 12 new tests: the cycle check, who may edit, refused edits leave the graph unchanged, a weak prerequisite first
  (fixed ledger), the deepest weak prerequisite chosen, a strong or exhausted prerequisite skipped, the assistant and the
  dashboard returning the same problem and reason, and the re-check offer, length, ledger rows and independence from the
  placement. Full suite in CI on the pushed branch: passed, lint clean (CI run on `bd26d40`).
- Live on the demo course (409), an all-wrong eval student: both the dashboard and the assistant say "variables io (8%) comes
  before conditionals, which builds on it, so revise it first" for "Sum of two numbers". The re-check asked 4 questions.
- Browser at 390 px: editing "Builds on", the circle refused with a message, no horizontal overflow.

## Limits

- The 0.5 "not ready" cut-off, the 4 questions, 14 days and 10 submissions are my choices, not measured; they are constants in
  `0032_next_step.py` and `routers/diagnostic.py`.
- Prerequisite data is a teaching judgement. A wrong graph gives a wrong first path.
- Re-check concepts are chosen from the ledger's evidence times only; it does not look at how well the concept is mastered.
