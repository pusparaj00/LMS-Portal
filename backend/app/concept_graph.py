"""The prerequisite graph of a course (F-29): concept -> the concepts it builds on."""


def creates_cycle(graph: dict[int, list[int]], concept: int, prerequisites: list[int]) -> bool:
    """True if giving `concept` these prerequisites would make it, directly or not, a prerequisite of itself."""
    seen: set[int] = set()
    stack = list(prerequisites)
    while stack:
        current = stack.pop()
        if current == concept:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, []))
    return False
