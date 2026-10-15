---
title: Lists
concept: lists
status: needs human review
---
## Indexing
List positions start at 0. `xs[0]` is the first item, `xs[-1]` the last and `xs[-2]` the second to last. Using an index equal to `len(xs)` raises an `IndexError`.

## Changing a list
`xs.append(x)` adds one item at the end. `xs.extend(other)` adds each item of another list, so `[1, 2]` after `append([3, 4])` has three items but after `extend([3, 4])` has four. `xs.sort()` sorts in place and returns `None`, while `sorted(xs)` returns a new list.

## Assignment does not copy
`b = a` makes `b` another name for the same list, so changing one changes the other. Make a copy with `a.copy()` or `a[:]` when you need an independent list.

## Looping and slicing
`for x in xs:` visits each item. `xs[a:b]` gives a new list from index `a` up to but not including `b`. `sum(xs)`, `max(xs)` and `min(xs)` work on a list of numbers, and `max` of an empty list raises an error, so handle the empty case.
