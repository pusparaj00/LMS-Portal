# Step 64: students read the notes the instructor shows (F-93)

Date 2026-10-20, branch `step-64-student-notes`.

## What changed

- Migration 0033 adds `documents.visible_to_students`, default false. Existing and new notes stay hidden until the instructor switches them on; the assistant keeps using every note.
- Instructor: a "Show these notes to students" box on upload, and a Show or Hide button on each note (`PATCH /courses/{id}/documents/{doc}`).
- Student: `GET /courses/{id}/notes` and `GET /courses/{id}/notes/{doc}` return only shown notes, for enrolled students (an instructor sees all, to check the student view). A hidden note answers 404; a student outside the course gets 403.
- A note whose code copies a problem's reference solution (`leak.copies_reference`) is refused with 409 until the instructor confirms a second time, on upload and on switching it on.
- Pages: "Notes to read" on Classwork (all) and on the stream (up to four), and a note reader that shows `## headings`, text, lists and code.
- Seed: notes imported for the first time are shown unless they copy a reference solution. Notes already in a database stay hidden until switched on.

## Checks

- `tests/test_student_notes.py`: hidden by default, shown then hidden again, the assistant's chunks survive hiding, outsiders refused, solution note needs the second confirmation (nothing saved on the refused upload), instructor sees every note.
- Access matrix and cross-course sweep extended with the three new routes; `openapi.json` regenerated (271 lines added, none removed).
- Full suite on 2026-10-20 (`docker compose --profile test run --rm test`): 1,088 passed, 1 failed (`test_openapi_file_is_frozen`, expected until the file was regenerated); after `python -m app.export_openapi > openapi.json`, `tests/test_contract.py` alone: 5 passed.
- Browser run (Playwright against a throwaway stack): the instructor switched three notes on; the student saw exactly those three on Classwork and the stream, and the reader showed the note with 4 sections. A fourth, hidden note was not listed.

## Not covered

No test of a PDF-sourced note reader; the reader shows text only. Admins cannot open the student note pages.
