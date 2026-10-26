"""Template hints keyed on error type and concept (TR-L-12). No model text, so nothing here can be wrong
about the student's code or reveal a solution."""

ERROR_TEMPLATES = {
    "syntax_error": "Python could not read your program, so no test ran. Look at the line named in the error "
    "message for a missing colon, bracket, quote or a wrongly indented line.",
    "time_limit": "Your program ran for too long. Check that every loop moves towards its stopping condition, "
    "and that nothing waits for input that never comes.",
    "memory_limit": "Your program used too much memory. Look for a list or string that keeps growing.",
    "output_limit": "Your program printed far too much. Look for a loop that prints on every pass without ending.",
    "runtime_error": "Your program stopped with an error on some inputs. Read the error message: it names the "
    "kind of error and the line where it happened.",
    None: "Your program ran but gave a different answer from the expected one on some tests. Compare your output "
    "with the expected output on the examples, then think about the categories of test listed below.",
}

CONCEPT_TEMPLATES = {
    "variables_io": "Check how you read the input and convert it, and what you print at the end.",
    "conditionals": "Check each condition and its boundary, and whether separate if statements should be elif.",
    "loops": "Check where your loop starts and stops, and whether it includes the last item.",
    "strings": "Remember that string methods return a new string, and check your indexes and slices.",
    "lists": "Check your indexes, and whether two names refer to the same list.",
    "tuples_sets": "Remember that sets drop duplicates and tuples cannot be changed.",
    "dictionaries": "Check what happens when a key is missing and how you update counts.",
    "functions": "Check that the function returns its result instead of printing it.",
    "recursion": "Check the base case, and that the recursive call's result is returned.",
    "comprehensions": "Check the condition and the expression inside your comprehension.",
    "exceptions": "Check which exception you catch and what the program does after catching it.",
    "classes": "Check what each method changes on the object and what it returns.",
}


# What to look at for a failing test category that says what kind of input broke the program. A category with a sentence
# here replaces the concept sentence, which is about the whole topic and can point at something the code already does.
CATEGORY_TEMPLATES = {
    "boundary": "Look at the values exactly on the edge between two cases: does each comparison include or exclude "
    "the edge value?",
    "zero": "Try the program by hand with the input 0 and follow what each line does with it.",
    "negative_numbers": "Try the program by hand with a negative number and follow what each line does with it.",
    "empty_input": "Try the program by hand with nothing to process and follow what each line does with it.",
    "single_item": "Try the program by hand with just one item and follow what each line does with it.",
    "large_input": "Think about how much work your program does when the input is very large.",
    "duplicates": "Try the program by hand with the same value appearing twice and follow what each line does with it.",
    "base_case": "Check what your program does for the smallest possible input before any repeating step starts.",
}


def template_hint(error_type: str | None, concept_name: str | None, failed_categories: list[str]) -> str:
    parts = [ERROR_TEMPLATES.get(error_type, ERROR_TEMPLATES["runtime_error"])]
    if error_type is None and failed_categories:
        parts.append("Failing categories: " + ", ".join(c.replace("_", " ") for c in failed_categories) + ".")
    specific = [CATEGORY_TEMPLATES[c] for c in failed_categories if c in CATEGORY_TEMPLATES]
    if error_type is not None:
        specific = []
    if specific:
        parts.append(specific[0])
    elif concept_name in CONCEPT_TEMPLATES:
        parts.append(CONCEPT_TEMPLATES[concept_name])
    return " ".join(parts)
