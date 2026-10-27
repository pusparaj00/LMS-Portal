# Step 83: deterrents against copying test content (TR-S-11, TR-S-12)

Date: 2026-10-27. Added to the TRD as TR-S-11 (client deterrents) and TR-S-12 (hidden tests never leave the server).

## What a browser can and cannot do

It cannot stop a screenshot, a phone photograph or developer tools. What was built makes casual copying hard and makes a
leaked capture traceable to the student who had the page open. Nothing here is described as prevention.

## What changed

| Change | Where |
| --- | --- |
| `Protected`: question text cannot be selected, copied, cut, dragged, opened in a context menu, or printed; screen readers still read it. Staff are not restricted. | `frontend/src/pages/ProtectedContent.tsx`, `styles.css` |
| `Watermark`: a faint, click-through label with the student's name (or email) and the UTC time, refreshed every 30 s | same |
| Applied to placement questions and options, quiz prompts and options, the problem statement with its examples, and the probe question | `PlacementPage.tsx`, `QuizPage.tsx`, `ProblemPage.tsx`, `FeedbackPanel.tsx` |
| The code editor and answer boxes are outside `Protected`, so typing and pasting your own work still work | |
| `test_no_student_route_returns_a_hidden_test`: after a failed submission, the problem list and detail, run, submit, read-back, run-custom, explain, three hints, the dashboard and a chat message are scanned for the hidden input and output | `backend/tests/test_hidden_test_exposure.py` (TR-S-12) |
| Browser check | `scripts/check-test-protection.py` |

## Measured

- Browser check (Chromium through Playwright, a throwaway stack with the step-83 frontend, 2026-10-27,
  `scripts/check-test-protection.py --api http://127.0.0.1:18000/api/v1 --web http://127.0.0.1:18080 --join-code ... --course 1`):
  17 checks on the problem page and a placement question, 0 failed: text not selectable, copy, cut, dragstart and
  contextmenu prevented, watermark shows the student's email and a UTC time and ignores clicks, the question text is hidden
  under print media, and the code editor still accepted typing. The same probe run on an unprotected part of the page
  (`section.solve`) reported selectable text and no prevented events, so the checks can fail.
- Backend: the exposure test passes. Full suite and `ruff`: see the end-of-step report.

## Not covered

- Quiz pages were not opened in the browser check (no quiz in the throwaway stack); they use the same two components.
- A student can still photograph the screen, use developer tools, or turn off scripts. Reading the page source gives the
  question text the student is already allowed to see; the hidden tests are the only protected data, and they are not sent.
- The watermark carries the student's own name and is shown only to them; it is not logged or sent anywhere.
- Print hiding and blocked selection also stop legitimate uses (copying a question into a translator). If that matters, an
  instructor-level switch is the next step; it was not built.
