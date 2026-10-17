# Step 35: every wrong solution fails where it should (TR-V-02)

Date: 2026-10-17. Branch `step-35-wrong-solutions`.

## What changed

- "Most common letter" has a fourth hidden tie test, `ccbbaa` with expected output `a`. In the three earlier tie tests
  the alphabetically first letter was also the first one seen, so `max(counts, key=counts.get)` passed them by luck.
- `evaluation/wrong_solutions.py` runs the 21 wrong solutions from the rating sheet against the stored problems,
  hidden tests included, in the sandbox. For each one it checks that it fails, and that the category its mistake is
  about is among the failing ones. The expected category is written next to each mistake, decided from the mistake and
  not from a run.

## Results (throwaway stack `-p lmsui`, fresh seed, course 1)

`python -m app.bank_import /srv/data/bank --dry-run`: validated 47 of 47 (35 code problems, 12 tracing items).
The seed then reported 1 problem updated (the new test) and 46 unchanged.

`python -m evaluation.wrong_solutions 1`, run 2026-10-17 06:16 UTC:

| Problem | Expected category | Result | Failing categories | Caught as expected |
| --- | --- | --- | --- | --- |
| Sum from 1 to n | basic | failed | basic, large_input | yes |
| Factorial | basic | failed | basic, large_input, zero | yes |
| Countdown | basic | failed | basic | yes |
| Reverse a string | basic | failed | basic, empty_input, palindrome, single_char, spaces | yes |
| Count vowels | uppercase | failed | uppercase | yes |
| Second largest | duplicates | failed | duplicates | yes |
| Word frequency | basic | failed | basic, ordering, single_item | yes |
| Fibonacci | base_case | failed | base_case, basic, large_input | yes |
| Safe division | zero_divisor | failed | basic, negative_numbers, zero, zero_divisor | yes |
| Rectangle | basic | failed | basic, square, zero | yes |
| Palindrome check | uppercase | failed | uppercase | yes |
| Remove duplicates | order | failed | order | yes |
| Grade letter | boundary | failed | boundary | yes |
| Leap year | century | failed | century | yes |
| Digit sum | base_case | failed | base_case, basic, large_input | yes |
| Phone book | missing_key | failed | empty_input, missing_key | yes |
| Rotate left | k_larger_than_n | failed | k_larger_than_n | yes |
| Most common letter | tie | failed | tie | yes |
| Word count | whitespace | failed | empty_input, whitespace | yes |
| Even or odd | basic | failed | basic, negative_numbers, zero | yes |
| Sum and maximum | basic | failed | basic, duplicates, negative_numbers | yes |

**21 of 21 wrong solutions fail in the expected category.** TR-V-02 now passes.

Full suite after the bank change (`docker compose --profile test run --rm test`): ruff clean, 666 passed.

## By hand

The app database still has the old tests for "Most common letter" in its courses until the seed runs there
(`docker compose exec -T api python -m app.seed`; it creates nothing new and prints no passwords for existing accounts).
