---
title: Lists
concept: lists
status: needs human review
---
## Indexing
List positions start at 0. `xs[0]` is the first item, `xs[-1]` the last and `xs[-2]` the second to last. An index that is too large raises an `IndexError`, and so does a negative index that reaches past the start: `xs[-5]` on a list of three items.

```python
xs = [1, 2, 3]
print(xs[-3])
try:
    xs[-5]
except IndexError:
    print("IndexError")
```
Output:
```
1
IndexError
```

## Changing a list
`xs.append(x)` adds one item at the end. `xs.extend(other)` adds each item of another list, so `[1, 2]` after `append([3, 4])` has three items but after `extend([3, 4])` has four. `xs.sort()` sorts in place and returns `None`, while `sorted(xs)` returns a new list.

```python
a = [1, 2]
a.append([3, 4])
print(len(a))
b = [1, 2]
b.extend([3, 4])
print(len(b))
```
Output:
```
3
4
```

## Assignment does not copy
`b = a` makes `b` another name for the same list, so changing one changes the other. Make a copy with `a.copy()` or `a[:]` when you need an independent list.

```python
a = [1, 2]
b = a
b.append(3)
print(a)
```
Output:
```
[1, 2, 3]
```

## Shallow copies
`a.copy()` and `a[:]` make a new outer list, but items that are themselves lists are still shared between the two.

```python
a = [[1, 2]]
b = a.copy()
b[0].append(3)
print(a)
```
Output:
```
[[1, 2, 3]]
```

## Looping and slicing
`for x in xs:` visits each item. `xs[a:b]` gives a new list from index `a` up to but not including `b`. `sum(xs)`, `max(xs)` and `min(xs)` work on a list of numbers, and `max` or `min` of an empty list raises a `ValueError`, so handle the empty case.

```python
try:
    max([])
except ValueError:
    print("empty")
```
Output:
```
empty
```
