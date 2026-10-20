# Feature walkthrough video, 2026-10-20

File: `docs/demo/lms-walkthrough-2026-10-20.webm` (7 minutes, 1366 x 768, VP9, no sound; captions are drawn on the screen). It plays in Chrome, Edge, Firefox and VLC. The file is about 37 MB, so `docs/demo/*.webm` is git-ignored; remove that line in `.gitignore` if you want it in the repository.

## How it was made

A script (Playwright, Chromium) clicked through the real interface of a freshly built and freshly seeded copy of the system (branch `step-59-audit`, a separate Docker project on port 18080, its own empty database, then `python -m app.seed`). Nothing in the video is mocked: every screen shows live data from that run, the code in the editor ran in the sandbox, and the model replies came from the configured providers (the local provider was not installed, so the log shows it failing over to Groq). The script is not in the repository. The time column is approximate (about 2 seconds either way).

## What is real and what is synthetic

- The 20 other students in the class heatmap, analytics and insight screens are the labelled synthetic demo students from the seed. The student who registers, takes the placement test and hands in work is a real new account made during the run (`recorder-student@eval.local`); the instructor and admin accounts are the seeded demo account and one made for the recording.
- The placement answers were chosen by the script (a mix of right, wrong, "fairly sure" and "I don't know"), not by a person, so the resulting mastery values describe the script's answers.
- The explanation for the failed submission was the template hint, not a model explanation: the verifier rejected the model's text twice (`no_hidden_test_leak`: the text repeated hidden test data) and the system showed its fallback. That is the designed behaviour, and it is what happened.

## Scenes

| Time | Role | What is shown |
| --- | --- | --- |
| 0:01 | Admin | Administrator walkthrough: account management and an overview of every course |
| 0:09 | Admin | Users: counts by role, search, role changes, password resets and disabling accounts |
| 0:15 | Admin | Search narrows the list. Synthetic demo students are left out of this table |
| 0:19 | Admin | Staff accounts (instructors, admins) are created here with a temporary password; students register themselves |
| 0:23 | Admin | All courses on the system, opened read-only for oversight |
| 0:28 | Admin | Admins can see the class views but cannot create courses or problems |
| 0:33 | Instructor | Instructor walkthrough: build a course, assess, and watch the class |
| 0:40 | Instructor | Dashboard: courses, students, upcoming assignments and submissions in one place |
| 0:45 | Instructor | The course Stream: announcements for the class |
| 0:54 | Instructor | Announcements can post now, be saved as a draft, or be scheduled |
| 1:00 | Instructor | Course settings: a class code and invite link (reset or close any time), concepts and their prerequisites |
| 1:07 | Instructor | Classwork: the validated question bank, each problem tagged with a concept |
| 1:13 | Instructor | Content: modules of lessons (text, links, video links, PDFs), hidden until published |
| 1:26 | Instructor | A module with a published lesson: students see their progress through it |
| 1:29 | Instructor | Quizzes: single-choice, multiple-choice and short answer, graded automatically |
| 1:39 | Instructor | Rubrics: reusable criteria for grading handed-in work |
| 1:49 | Instructor | Assignments: choose problems, a quiz or handed-in work, with a due date and category |
| 1:57 | Instructor | An assignment can ask for handed-in work (file, link or text), scored by hand or against a rubric |
| 2:05 | Instructor | Course notes: the explanations and the assistant draw on these and cite them |
| 2:09 | Instructor | Class overview: a mastery heatmap by student and concept (20 synthetic demo students, labelled) |
| 2:14 | Instructor | Analytics: completion, score distribution, progress per assignment and ratings |
| 2:18 | Instructor | Insight: students who may need help, each with the facts behind the alert |
| 2:25 | Instructor | People: teachers and students, co-teachers, muting private comments, removing students |
| 2:29 | Instructor | Gradebook: weighted grade categories, scores per student and CSV export |
| 2:33 | Instructor | Calendar of due dates across courses |
| 2:37 | Student | Student walkthrough: register, join with the class code, take the placement test, solve problems |
| 2:40 | Student | A new student creates an account (students register themselves; staff accounts are made by an admin) |
| 2:46 | Student | First login: the privacy notice. Nothing is processed until the student agrees and confirms they are an adult |
| 2:55 | Student | Join a class with the code the instructor shares |
| 3:00 | Student | Student dashboard: courses, scores, next due and the weakest concepts |
| 3:04 | Student | Placement test: 16 to 20 adaptive questions; I don't know is allowed and confidence is optional |
| 3:14 | Student | Each answer updates a mastery estimate per concept; wrong options map to named misconceptions |
| 3:40 | Student | The result: mastery and confidence per concept, and suspected misconceptions |
| 3:46 | Student | My progress: mastery per concept with how sure the system is and when it was last assessed |
| 3:50 | Student | Classwork: lessons, assignments, quizzes and the problem list with status |
| 3:55 | Student | A coding problem: editor, examples, a Run box for your own input, and Submit |
| 4:05 | Student | Run executes the code once in an isolated sandbox on the typed input; nothing is graded or stored |
| 4:11 | Student | Submit runs hidden tests in the sandbox: pass or fail per category, never the hidden inputs |
| 4:15 | Student | The explanation is checked by a verifier (cited test and line, no solution code) before it is shown, else a template hint |
| 4:26 | Student | Hints follow a ladder: a concept hint, then a location hint, then a worked example on a different problem |
| 4:34 | Student | The assistant routes each message (explain, hint, progress, next step, deadlines) and never gives a full solution |
| 4:47 | Student | Fixing the code and submitting again |
| 4:56 | Student | A corrected submission passes; the mastery estimate for the concept is updated by the mastery service |
| 5:00 | Student | My progress again: the why-did-my-mastery-change history shows the test and rule behind each change |
| 5:04 | Student | Back in Classwork: a quiz and an assignment that asks for handed-in work |
| 5:08 | Student | Quizzes are graded automatically; the right answers are never sent before the student submits |
| 5:16 | Student | Opening the handed-in work assignment |
| 5:19 | Student | The rubric is shown up front. The student saves a draft, turns it in, and can message the instructor privately |
| 5:34 | Student | To-do: assigned, missing and done work grouped by due date |
| 5:38 | Student | Grades: every score and the overall weighted grade for the course |
| 5:42 | Student | Calendar: due dates for the student's own courses |
| 5:46 | Student | Account: profile and password. The profile is never sent to the AI model |
| 5:51 | Instructor | Back as the instructor: grading the work the student just handed in |
| 5:58 | Instructor | In-app notification: new work to review (no email is sent) |
| 6:06 | Instructor | To review: handed-in work waiting for a score across all of the instructor's courses |
| 6:12 | Instructor | Score against the rubric: one level per criterion, plus written feedback. Every view and grade is audited |
| 6:24 | Instructor | The student sees the score and feedback only after the instructor returns the work |
| 6:27 | Instructor | The gradebook now includes the manual score, with the same late rule as coding problems |
| 6:37 | Student | The student is notified and sees the returned score, rubric result and feedback |
| 6:45 | Student | Classwork shows the assignment as scored |
| 6:51 | Student | The returned work: score, the rubric levels the instructor chose, and written feedback |
| 6:55 | Student | Grades now show the quiz score, the problem score and the returned hand-in |
| 7:00 | Lms | End of the walkthrough: admin, instructor and student flows on a freshly seeded system |

## Not shown in the video

Login rate limits and lockout, erasure and retention, the audit trail, LTI launch and grade send-back (needs a Moodle), co-teachers and muting, scheduled and draft announcements being used, grade categories with weights and score overrides, CSV exports, PDF notes upload, problem editing and model-drafted problems, the per-problem hint policy, the review of stored explanations, quiz reports, the phone-width layout, and the course rating form. These are covered by the automated tests and the earlier results files, not by this recording.
