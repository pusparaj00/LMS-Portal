# Step 20 results: accounts (F-01, TR-S-01, TR-S-02, TR-S-06, TR-S-08)

All runs on 2026-10-16 on the dev stack, branch `step-20-accounts`.

## What was built

- **Own account** (`GET/PATCH /me`, `POST /me/password`, Account in the top bar):
  - an optional display name, up to 80 characters;
  - a password change that needs the current password, at least 8 characters, different from the old one, and is
    rate-limited.
  - The change signs out every other session; the reply carries a fresh token so this one carries on.
  - Accounts opened from an LMS have no password here and are told so.
- **Display names** replace the email prefix in the class view, gradebook and gradebook download. They are never sent
  to the AI model; the existing prompt test (TR-S-06) now sets a distinctive name and checks every explanation and chat
  prompt.
- **Admin page** (`/admin/users`, Users in the top bar, admin role only):
  - search by email or name, optionally by role (synthetic demo students are left out, newest 200 shown);
  - create staff accounts;
  - reset a password (a one-time temporary password shown once to the admin, since there is no email service);
  - disable and enable accounts;
  - change roles.
  - An admin cannot disable or demote themselves, and the last enabled admin cannot be removed.
  - An LMS account's role stays with the LMS.
  - `python -m app.manage create-user` still works.
- **Session rules** (migration 0016):
  - Tokens now carry their issue time. After a password change or reset, tokens issued earlier are refused.
  - A disabled account is refused on every request and at login. Its message is given only after the right password,
    so a guesser learns nothing.
  - An LMS launch of a disabled account is refused too.
  - After a reset, the user can reach only `/me` and `/me/password` until they choose a password.
  - Existing accounts start with no recorded change, so the upgrade signed nobody out.
- **Audit events:** `account.password_changed`, `account.password_reset`, `account.disabled`, `account.enabled`,
  `account.role_changed`, `staff.created` (via the admin page).

## Tests

`docker compose --profile test run --rm --build test`: **621 passed**, ruff clean. That is 16 new: 7 in
`backend/tests/test_accounts.py`, plus 9 access-matrix cases for the new routes.
- **Password change:**
  - a wrong current password is refused, and so are the same password and a short one;
  - after the change the old token gets 401 and the new one works;
  - only the new password logs in, and the change is audited.
- **Display name:** set (trimmed), too long refused, shown in the class view, cleared.
- **Reset:**
  - the old session ends;
  - the temporary password logs in with `must_change_password`;
  - every other request gets 403 until the change, then access returns.
- **Staff creation:**
  - a temporary password and forced change;
  - a duplicate gives 409;
  - reserved or invalid addresses are refused;
  - search by name works.
- **Disable:** the open session ends; login with the right password says "disabled", with a wrong password the usual
  message. Enable restores access.
- **Roles and admins:**
  - a role change takes effect at once;
  - an admin cannot demote or disable themselves;
  - the last enabled admin cannot be removed.
- **Access:** students and teachers get 403 on every admin route; anonymous gets 401.
- **Prompts:** a student's display name appears in no explanation or chat prompt.

Also fixed: the rate-limit tests now freeze only the limiter's own clock. One of them failed at random on a minute
boundary in this step's first full run, and its "time moves on" step used to patch `time.time` for the whole test
process.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, with a throwaway admin, teacher and student:
1. The admin created a teacher; the 12-character temporary password was shown once.
2. The teacher's first login showed only "Choose a new password", with no top bar. After the change they reached
   Courses, with the top bar showing "Teacher N · instructor".
3. A student set "Meera Iyer" on the Account page, and the teacher's class view listed "Meera Iyer".
4. The admin reset the teacher, and the teacher's open page went back to the login page on reload.
5. With the account disabled, logging in with the right password said "this account is disabled; ask an
   administrator". After enabling, the account was back.

One defect was found and fixed: at 390 px the Users page overflowed by 17 px, because LMS accounts' long placeholder
addresses could not wrap. Rows now wrap and long addresses break. Final run: no page errors, no 5xx responses, no
overflow.
