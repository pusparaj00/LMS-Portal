---
title: Exceptions
concept: exceptions
status: needs human review
---
## try and except
Code that might fail goes in a `try` block, and an `except` block handles the failure: `try: x = int(text)` then `except ValueError:`. If no exception happens the `except` block is skipped.

## Catch specific exceptions
Name the exception you expect, such as `ValueError`, `ZeroDivisionError` or `KeyError`. A bare `except:` hides unrelated mistakes, including typing errors in your own code.

## Common causes
`int("abc")` and `int("3.5")` raise `ValueError`. Dividing by zero raises `ZeroDivisionError`. Reading a missing dictionary key raises `KeyError`, and an index past the end of a list raises `IndexError`. Assigning to a tuple item raises `TypeError`.

## Choosing the response
Decide what the program should do when the exception happens: skip the value, use a default, or print a message. Ignoring a bad value with `pass` is fine only when skipping it is the intended behaviour.
