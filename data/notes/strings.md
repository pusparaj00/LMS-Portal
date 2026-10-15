---
title: Strings
concept: strings
status: needs human review
---
## Strings are immutable
A string cannot be changed in place. Methods such as `upper()`, `lower()`, `strip()` and `replace()` return a new string and leave the original unchanged, so write `s = s.upper()` to keep the result. Writing `s.upper()` on its own line does nothing useful.

## Indexing and slicing
`s[0]` is the first character and `s[-1]` is the last. A slice `s[a:b]` takes the characters from index `a` up to but not including `b`, and `s[::-1]` is the string reversed. Slices never raise an error for out-of-range bounds, but a single index does.

## Useful methods
`s.split()` splits on whitespace and returns a list of words, and an empty string gives an empty list. `"-".join(parts)` joins a list of strings. `s.lower()` helps compare text without regard to case, and `len(s)` is the number of characters.

## Reading input
`input()` always returns a string, without the trailing newline. Convert with `int(...)` or `float(...)` before doing arithmetic.
