"""TR-P-08: the model-usage report counts live calls and stored answers from explanation_checks rows."""
from evaluation.llm_usage import report, summarise


def rows():
    return [
        # 1: verified on the first attempt (one call)
        (1, 1, "gemini", "json_valid", True), (1, 1, "gemini", "final", True),
        # 2: rejected once, verified on the retry (two calls)
        (2, 1, "gemini", "test_exists", False), (2, 2, "gemini", "json_valid", True), (2, 2, "gemini", "final", True),
        # 3: the provider failed twice, template hint (two calls, a fallback)
        (3, 1, "gemini", "llm_call", False), (3, 2, "gemini", "llm_call", False), (3, 2, "gemini", "final", False),
        # 4: from the failure-signature cache (no call)
        (4, 0, "cache", "json_valid", True), (4, 0, "cache", "final", True),
        # 5: from the prepared demo explanations (no call)
        (5, 0, "cached-demo", "json_valid", True), (5, 0, "cached-demo", "final", True),
    ]


def test_calls_per_100_and_the_stored_share_are_computed_from_the_rows():
    result = summarise(rows())
    assert result["explained"] == 5 and result["live_calls"] == 5  # 1 + 2 + 2
    assert result["calls_per_100"] == 100.0
    assert result["stored"] == {"cache": 1, "cached-demo": 1} and result["stored_share"] == 0.4
    assert result["fallback"] == 1 and result["max_calls_for_one_submission"] == 2


def test_the_report_states_the_numbers_and_the_two_call_limit():
    text = report(summarise(rows()), None)
    assert "**100.0**" in text and "**40%**" in text and "limit: 2" in text


def test_an_empty_period_says_so_instead_of_dividing_by_zero():
    result = summarise([])
    assert result["calls_per_100"] is None and result["explained"] == 0
    assert report(result, None) == "No explained submissions in this period."


def test_a_third_call_for_one_submission_would_be_visible():
    extra = [(9, n, "gemini", "json_valid", True) for n in (1, 2, 3)]
    assert summarise(extra)["max_calls_for_one_submission"] == 3
