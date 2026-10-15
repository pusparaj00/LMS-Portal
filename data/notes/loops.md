---
title: Loops and range
concept: loops
status: needs human review
---
## The for loop
A `for` loop runs its body once for each item in a sequence. `for item in items:` takes the items one at a time, and `for i in range(5):` repeats the body five times with `i` set to 0, 1, 2, 3 and 4.

## How range works
`range(stop)` counts from 0 up to but not including `stop`, so `range(5)` gives 0 to 4. `range(start, stop)` begins at `start`, so `range(1, 6)` gives 1 to 5. `range(start, stop, step)` moves by `step`, and a negative step counts down: `range(5, 0, -1)` gives 5, 4, 3, 2, 1. The most common off-by-one mistake is forgetting that `stop` is excluded, so to include `n` write `range(1, n + 1)`.

## The while loop
A `while` loop repeats as long as its condition is true. Something inside the loop must change the condition, otherwise the loop never ends. If a program runs for too long, check that every `while` loop moves towards its stopping condition.

## Accumulating a result
To add up values, start a variable before the loop (`total = 0`) and update it inside (`total += i`). Starting the variable inside the loop resets it on every pass.
