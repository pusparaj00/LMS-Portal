# PRD — Adaptive AI-Powered LMS

Oct 15, 2026 · @Joseph

## 1. Overview

The product is an LMS for programming courses (Python first, then C and Java) that diagnoses a brand-new student in about 10 questions, keeps a per-concept mastery vector up to date on every submission, and explains wrong answers using the course's own material.

**Problem.** Standard LMSs report scores and completion. They cannot say which concept a student is missing or why a submission failed. Adaptive systems also need interaction history before they work, so a new student gets a generic experience (the cold-start problem).

**Vision.** Every submission is evidence. The system runs the code, reads the failure, updates concept-level mastery, and tells the student what went wrong in terms of their own course material.

**Goals**

1. Cold-start diagnosis: an adaptive placement test that produces a usable mastery vector in 8 to 10 questions.
2. Execution-grounded mastery updates after every right or wrong submission.
3. Course-grounded explanations for wrong answers, followed by a probe question on the weak concept.
4. An agentic AI chat that routes each request to the right capability.
5. A credible full-stack LMS around it: roles, courses, assignments, gradebook, dashboard.

**Non-goals for this release.** Replacing Moodle feature-for-feature (core course structure, content and completion tracking are in scope from step 43; forums, quizzes and bulk administration are separate steps), mobile apps, plagiarism detection, and live proctoring.

## 2. Users

Three roles use the system, and students are the primary user.

| Role | Needs | Key actions |
| --- | --- | --- |
| Student | Know what they are weak at and get unstuck without being handed the answer | Take the placement test, solve problems, read explanations, chat with the assistant, view mastery |
| Instructor | See where the class is struggling and control the content | Create courses and problems, upload notes, set assignments, view class mastery heatmap and gradebook |
| Admin | Keep the platform running and secure | Manage users and roles, configure the LLM and sandbox limits, view audit logs |

**Primary scenario.** A new student enrolls in Python 101. They take a 10-question placement test, and the dashboard shows a mastery bar per concept. They then open a problem, submit wrong code, and see a plain explanation tied to the instructor's notes plus one short probe question on the weak concept. Their answer to the probe moves the mastery bar.

## 3. Scope

The 21 Oct review gets one complete vertical slice that works live: Python only, one course, about 35 problems. Everything else is shown as design and labelled that way.

| Capability | 21 Oct demo | Design only |
| --- | --- | --- |
| Auth, roles, course, enrollment | Yes |  |
| Question bank (Python, concept-tagged, with tests) | Yes, 30 to 40 problems | C and Java banks |
| Code editor and sandboxed execution | Yes (Python) | C and Java runtimes |
| Cold-start adaptive diagnostic | Yes, 8 to 10 items | Full multi-concept cognitive diagnosis |
| Mastery vector with live updates | Yes | AKT, NeuralCDM |
| RAG over course notes | Yes, a few notes | Large-scale ingestion |
| LLM explanation and probe question | Yes | Explanation verifier, if not finished |
| AI chat with router | Yes, 4 routes | Recommender, LMS-query route |
| Instructor dashboard | Basic class view | Advanced analytics |
| Gradebook, announcements | Basic | Full gradebook features |

**Rule for the demo.** Nothing is faked. Any module not working live is presented as a design with its status stated.

## 4. Functional requirements

Priority: P0 must work in the demo, P1 should, P2 is design only.

| ID | Requirement | Priority |
| --- | --- | --- |
| **LMS core** |  |  |
| F-01 | Register and log in with student, instructor and admin roles | P0 |
| F-02 | Instructors create courses, topics and problems; students enroll | P0 |
| F-03 | Instructors upload course notes (PDF, Markdown) for retrieval | P0 |
| F-04 | Assignments with due dates and a gradebook view | P1 |
| F-05 | Announcements | P2 |
| **Assessment and sandbox** |  |  |
| F-10 | Browser code editor with run and submit | P0 |
| F-11 | Submissions run in an isolated sandbox against hidden test cases | P0 |
| F-12 | Each run returns structured evidence: passed and failed tests, error type, runtime, timeout | P0 |
| F-13 | Every problem is tagged with one or more concepts and test cases | P0 |
| F-14 | A Run button runs the code once on input the user types and shows the output and any error; nothing is stored or graded and no test case is revealed | P1 |
| **Cold-start diagnostic** |  |  |
| F-20 | A new student gets an adaptive placement test of 8 to 10 items | P0 |
| F-21 | Item selection maximizes information about the mastery vector, starting from a population prior | P0 |
| F-22 | The test ends at a fixed length or when concept uncertainty is low enough | P1 |
| F-23 | Newly added or generated items get initial difficulty estimates from text and concept tags | P2 |
| F-24 | The placement test mixes code-tracing multiple-choice items, whose wrong options map to named misconceptions, with 2 short coding tasks | P0 |
| **Mastery model** |  |  |
| F-30 | One mastery probability per concept per student, in the range 0 to 1 | P0 |
| F-31 | Updated after every submission, with weight depending on evidence type | P0 |
| F-32 | Only the deterministic mastery service writes mastery; the LLM never does | P0 |
| F-33 | Concept prerequisite graph used to propagate evidence | P1 |
| F-34 | Every mastery change is logged with its evidence, and a 'why did my mastery change' view shows the test, error and rule behind it | P0 |
| **Feedback loop** |  |  |
| F-40 | On a wrong submission, retrieve relevant course chunks for the failing concept | P0 |
| F-41 | The LLM explains why the submission failed, citing the failure evidence and the retrieved material | P0 |
| F-42 | The system selects one probe question for the weak concept from the vetted question bank; the result updates mastery. Generated probes are later work | P0 |
| F-43 | A verifier checks every explanation before display: the cited test and line must exist in the run result, the concept must match, and the text must contain no solution code; a failed check triggers one retry, then a fallback hint | P0 |
| F-44 | Explanations never reveal the full solution; a code-leak check blocks any reply with more than a few lines of code or a close match to the reference solution | P0 |
| F-45 | Hints follow a ladder: concept hint, then location hint, then a worked example on a different problem | P0 |
| F-46 | Verified explanations are stored by failure signature (problem, failed test, error type) and reused, so the LLM runs only for new failure patterns | P1 |
| **AI chat and routing** |  |  |
| F-50 | A chat panel available on every page | P0 |
| F-51 | A router classifies each message into explain, hint, my-progress, general, recommend or LMS-query | P0 |
| F-52 | Each route calls its own tool or agent and returns a response with its sources | P0 |
| F-53 | If routing is uncertain, a rule-based fallback applies and the student can correct it | P1 |
| **Dashboards** |  |  |
| F-60 | Student dashboard: mastery per concept, recent submissions, recommended next problem | P0 |
| F-61 | Instructor dashboard: class mastery heatmap and common failure patterns | P1 |
| F-62 | Instructors review, edit and approve stored explanations and set the hint and leak policy per problem | P1 |
| F-63 | Student dashboard stats and grades page: enrolled courses, average assignment score, upcoming assignments, progress per course and every assignment score, from the student's own data only | P1 |
| F-64 | Instructor dashboard stats and course analytics: courses, students, upcoming assignments, submissions in the last 7 days, completion rate and score distribution, for the instructor's own courses only | P1 |
| F-65 | A student enrolled in a course rates the course and its instructor from 1 to 5 with an optional text review; instructors see averages and anonymous reviews for their own courses | P1 |
| F-66 | A course has ordered modules that hold ordered lesson items; only the course's instructor edits them, and each module and item can be published or kept hidden from students | P1 |
| F-67 | Lesson items are text, a link, a video link or a PDF file; text is shown as text, links must start with http:// or https://, a PDF is checked for real PDF content and downloaded as an attachment | P1 |
| F-68 | A student marks lesson items complete and sees progress per module and per course; the instructor sees a completion rate per module; erasure removes a student's completions | P1 |
| F-71 | An instructor builds a quiz of single-choice, multiple-choice and short-answer questions with an attempt limit, and publishes it; a quiz is graded automatically, a question is all-or-nothing, and the questions of a quiz that has attempts cannot be changed | P1 |
| F-72 | A student takes a published quiz of a course they are enrolled in; correct answers are never sent to the student before they submit, and afterwards only when the instructor turned review on and every assignment holding the quiz is past due | P1 |
| F-73 | An assignment can ask for handed-in work: instructions plus a file, a link or text; a student saves a draft, turns it in and can unsubmit it until the instructor has graded it; a file is a PDF, text, Python or zip file of at most 4.5 MB, checked by content, stored in the database, downloaded as an attachment and never opened or run | P1 |
| F-74 | An instructor opens each student's handed-in work on one page, enters a score and written feedback, and returns it; a student sees the score and feedback only after the return, every grade, return and view is audited, and an instructor reaches only their own course's work | P1 |
| F-75 | Quiz scores and returned manual scores count in the gradebook, the grades page, the dashboards, the assistant's LMS answers and the LTI grade send, under the same late rule as coding problems | P1 |
| F-76 | A to-review page lists, across the instructor's own courses, the work turned in and not yet graded, grouped by course and assignment with counts, and a second tab of reviewed work | P1 |
| F-77 | A student and the course's instructor exchange private comments on one piece of handed-in work; nobody else can read them | P1 |
| F-78 | A to-do page for students with Assigned, Missing and Done tabs, grouped by earlier (past due), this week, next week and later (every assignment has a due date) | P1 |
| F-79 | A calendar page shows the due dates of the signed-in user's own courses by week and month, and can be limited to one course | P2 |
| F-80 | In-app notifications (a bell with an unread count) for new announcements, returned work, new work to review, new private comments and due dates coming up; each person sees only their own; no email is sent | P1 |
| F-81 | A course has a class code and an invite link that students use to join; the instructor can reset or disable the code; a course can no longer be joined without it | P1 |
| F-82 | A People page: the instructor sees every teacher and student and can remove a student, mute a student's private comments and add a co-teacher; a student sees only the teachers and the number of classmates | P1 |
| F-83 | A course has an optional section, subject and accent colour, shown on the course cards and the course page | P2 |
| F-84 | The course page has Stream, Classwork and People tabs; classwork is grouped by topic | P1 |
| F-85 | An instructor saves an announcement as a draft or schedules it for a later time; students see it only once it is published | P1 |
| F-86 | An assignment can be given to the whole class or to selected students; a student sees and is scored on only the assignments given to them | P1 |
| F-87 | A course can group assignments into categories with weights and shows each student an overall grade from them | P1 |
| F-88 | An instructor writes reusable rubrics and scores handed-in work against one; the student sees the rubric result with the returned work | P2 |
| F-89 | An instructor overrides a student's score for an assignment in the gradebook with a reason; the change is audited and shown to the student | P2 |
| F-90 | At-risk alerts list students with the factors that triggered each alert (missing work, low mastery, falling scores, inactivity), so an alert can be explained and checked | P1 |
| F-91 | A quiz report shows, per question, how many students answered it and how many were right, so the instructor sees which questions most of the class missed | P1 |
| F-92 | A content report compares, for each lesson item, the mastery or scores of students who completed it with those who did not, labelled as an association and not as proof of effect | P2 |
| F-70 | Launch from Moodle or Canvas through LTI 1.3 so the system fits an existing LMS | P2 |

## 5. Non-functional requirements

The sandbox is the highest-risk component, because it runs untrusted student code.

| Area | Requirement |
| --- | --- |
| Sandbox security | No network access, read-only filesystem except a temp directory, non-root user, CPU, memory and wall-clock limits per run, no host mounts |
| Sandbox performance | A typical run returns within 5 s; hard timeout at 10 s |
| Diagnostic latency | Next-item selection returns in under 1 s |
| LLM latency | A verified explanation within 15 s for a new failure and within 1 s from the cache (target); the interface shows a progress state, because an explanation is shown only after the verifier passes |
| Availability | Single-node deployment through Docker Compose; sessions stored in Redis so a restart does not lose them |
| Security | Hashed passwords, JWT with expiry, role checks on every endpoint, no secrets in the repository |
| Privacy | Student code and chat history visible only to the student and their instructors; configurable LLM provider so data can stay on a local model |
| LLM safety | Prompts include only the failing evidence and retrieved chunks; the system never gives a full solution unless the instructor allows it |
| Reproducibility | Every trained model is stored with a metadata file of hyperparameters and data statistics; seeded demo data |
| Observability | Log every routed request, sandbox run and mastery update with timestamps |
| Usability | Works in current Chrome and Edge; usable at 1366 px width |

## 6. Success metrics and evaluation

The demo succeeds if the live flow works end to end and at least two of the measured claims below hold on real or simulated data. Targets are proposals for the team to confirm.

| Claim | Metric | Comparison | Target |
| --- | --- | --- | --- |
| Cold-start diagnosis is efficient | Items needed for mastery-vector error below a threshold | Adaptive vs random item selection | Adaptive needs at least 30% fewer items |
| Diagnosis is accurate | Prediction of held-out responses (AUC) and ranking of weakest concepts | Population-prior baseline | AUC above baseline by a clear margin |
| Mastery updates are sensible | Mastery rises after correct and falls after incorrect submissions; no oscillation | Simulated students with known skills | Mastery within 0.15 of true skill after 15 submissions |
| Explanations are grounded | Share of explanation claims supported by evidence or retrieved chunks | Plain LLM feedback with no retrieval | Higher grounded share, rated by 2 reviewers on 20 samples |
| Explanations help | Student rating of clarity and success on the next attempt | Plain LLM feedback | Pilot of 5 to 10 students, directional only |
| Routing works | Share of test messages sent to the right route | Hand-labelled set of 50 messages | At least 90% |
| System works | Sandbox run success, end-to-end flow completes without manual intervention |  | 10 consecutive demo runs without failure |
| Answers are never leaked | Share of replies containing a full or near-full solution | 50 adversarial help requests, plain LLM versus guarded flow | Zero leaks with the guard on |

**Data.** The existing XES3G5M results (IRT and CAT) become a baseline study on a public maths benchmark. Programming-specific claims need your own question bank and a small pilot, plus simulated students, since XES3G5M contains no code.

## 7. Demo plan and schedule

The review on 21 Oct gets a live run of the vertical slice, so integration has to start by 19 Oct.

&#91;embedded content: demo schedule · 7 workstreams, 6 days to review\]

Day 1 fixes the schema and API contracts so the three streams can work in parallel. Day 4 covers the RAG, explanation, probe and chat router. Record a backup video of the full flow on 19 Oct, in case the live LLM or network fails.

**Demo script (about 8 minutes).**

1. Log in as a new student and take the 10-question placement test.
2. Show the mastery vector appear on the dashboard.
3. Submit wrong code and show the sandbox evidence, then the grounded explanation.
4. Answer the probe question and watch the mastery bar move.
5. Ask the chat assistant a hint question and a progress question to show routing.
6. Show the instructor heatmap, then the roadmap slide for what is design-only.

## 8. Risks and assumptions

The biggest threat to the 21 Oct demo is trying to build everything. The mitigations below keep the live slice small.

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Sandbox setup takes too long | Medium | High | Start with Judge0 or a plain Docker run on day 1; keep a fallback of restricted subprocess execution for the demo machine only |
| Question bank is too small or wrong | Medium | High | Draft with an LLM, hand-check test cases, and stop at 30 problems if time runs out |
| LLM output is wrong or leaks solutions | Medium | Medium | Strict prompt with evidence and chunks only, instruction not to give full code, optional verifier |
| LLM API fails or is slow during review | Medium | High | Cache the demo explanations and keep a recorded backup video |
| Mastery model looks arbitrary | Medium | Medium | Keep it simple (Bayesian update per concept), show the update rule, and test it on simulated students |
| Cold-start claim is not supported | Medium | High | Run the adaptive vs random simulation early; report honestly if the gain is small |
| Integration bugs on day 5 | High | High | Agree API contracts on day 1 and integrate daily |
| Public disclosure before any patent filing | Low | High | Ask the IPR cell before the review; keep the demo internal |

**Assumptions.** Three team members, six working days, one LLM API key or a local model, a laptop or small server for the demo, and permission to build a Python-only course for the review.

## 9. IP and patent considerations

The full pipeline is unlikely to be patentable, because each component is established. Mapping execution evidence to mastery is not new on its own, because test-case-informed knowledge tracing for coding is already published, so it should not be the claim. The stronger candidate is the verified loop: an explanation is accepted only after deterministic checks against the sandbox result pass, and a probe question on the contested concept then feeds back into the mastery vector. A failure-signature cache of verified explanations is a possible second claim.

- A second possible claim is estimating difficulty and discrimination for newly generated items from their text and concept tags, so they can be used in selection at once.
- India's Section 3(k) excludes mathematical methods and software per se, so any claim needs a measurable technical effect, such as fewer diagnostic items for the same accuracy.
- Before the review: search Google Patents, InPASS and Espacenet, talk to the institution's IPR cell about a provisional application, and avoid public demos or publication until a filing date is secured.
- Keep dated records of design decisions and experiments from now on, since they support both the claim and the evidence.

This section is orientation only and not legal advice.

## 10. Audit of the current design

The core idea is sound and testable, but five weaknesses and gaps would have cost the product its credibility in front of reviewers or customers. Each is now fixed in the requirements table or the metrics in section 6.

| Area | Verdict | Finding | Change made |
| --- | --- | --- | --- |
| Problem choice: cold-start diagnosis | Good to go | Real, measurable, and not solved by a plain LLM chat tutor | Added misconception-tagged items to the placement test (F-24) |
| Deterministic mastery, LLM never writes state | Good to go | Auditable and cheap to test, and it protects students from LLM errors | Added a visible evidence ledger (F-34) |
| Execution evidence feeds mastery | Good, but not new | Test-case-informed knowledge tracing for coding already exists in published work | Patent and positioning shift to the verified feedback loop (section 9) |
| LLM explanation reliability | Weak | One benchmark of 45 student solutions found 37% of LLM feedback hints contained mistakes, including hallucinated issues ([Silva and Costa, 2025](https://arxiv.org/abs/2503.14630v1)) | Verifier is now P0 and runs deterministic checks (F-43) |
| Solution leakage | Weak | A 2024 review notes earlier LLM replies to student help requests almost always contained code ([Tutor Kai paper](https://arxiv.org/pdf/2403.09744)) | Code-leak check and a hint ladder (F-44, F-45) |
| Evaluation | Weak | IRT and CAT results come from simulated students drawn from the same model, and none involve programming data | Metrics now name baselines and add explanation accuracy and leak rate |
| Cost and latency | Risk | An LLM call on every failure is slow and expensive at class scale | Failure-signature cache (F-46) |
| Instructor control and adoption | Gap | Teachers need to trust, edit and fit the tool into an existing LMS | Approval workflow and LTI launch (F-62, F-70) |
| Privacy | Partly covered | Student code goes to a hosted model unless a local one is used | Local-model option is in the non-functional requirements; consent and data-protection duties need a check with the institution |

**Net assessment.** The architecture is right and the demo slice is achievable. The product is distinct only if it proves two things with numbers: that its explanations are verified, and that its diagnosis finds misconceptions in about 10 questions.

## 11. Competitive landscape

Existing platforms already offer AI explanations, adaptive difficulty and AI grading, so those features alone will not set this product apart. The right column lists only what the pages I read do not show, so check each vendor before making a public claim. Sources were checked on 15 Oct 2026.

| Platform or work | What it does, per the sources | Not shown in those sources |
| --- | --- | --- |
| Khanmigo | Socratic tutor that guides instead of giving answers, rated strongest for school maths and science ([Dupple](https://dupple.com/learn/best-ai-education-tools), [Coursebox](https://www.coursebox.ai/blog/best-ai-tutors)) | A placement diagnostic by programming misconception, or checked code feedback |
| Replit, Codecademy, freeCodeCamp | AI explains errors in plain language, asks Socratic questions and adapts explanation depth to the learner ([Metavert](https://metavert.io/industry/ai-coding-tools-for-education)) | Instructor-approved explanations, or a published accuracy check on the explanations |
| Gradescope, CodeHS | Rubric-aware AI feedback on submissions at scale, with teacher dashboards ([Metavert](https://metavert.io/industry/ai-coding-tools-for-education)) | Per-concept mastery updated from every submission |
| DataCamp | AI-native adaptive courses that adjust difficulty from performance, focused on data and AI skills ([Fast.io](https://fast.io/resources/best-ai-for-learning-2026/)) | General programming courses with instructor-owned notes |
| Coursebox AI | Private tutor grounded in an organisation's own course content, listed without source citations ([Coursebox](https://www.coursebox.ai/blog/best-ai-tutors)) | Code execution evidence behind the feedback |
| CodeHelp (research tool) | Guardrails and one-shot requests, with a warning that responses may be wrong ([CodeHelp](https://arxiv.org/pdf/2308.06921)) | Automatic verification of each response |
| Code-DKT, KCGen-KT, TIKTOC (research) | Knowledge tracing on programming code and test cases ([Code-DKT](https://arxiv.org/pdf/2206.03545), [KCGen-KT](https://arxiv.org/pdf/2502.18632)) | Tutoring feedback and a probe question that close the loop |

**What this means.** The open space is not a smarter chat tutor. It is feedback that is checked against execution evidence, a short diagnostic that names misconceptions, and tight instructor control, all in one course platform.

## 12. Differentiation and why customers should use it

The product wins on trust, not on features: every claim below has a metric, so it can be shown to a reviewer or an instructor rather than asserted.

| Differentiator | What the customer gets | Metric that proves it |
| --- | --- | --- |
| Verified feedback | Explanations that name a real failing test and line, with no invented bugs | Share of explanation claims confirmed by the run result, versus plain LLM feedback on the same 20 submissions |
| Misconception diagnosis in about 10 questions | A day-one map of what the student misunderstands, not only a score | Items needed to reach the error threshold, adaptive versus random selection |
| Never hands over the answer | Students still do the thinking, and instructors can allow it | Solution-leak rate on 50 adversarial prompts, target zero |
| Transparent mastery | Student and instructor can see why a mastery value changed | Every mastery change links to a logged test, error and rule |
| Instructor control and private deployment | Approved explanations, per-problem hint policy, and a local-model option so student code can stay on campus | Share of explanations approved by the instructor, and a full demo run on a local model |
| Lower running cost | Repeated failure patterns are answered from stored verified explanations | Share of failures served from the cache |
| Fits existing systems (design only) | Launch from Moodle or Canvas through LTI 1.3 | Not measured in the demo |

**Why each audience cares**

- Students get feedback they can trust and a next step that matches their gaps, without being given the code.
- Instructors see which misconceptions the class holds, and control what the AI may say.
- Institutions get auditable decisions and a deployment option that keeps student code in their own environment.

**What not to claim yet.** Do not claim better learning outcomes until a controlled pilot shows it. The defensible claims for the review are diagnostic efficiency, explanation accuracy and leak rate.
