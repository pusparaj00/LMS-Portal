"""Language knowledge for the feedback pipeline (multi-language support).

The verifier and leak guard both need to know what is "plain" for a language (names a claim may quote
without them being invented code) and what looks like code. Python is the historical default; java and c
share the same generic token comparison, they just differ in keywords, primitives and code-looking signals.
"""
import builtins
import keyword
import re

LANGUAGES = ("python", "java", "c")

KEYWORDS = {
    "python": set(keyword.kwlist),
    "java": {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
        "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
        "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long", "native",
        "new", "package", "private", "protected", "public", "return", "short", "static", "strictfp",
        "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try", "void",
        "volatile", "while",
    },
    "c": {
        "auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum",
        "extern", "float", "for", "goto", "if", "inline", "int", "long", "register", "restrict", "return",
        "short", "signed", "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned", "void",
        "volatile", "while",
    },
}

# Names a claim may quote without the student's code containing them: keywords, primitive types and a
# modest set of standard-library identifiers. Deliberately generous — the leak guard (containment against
# the reference) is the real defence; this only stops the verifier flagging ordinary names as invented.
PLAIN = {
    "python": set(keyword.kwlist) | {
        "print", "input", "range", "len", "int", "str", "float", "sum", "max", "min", "sorted", "set",
        "list", "dict", "abs", "map", "split", "strip", "lower", "upper", "append", "join", "get",
        "items", "keys",
    },
    "java": KEYWORDS["java"] | {
        "String", "System", "out", "println", "print", "Integer", "Math", "Boolean",
        "Double", "Float", "Long", "Character", "Scanner", "Console", "Integer.parseInt", "True", "False",
        "null", "Integer.valueOf",
    },
    "c": KEYWORDS["c"] | {
        "printf", "scanf", "puts", "getchar", "putchar", "stdin", "stdout", "stderr", "NULL",
        "size_t", "malloc", "free", "calloc", "realloc", "strlen", "strcpy", "strcmp", "strcat", "atoi",
        "atof", "abs", "sqrt", "pow", "floor", "ceil", "true", "false",
    },
}

# Names a claim may quote without the student's code containing them. For python this must match the
# historical `dir(builtins) | keyword.kwlist` exactly, so the verifier's quoted-code check is unchanged.
CLAIM_PLAIN = {
    "python": set(dir(builtins)) | set(keyword.kwlist),
    "java": KEYWORDS["java"] | {
        "String", "System", "out", "println", "print", "Integer", "Math", "Boolean", "Double", "Float",
        "Long", "Character", "Scanner", "Console", "parseInt", "valueOf", "true", "false", "null",
    },
    "c": KEYWORDS["c"] | {
        "printf", "scanf", "puts", "getchar", "putchar", "stdin", "stdout", "stderr", "NULL", "size_t",
        "malloc", "free", "calloc", "realloc", "strlen", "strcpy", "strcmp", "strcat", "atoi", "atof",
        "abs", "sqrt", "pow", "floor", "ceil", "true", "false",
    },
}

# A number or string literal is allowed in a claim in any language.
_STRING_OR_CHAR = r"\"[^\"]*\"|'(?:[^'\\]|\\.)'"
_LITERAL = {
    "java": re.compile(
        r"^(?:[+-]?\d+(?:\.\d+)?[fFdDlLuU]*|0[bx][0-9a-fA-F_]+[fFdDlLuU]*|" + _STRING_OR_CHAR + r"|true|false|null)$"),
    "c": re.compile(
        r"^(?:[+-]?\d+(?:\.\d+)?[uUlLfF]*|0[xX][0-9a-fA-F]+[uUlLfF]*|0[bB][01]+[uUlLfF]*|"
        + _STRING_OR_CHAR + r"|NULL|true|false)$"),
}


def is_supported(language: str) -> bool:
    return language in LANGUAGES


def plain_names(language: str) -> set[str]:
    """Names kept distinct (not collapsed to ID) when normalising code for the leak guard."""
    return PLAIN.get(language, PLAIN["python"])


def is_plain(token: str, language: str) -> bool:
    """A name the verifier lets a claim quote without it being in the student's code."""
    return token in CLAIM_PLAIN.get(language, CLAIM_PLAIN["python"])


def is_literal(token: str, language: str) -> bool:
    if language == "python":
        import ast
        try:
            ast.literal_eval(token)
            return True
        except (ValueError, SyntaxError):
            return False
    pattern = _LITERAL.get(language)
    return bool(pattern.match(token)) if pattern is not None else False


def code_word(language: str) -> str:
    """A regex fragment matching the language's most code-telling keywords, for leak detection."""
    if language == "java":
        words = ("class|public|static|void|main|String|int|return|import|new|for|while|if|else|System")
    elif language == "c":
        words = ("int|char|float|double|return|include|printf|scanf|for|while|if|else|struct|main")
    else:
        words = ("def|return|import|for|while|if|elif|else|print|input|lambda|class|try|except")
    return rf"\b(?:{words})\b"


def statement_start(language: str) -> str:
    """A regex matching a line that begins like a statement of the language."""
    if language == "java":
        return r"^(?:class|public|static|void|int|return|System|new|for|while|if|else)\b"
    if language == "c":
        return r"^(?:int|char|float|double|return|printf|scanf|for|while|if|else|struct|main)\b"
    return r"^(?:def|return|import|for|while|if|elif|else|class|try|except|with)\b|^[a-z_][\w.]*\("


def indent_sensitive(language: str) -> bool:
    """Only Python treats indentation as a code signal; java and c use braces instead."""
    return language == "python"
