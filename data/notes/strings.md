---
title: Strings
concept: strings
status: needs human review
---
## Strings are immutable
A string cannot be changed in place. Methods such as `upper()`, `lower()`, `strip()` and `replace()` return a new string and leave the original unchanged, so write `s = s.upper()` to keep the result. Writing `s.upper()` on its own line does nothing useful.

```python
s = "hello"
s.upper()
print(s)
s = s.upper()
print(s)
```
Output:
```
hello
HELLO
```

## Indexing and slicing
`s[0]` is the first character and `s[-1]` is the last. A slice `s[a:b]` takes the characters from index `a` up to but not including `b`, and `s[::-1]` is the string reversed. Slices never raise an error for out-of-range bounds, but a single index does.

```python
print("hello"[1:3])
print("hello"[::-1])
```
Output:
```
el
olleh
```

## Useful methods
`s.split()` with no argument splits on runs of whitespace and ignores whitespace at the ends, so an empty string gives an empty list. `s.split(",")` splits at every comma and keeps empty fields. `"-".join(parts)` joins a list of strings. `s.lower()` helps compare text without regard to case, and `len(s)` is the length.

```python
print("a  b ".split())
print("a,,b".split(","))
```
Output:
```
['a', 'b']
['a', '', 'b']
```

## Reading input
`input()` always returns a string. It removes the trailing newline but keeps any other spaces the user typed. Convert with `int(...)` or `float(...)` before doing arithmetic.

## Length and characters
`len(s)` counts Python's code points, which is usually the number of characters you see. A letter written as a base letter plus a combining accent counts as two.

```python
print(len("é"), len("é"))
```
Output:
```
2 1
```
