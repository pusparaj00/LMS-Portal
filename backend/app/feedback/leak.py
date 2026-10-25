"""Leak guard (TR-L-06, F-44): reject replies that contain solution code. Deterministic, no second LLM.

A reply fails if it has fenced code, more than MAX_CODE_LINES lines that look like code, an over-long
inline snippet, or code-like text whose token pattern closely matches the reference solution. Identifiers,
numbers and strings are normalised before comparing, so renaming variables does not hide a copy.
"""
import re
from dataclasses import dataclass

from app.feedback import lang

MAX_CODE_LINES = 3
MAX_INLINE_SNIPPET_CHARS = 60
MIN_TOKENS_TO_COMPARE = 12  # shorter fragments (a single `range(1, n + 1)`) are not a solution...
MIN_TOKENS_FLOOR = 6  # ...unless the whole reference solution is shorter: then a copy of all of it is compared too
SIMILARITY_THRESHOLD = 0.7  # chosen on the question bank, see evaluation/leak_threshold.py
STRICTEST_THRESHOLD = 0.3  # a problem may only make the guard stricter (F-62), down to this
NGRAM = 3

FENCE = "`" * 3
SYMBOLS = frozenset("()[]{}:=<>+-*/%,")
MIN_SYMBOL_DENSITY = 0.1  # prose has few brackets and operators per character
TOKEN = re.compile(
    r"[A-Za-z_]\w*|\d+(?:\.\d+)?|\"[^\"\n]*\"|'[^'\n]*'|==|!=|<=|>=|//|\*\*|\+=|-=|[-+*/%()\[\]{}:,.=<>]"
)
ASSIGNMENT = re.compile(r"^\s*[A-Za-z_][\w\[\]\.]*\s*(?:[-+*/]?=)\s*\S")
INLINE = re.compile(r"`([^`\n]+)`")
BRACE_LANGS = ("java", "c")  # indentation is not a code signal for these; brace-terminated lines are


@dataclass(frozen=True)
class LeakResult:
    passed: bool
    reason: str


def normalise_tokens(code: str, language: str = "python") -> list[str]:
    plain = lang.plain_names(language)
    out = []
    for token in TOKEN.findall(code):
        if token[0].isdigit():
            out.append("NUM")
        elif token[0] in "\"'":
            out.append("STR")
        elif token[0].isalpha() or token[0] == "_":
            out.append(token if token in plain else "ID")
        else:
            out.append(token)
    return out


def _ngrams(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + NGRAM]) for i in range(max(0, len(tokens) - NGRAM + 1))}


def containment(candidate: str, reference: str, language: str = "python") -> float:
    """Share of the candidate's token 3-grams that also occur in the reference solution."""
    grams = _ngrams(normalise_tokens(candidate, language))
    if not grams:
        return 0.0
    return len(grams & _ngrams(normalise_tokens(reference, language))) / len(grams)


def long_enough_to_compare(code: str, reference: str, language: str = "python") -> bool:
    """Short fragments are pointers, not solutions; but a reference shorter than the minimum is itself that short."""
    needed = max(MIN_TOKENS_FLOOR, min(MIN_TOKENS_TO_COMPARE, len(normalise_tokens(reference, language))))
    return len(normalise_tokens(code, language)) >= needed


def looks_like_code(line: str, language: str = "python") -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if language == "python" and line.startswith(("    ", "\t")):
        return True
    if ASSIGNMENT.match(stripped) and not stripped.endswith((".", "?", "!")):
        return True
    if stripped.endswith((".", "?", "!")):
        return False
    symbols = sum(ch in SYMBOLS for ch in stripped)
    if language in BRACE_LANGS and stripped.endswith((";", "{", "}")):
        return True
    if re.match(lang.statement_start(language), stripped) and (symbols >= 2 or stripped.endswith(":")):
        return True
    dense = symbols >= 4 and symbols / len(stripped) >= MIN_SYMBOL_DENSITY
    return bool(re.search(lang.code_word(language), stripped)) and dense


def code_like_text(text: str, language: str = "python") -> tuple[list[str], list[str]]:
    """The lines that look like code, and the inline `snippets`."""
    inline = INLINE.findall(text)
    without_inline = INLINE.sub(" ", text)
    return [line for line in without_inline.splitlines() if looks_like_code(line, language)], inline


def code_in(text: str, language: str = "python") -> str:
    """All the code in a text: fenced blocks, lines that look like code, and inline snippets."""
    blocks = re.findall(FENCE + r"[^\n]*\n(.*?)" + FENCE, text, re.S)
    lines, snippets = code_like_text(re.sub(FENCE + ".*?" + FENCE, " ", text, flags=re.S), language)
    return "\n".join([*blocks, *lines, *snippets])


def copies_reference(
    text: str, reference_solution: str, threshold: float = SIMILARITY_THRESHOLD, language: str = "python"
) -> bool:
    """Whether code in a text matches the reference solution. Unlike `check`, a short example in a fence is allowed:
    this is for text written for the course (notes), not for a model reply."""
    code = code_in(text, language)
    return long_enough_to_compare(code, reference_solution, language) and containment(
        code, reference_solution, language) >= min(threshold, SIMILARITY_THRESHOLD)


def check(
    text: str, reference_solution: str, threshold: float = SIMILARITY_THRESHOLD, language: str = "python"
) -> LeakResult:
    """`threshold` is the problem's leak policy; it is never allowed above the tuned default."""
    threshold = min(threshold, SIMILARITY_THRESHOLD)
    if FENCE in text:
        return LeakResult(False, "fenced code block")
    lines, snippets = code_like_text(text, language)
    if len(lines) > MAX_CODE_LINES:
        return LeakResult(False, f"{len(lines)} lines of code (limit {MAX_CODE_LINES})")
    if any(len(s) > MAX_INLINE_SNIPPET_CHARS for s in snippets):
        return LeakResult(False, "inline snippet longer than a short expression")
    combined = "\n".join([*lines, *snippets])
    if long_enough_to_compare(combined, reference_solution, language):
        similarity = containment(combined, reference_solution, language)
        if similarity >= threshold:
            return LeakResult(False, f"code matches the reference solution ({similarity:.0%})")
    return LeakResult(True, "no solution code")
