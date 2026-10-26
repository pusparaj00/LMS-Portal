"""TR-L-12: the template hint names what to look at for the failing category, not a sentence about the whole topic."""
from app.feedback.fallback import template_hint


def test_a_boundary_failure_gets_the_boundary_sentence_not_the_conditionals_one():
    text = template_hint(None, "conditionals", ["boundary"])
    assert "exactly on the edge" in text and "elif" not in text


def test_a_category_without_its_own_sentence_still_gets_the_concept_sentence():
    assert "elif" in template_hint(None, "conditionals", ["tie"])


def test_an_error_type_hint_is_unchanged_by_the_categories():
    assert "could not read your program" in template_hint("syntax_error", "conditionals", ["boundary"])
