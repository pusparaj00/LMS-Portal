---
title: Functions and return values
concept: functions
status: needs human review
---
## Defining and calling
`def name(parameters):` defines a function and `name(arguments)` calls it. An assignment inside a function normally creates or updates a local variable that exists only during that call, unless the name is declared `global` or `nonlocal`.

## Return is not print
`return value` sends a value back to the caller and ends the function. `print(value)` only shows text on the screen. A function with no `return` statement returns `None`, so `y = f(4)` gives `None` when `f` only prints.

```python
def f(x):
    print(x * 2)

y = f(4)
print(y)
```
Output:
```
8
None
```

## Default arguments
A default value such as `def add(x, items=[])` is created once, when the function is defined, not on every call. A mutable default, such as a list, therefore persists between calls and keeps any change made to it. It grows only because this function changes it. Use `items=None` and create the list inside the function when you want a fresh one each time.

```python
def add(x, items=[]):
    items.append(x)
    return items

print(add(1))
print(add(2))
```
Output:
```
[1]
[1, 2]
```

## Parameters and tests
Check what happens for small and boundary inputs such as zero, one and an empty list. A helper function that does one job is easier to test than one long block of code.
