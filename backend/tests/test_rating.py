"""TR-V-03: the rating sheet is blinded and the scoring script computes the correct-claim share per flow."""
import random

from evaluation import rating_sheet as rs


def key(i, first):
    other = "plain" if first == "verified" else "verified"
    return {"id": str(i), "explanation_1_is": first, "explanation_2_is": other, "verified_status": "verified",
            "verified_attempts": "1", "provider": "x"}


def row(i, r1_1="", r1_2="", r2_1="", r2_2=""):
    return {"id": str(i), "r1_exp1": r1_1, "r1_exp2": r1_2, "r2_exp1": r2_1, "r2_exp2": r2_2}


def test_the_shuffle_hides_the_origin_but_is_reproducible_and_balanced():
    pairs = [rs.shuffled_pair(random.Random(rs.SEED), "V", "P") for _ in range(2)]
    assert pairs[0] == pairs[1]
    rng = random.Random(rs.SEED)
    firsts = [rs.shuffled_pair(rng, "V", "P")[2] for _ in range(200)]
    assert 60 < firsts.count("verified") < 140  # not always the same position
    one, two, is_one, is_two = rs.shuffled_pair(random.Random(1), "verified text", "plain text")
    assert {one, two} == {"verified text", "plain text"} and {is_one, is_two} == {"verified", "plain"}


def test_the_sheet_columns_say_nothing_about_which_explanation_is_which():
    assert not [f for f in rs.SHEET_FIELDS if "verif" in f or "plain" in f]
    assert "explanation_1_is" not in rs.SHEET_FIELDS and "explanation_1_is" in rs.KEY_FIELDS


def test_there_are_at_least_twenty_distinct_submissions_for_more_than_ten_problems():
    assert len(rs.SUBMISSIONS) >= 20 and len({code for _, code in rs.SUBMISSIONS}) == len(rs.SUBMISSIONS)
    assert len({title for title, _ in rs.SUBMISSIONS}) == len(rs.SUBMISSIONS)


def test_scores_are_computed_per_flow_with_the_key_applied():
    keys = [key(1, "verified"), key(2, "plain")]
    # submission 1: explanation 1 is the verified one; submission 2: explanation 1 is the plain one
    sheet = [row(1, "1", "0", "1", "0"), row(2, "0", "1", "0", "1")]
    result = rs.compute(sheet, keys)
    assert result["verified"]["r1"] == "2 of 2 = 100%" and result["plain"]["r1"] == "0 of 2 = 0%"
    assert result["verified"]["both"] == "2 of 2 = 100%" and result["plain"]["both"] == "0 of 2 = 0%"
    assert result["agreement"] == 1.0 and result["rated_pairs"] == 4 and result["unrated_explanations"] == 0


def test_disagreement_and_missing_ratings_are_reported_not_hidden():
    keys = [key(1, "verified"), key(2, "verified")]
    sheet = [row(1, "1", "1", "0", "1"), row(2, "1", "0", "", "")]
    result = rs.compute(sheet, keys)
    # explanation 1 of submission 1: reviewers disagree (1 vs 0); explanation 2: agree (1 and 1); submission 2 has no second rating
    assert result["agreement"] == 0.5 and result["rated_pairs"] == 2 and result["unrated_explanations"] == 2
    assert result["verified"]["r2"] == "0 of 1 = 0%" and result["plain"]["r2"] == "1 of 1 = 100%"
    assert result["verified"]["r1"] == "2 of 2 = 100%"  # reviewer 1 rated both verified explanations
    assert result["plain"]["both"] == "1 of 1 = 100%" and result["verified"]["both"] == "no ratings yet"
    text = rs.report(result)
    assert "Reviewer agreement" in text and "not yet rated" in text


def test_an_empty_sheet_says_there_are_no_ratings_instead_of_inventing_numbers():
    result = rs.compute([row(1)], [key(1, "verified")])
    assert result["verified"]["r1"] == "no ratings yet" and result["agreement"] is None
    assert "n/a" in rs.report(result)


class FakeRater:
    def __init__(self, provider, answers):
        self.config = type("C", (), {"provider": provider, "model": "m"})()
        self.answers, self.seen = answers, []

    def complete(self, system, user, json_schema=None):
        self.seen.append(user)
        return self.answers.pop(0)


def test_llm_panel_fills_the_columns_labels_the_rows_and_leaves_unreadable_answers_blank(tmp_path, monkeypatch):
    import csv

    from app.llm import adapter

    raters = [FakeRater("groq", ["RATING: 1 fine", "**RATING: 0** wrong"]), FakeRater("mistral", ["RATING: 1", "I think it is ok"])]
    monkeypatch.setattr(adapter, "build_adapter", lambda settings: raters.pop(0))
    sheet = tmp_path / "s.csv"
    with open(sheet, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rs.SHEET_FIELDS)
        writer.writeheader()
        writer.writerow({f: "x" for f in rs.SHEET_FIELDS} | {"r1_exp1": "", "r1_exp2": "", "r2_exp1": "", "r2_exp2": "", "notes": ""})
    out = tmp_path / "o.csv"
    rs.llm_rate(str(sheet), str(out), ["groq", "mistral"])
    row = next(csv.DictReader(open(out, encoding="utf-8", newline="")))
    assert (row["r1_exp1"], row["r1_exp2"], row["r2_exp1"], row["r2_exp2"]) == ("1", "0", "1", "")
    assert row["notes"].startswith("LLM-rated, not human") and "groq:m" in row["notes"]
