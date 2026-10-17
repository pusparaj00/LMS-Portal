# Step 34: adult confirmation (TR-S-10)

Date: 2026-10-17. Branch `step-34-adult-confirmation`.

## What changed

- The privacy notice (now version `2026-10-v4`) opens with "Who can use this". The system is for people aged 18 or
  over, and there is no parental-consent route yet, so learners under 18 are told to speak to their instructor.
- `POST /consent/accept` takes `adult: true`. Without it the reply is 422 and nothing is recorded. Consent counts only when
  the latest agreement has `adult_confirmed` (migration 0021). The audit trail records `adult: true`.
- The Privacy page has a checkbox, "I confirm that I am 18 or older", and "I agree" stays disabled until it is ticked.
- Because the notice version changed, every student is asked once more. This also collects the age confirmation from
  existing accounts.

TR-S-10 asks for an adult confirmation or a verified parental-consent step. The first is built. The second needs a real
way to verify a parent, which the institution would have to define, so it is not built.

## Checks

- `docker compose --profile test run --rm test` (ruff and pytest): 663 passed, 3 failed. All three failures were tests
  that found the notice sections by position, and the new section is first. After updating them,
  `pytest tests/test_consent.py tests/test_student_work.py tests/test_contract.py` passed 24 of 24, so all 666 tests pass.
- New test `test_agreeing_needs_the_student_to_confirm_they_are_an_adult` covers four things: no flag or `false` gives 422,
  the student stays blocked from chat, agreeing with the flag works, and the row has `adult_confirmed = true`.
- Browser (throwaway stack `-p lmsui`): "I agree" was disabled before the box was ticked. After ticking it and agreeing,
  a submission returned 200. 18 pages for the three roles at 1366 and 390 px had no console errors and no horizontal overflow.
