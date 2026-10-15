---
title: Loops and range
concept: loops
status: needs human review
---
## The for loop
A `for` loop runs its body once for each item in a sequence. `for item in items:` takes the items one at a time, and `for i in range(3):` repeats the body three times with `i` set to 0, 1 and 2.

```python
for i in range(3):
    print(i)
```
Output:
```
0
1
2
```

## How range works
`range(stop)` counts from 0 up to but not including `stop`, so `range(5)` gives 0 to 4. `range(start, stop)` begins at `start`, so `range(1, 6)` gives 1 to 5. `range(start, stop, step)` moves by `step`, and a negative step counts down: `range(5, 0, -1)` gives 5, 4, 3, 2, 1. The most common off-by-one mistake is forgetting that `stop` is excluded, so to include `n` write `range(1, n + 1)`.

```python
print(list(range(1, 6)))
print(list(range(5, 0, -1)))
```
Output:
```
[1, 2, 3, 4, 5]
[5, 4, 3, 2, 1]
```

## The while loop
A `while` loop repeats as long as its condition is true. Make sure every `while` loop has a reachable way to stop: either something inside the loop changes the condition, or the loop leaves deliberately with `break`. If a program runs for too long, check each loop's stopping condition first.

## break and continue
`break` leaves the loop immediately. `continue` skips the rest of the current pass and goes on to the next one.

```python
for i in range(1, 6):
    if i == 2:
        continue
    if i == 4:
        break
    print(i)
```
Output:
```
1
3
```

## Accumulating a result
To add up values, start a variable before the loop (`total = 0`) and update it inside (`total += i`). Starting the variable inside the loop resets it on every pass.

```python
total = 0
for i in range(1, 5):
    total += i
print(total)
```
Output:
```
10
```
