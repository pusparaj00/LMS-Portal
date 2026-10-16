# Step 17 results: announcements (F-05)

All runs on 2026-10-16 on the dev stack, branch `step-17-announcements`. The PRD lists F-05 as "Announcements" (P2,
basic); nothing else defines it.

## What was built

- **Data:** `announcements` (migration 0014) holds the course, author, title (1 to 200 characters), body (1 to 5,000),
  and created and edited times.
- **Endpoints:** `GET /courses/{id}/announcements` for any course member, newest first. `POST`, `PUT` and
  `DELETE /courses/{id}/announcements/{aid}` for the course's teacher only. An announcement can only be changed through
  its own course.
- **Plain text only.** Line breaks are kept, and nothing is rendered as HTML, so text that looks like markup is shown
  as typed. No new library.
- **Course page:** an Announcements section, latest three plus "Show all", with "edited <time>" after a change. The
  teacher gets post, edit and delete.
- **Not included:** no read tracking (nothing new stored about students), no email, no scheduling, no Moodle sync.
- **Also fixed:**
  - The teacher's row of course buttons overflowed a 390 px screen by 158 px, since Step 14 added two buttons. Action
    rows now wrap.
  - README and `.env.example` now give the Windows PowerShell form of the key command (`>>` there writes UTF-16 and
    breaks `.env`).

## Tests

`docker compose --profile test run --rm --build test`: **584 passed**, ruff clean. `backend/tests/test_announcements.py`
has 11 tests:
- **Lifecycle:** post, edit (edited time set, created time kept), delete (a second delete gives 404), newest first,
  line breaks kept.
- **Validation (7 cases):** empty, blank and over-long titles and bodies, and a NUL byte.
- **Text as typed:** markup-like text is stored exactly as typed.
- **Access:** a student and another teacher cannot write; an outsider cannot read; anonymous gets 401; an enrolled
  student can read.
- **Ownership:** an announcement cannot be changed through another course.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, with throwaway `@eval.local` accounts:
1. The teacher posted four announcements through the form. One was titled `<i>Week N</i> news` with the body
   `Line one <script>alert(1)</script>` / `Line two <b>bold</b> <img src=x onerror=alert(2)>`.
2. The enrolled student saw that title and body exactly as typed, on two lines. No element was created from the text
   and no alert dialog opened.
3. The student saw 3 announcements and then all of them after "Show all", and had no post or edit controls.
4. The teacher edited one ("edited <time>" shown) and deleted another, and the student's reloaded page matched.

Page errors, 5xx responses and horizontal overflow: none after the wrap fix.
