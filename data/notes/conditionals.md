---
title: Conditionals
concept: conditionals
status: needs human review
---
## if, elif and else
An `if` statement runs its block only when its condition is true. `elif` adds another condition that is checked only if the earlier ones were false, and `else` runs when none of them were true. Exactly one branch of an `if`/`elif`/`else` chain runs.

## Separate if statements are independent
Two separate `if` statements are both checked every time, so both blocks can run. Use `elif` when the cases are meant to exclude each other.

## Comparing values
Use `==` to test equality and `=` only to assign. The comparison operators are `==`, `!=`, `<`, `<=`, `>` and `>=`. Combine conditions with `and`, `or` and `not`.

## Boundaries
Many wrong answers come from a boundary: whether a score of exactly 90 counts as an A depends on using `>=` or `>`. Test the values on each side of every boundary, and check the order of an `elif` chain: the first true condition wins, so list the narrowest case first when ranges overlap.
