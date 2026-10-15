---
title: Dictionaries
concept: dictionaries
status: needs human review
---
## Keys and values
A dictionary maps keys to values: `d = {"a": 1}`. Read a value with `d["a"]` and set one with `d["b"] = 2`. Keys must be hashable. Strings, numbers and tuples whose items are all hashable work; a list cannot be a key, and neither can a tuple that contains a list.

```python
d = {(1, 2): "valid"}
try:
    d[([1, 2],)] = "x"
except TypeError:
    print("unhashable")
print(d[(1, 2)])
```
Output:
```
unhashable
valid
```

## Missing keys
`d["z"]` raises a `KeyError` when the key is not present. `d.get("z")` returns `None` instead, and `d.get("z", 0)` returns the default you give. Test membership with `"z" in d`.

```python
d = {"a": 1}
print(d.get("b"))
print(d.get("b", 0))
```
Output:
```
None
0
```

## Counting with a dictionary
A common pattern is `counts[word] = counts.get(word, 0) + 1`, which starts a missing key at 0 and adds one. Looping with `for key in d:` visits the keys, and `d.items()` gives key and value pairs.

```python
counts = {}
for word in "to be or not to be".split():
    counts[word] = counts.get(word, 0) + 1
print(counts)
```
Output:
```
{'to': 2, 'be': 2, 'or': 1, 'not': 1}
```

## Order
Dictionaries keep the order in which keys were first inserted. To print in alphabetical order use `sorted(d)`. Assigning to an existing key replaces its value; it does not add a second entry, so when the same key is read twice the later value wins.

```python
d = {"a": 1}
d["a"] = 2
print(d, len(d))
```
Output:
```
{'a': 2} 1
```
