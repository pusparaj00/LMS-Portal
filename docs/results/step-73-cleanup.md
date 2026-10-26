# Step 73: test-data cleanup of the live database (G-16)

Run on 2026-10-26 against the live Postgres, after `backup/lms-2026-10-26-before-cleanup.dump` (pg_dump -Fc, 5.5 MB,
`pg_restore --list` shows 54 table-data entries). The script `backup/cleanup-2026-10-26.sql` is git-ignored with the other
backups; it was run first as a dry run (`ROLLBACK`), then with `COMMIT` after the dry run passed every guard.

| | Before | Removed | After (measured by query) |
| --- | --- | --- | --- |
| Users | 559 | 522 | 37 |
| Courses | 64 | 54 | 10 |
| Problems | 193 | 43 | 150 |
| Submissions | 503 | 402 | 101 |

Every kept-data count (enrollments, mastery, mastery_events, explanation_cache, chat_messages, documents, audit_events,
erasure_requests, run_results) was identical before and after inside the transaction. Kept on purpose: the demo, lms and
real accounts, the synthetic class, courses 19 and 409, and 6 test-pattern accounts whose submissions are the source of
stored explanations on problems that stay (F-46, F-62); those 6 were taken out of the classes.

Changes against the 2026-10-19 script: LTI contexts and users are deleted; the explanation-source exclusion applies only to
sources of explanations on kept problems (the two audit-* accounts' explanations were on removed problems); removed
accounts enrolled in demo courses 19 and 409 (157 enrollments) are expected and no longer stop the script.
The throwaway accounts (langcheck-, smoke-, g3-) all matched the patterns. Problems and submissions "before" are
derived: kept count plus removed count from the dry run.
