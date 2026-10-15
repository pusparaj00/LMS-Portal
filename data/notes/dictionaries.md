---
title: Dictionaries
concept: dictionaries
status: needs human review
---
## Keys and values
A dictionary maps keys to values: `d = {"a": 1}`. Read a value with `d["a"]` and set one with `d["b"] = 2`. Keys must be hashable, such as strings, numbers and tuples.

## Missing keys
`d["z"]` raises a `KeyError` when the key is not present. `d.get("z")` returns `None` instead, and `d.get("z", 0)` returns the default you give. Test membership with `"z" in d`.

## Counting with a dictionary
A common pattern is `counts[word] = counts.get(word, 0) + 1`, which starts a missing key at 0 and adds one. Looping with `for key in d:` visits the keys, and `d.items()` gives key and value pairs.

## Order
Dictionaries keep the order in which keys were first inserted. To print in alphabetical order use `sorted(d)`. Assigning to an existing key replaces its value, so when the same key is read twice the later value wins.
