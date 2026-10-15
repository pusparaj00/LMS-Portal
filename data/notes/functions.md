---
title: Functions and return values
concept: functions
status: needs human review
---
## Defining and calling
`def name(parameters):` defines a function and `name(arguments)` calls it. Variables created inside a function are local to it.

## Return is not print
`return value` sends a value back to the caller and ends the function. `print(value)` only shows text on the screen. A function with no `return` statement returns `None`, so `y = f(4)` gives `None` when `f` only prints.

## Default arguments
A default value such as `def add(x, items=[])` is created once, when the function is defined, not on every call. A default list is therefore shared between calls and keeps growing. Use `items=None` and create the list inside the function.

## Parameters and tests
Check what happens for small and boundary inputs such as zero, one and an empty list. A helper function that does one job is easier to test than one long block of code.
