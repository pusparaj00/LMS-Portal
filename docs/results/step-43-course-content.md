# Step 43: Course content structure (F-66, F-67, F-68)

Date: 2026-10-19. Branch `step-43-course-content`, from `step-42-run-custom-input`. First of the traditional-LMS areas the user
chose (content structure, quizzes and manual grading, discussion and notifications, admin tools).

## What was built

| ID | Change |
| --- | --- |
| F-66 | Migration 0024 `modules`, `content_items`, `item_completions`; `GET /courses/{id}/content`, module and item create, edit, delete and move endpoints; modules start hidden, items start visible; students see only published modules and items; only the course's own instructor edits |
| F-67 | Item kinds text, link, video link and PDF. Links must match `^https?://` with no spaces (checked in the API and by a database constraint); text is shown as text; a PDF must start with `%PDF-`, is at most 4.5 MB, is stored in the database, and is downloaded as an attachment with `nosniff` and a cleaned file name. Videos are links that open in a new tab (`rel="noopener noreferrer"`); nothing is embedded |
| F-68 | `PUT` and `DELETE /courses/{id}/items/{item}/completion` (students); per-module and course progress for students; completion rate per module for the instructor; content progress on the student dashboard card; erasure deletes a student's completions |

UI: a Course content section on the course page (student and instructor), an authoring page at `#/course/{id}/content` (add, rename, hide or show, reorder with Up/Down, edit, delete), and a Content menu link for instructors.
No new dependency. Lesson uploads have their own request limit (6.2 MB); the notes upload limit is unchanged (6.0 MB).

## Measured (2026-10-19)

| Check | Command | Result |
| --- | --- | --- |
| Full backend suite, first run | `docker compose --profile test run --rm test` | 742 passed, 1 failed in 277.08 s. The failure (`test_only_the_notes_upload_accepts_a_large_body`) showed that my shared upload limit had loosened the notes upload; I gave the notes upload its old limit back |
| After the fix | `ruff check . && pytest -q tests/test_course_content.py tests/test_notes_upload.py tests/test_limits.py tests/test_contract.py` | 59 passed; the full suite was not run again |
| New tests | `tests/test_course_content.py` | 28 tests: visibility, order, link and PDF checks, completions, rates, isolation, deletion, upload limit |
| Frontend | `npm run build` | built, no type errors |
| Migration | app database | `0024` |
| Browser | Playwright, Chromium 1366 px, live stack | an instructor added a module with text, link and PDF through the editor; the student did not see it while it was a draft, saw it after it was published; `<script>` in text was shown as text; the link had `target=_blank` and `rel=noopener noreferrer`; two items ticked gave "2 of 3 items complete"; the PDF downloaded as `lesson.pdf`; the instructor saw 66.7% of the class done; no console errors |

The throwaway accounts and course used for the browser check were deleted afterwards.

## Not done

Drag-and-drop ordering, rich text or Markdown, video upload or embeds, files other than PDF, and prerequisites between modules.
