---
title: Recursion
concept: recursion
status: needs human review
---
## Base case and recursive case
A recursive function calls itself on a case that makes progress towards a base case, usually a smaller input. It needs a base case that returns without a further call, and a recursive case that moves towards it. Python stops runaway recursion with a `RecursionError` after about a thousand nested calls. That limit is a safety net, not a replacement for a correct base case.

## A complete example
Factorial has the base case `n == 0` and a recursive case that uses a smaller `n`.

```python
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)

print(factorial(4))
```
Output:
```
24
```

## Returning the recursive result
The value of a recursive call must be returned or used. Writing `total(n - 1)` on its own line computes a value and throws it away, so the function returns `None`. Write `return n + total(n - 1)`.

```python
def total(n):
    if n == 0:
        return 0
    total(n - 1)

print(total(3))
```
Output:
```
None
```

## Tracing a call
To check a recursive function, trace a small input by hand. Here `fib(0) = 0` and `fib(1) = 1` (other definitions start differently): `fib(4)` calls `fib(3)` and `fib(2)`, and so on until the base cases `fib(1)` and `fib(0)`. Tracing on `0` and `1` first usually exposes a missing or wrong base case.

## Cost
Calling a function twice in the recursive case, as the plain Fibonacci definition does, repeats work and becomes slow for larger inputs.
