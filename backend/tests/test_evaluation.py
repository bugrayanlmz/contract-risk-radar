import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.metrics import measure, summarize  # noqa: E402
from evals.run import load_contracts  # noqa: E402


def test_ground_truth_and_perfect_reference():
    contracts = load_contracts()
    assert len(contracts) == 21
    assert [item["id"] for item in contracts[:12]] == [f"eval-{index:02}" for index in range(1, 13)]
    assert sum(item["language"] == "german" for item in contracts) == 6
    assert sum("ai_findings" in item for item in contracts) == 9
    rows = [measure(item["text"], item["clauses"], item["clauses"]) for item in contracts]
    result = summarize(rows)
    assert (
        result["clause_recall"]
        == result["category_accuracy"]
        == result["quote_verification_rate"]
        == 1
    )
    assert len(result["by_category"]) == 7


def test_matching_is_one_to_one_category_independent_and_not_fuzzy():
    text = "The tenant owes all remaining rent."
    gold = [{"category": "EARLY_TERMINATION", "quote": text, "start": 0, "end": len(text)}]
    result = measure(
        text,
        [
            {"category": "LATE_PAYMENT", "quote": text},
            {"category": "EARLY_TERMINATION", "quote": text},
            {"category": "EARLY_TERMINATION", "quote": "The tenant owes the rest of the rent."},
        ],
        gold,
    )
    assert (
        result["matched"] == 1 and result["verified"] == 2 and result["unmatched_predictions"] == 2
    )
    assert result["correct_category"] == 0  # Matching never favors the correct category.


def test_additional_evidence_is_measured_separately():
    contracts = [item for item in load_contracts() if "ai_findings" in item]
    rows = [measure(item["text"], item["ai_findings"], item["ai_findings"]) for item in contracts]
    assert summarize(rows)["clause_recall"] == 1
    assert summarize(rows)["quote_verification_rate"] == 1


async def test_runner_separates_ai_scores_and_keeps_failures_in_denominator(monkeypatch):
    from app.config import Settings
    from evals.run import evaluate
    from tests.helpers import FakeProvider
    from tests.test_hybrid import finding

    contract = next(item for item in load_contracts() if item["id"] == "eval-13")
    gold = contract["ai_findings"][0]
    monkeypatch.setattr(
        "evals.run.create_provider",
        lambda settings: FakeProvider(
            clauses=[],
            ai_findings=[
                finding(title=gold["title"], quote=gold["quote"], model_score=gold["model_score"])
            ],
        ),
    )
    report = await evaluate(Settings(llm_provider="claude", llm_model="fixture-model"), [contract])
    assert report["ai_assessment_summary"]["clause_recall"] == 1
    assert report["ai_score_reference_mean_absolute_error"] == 0
    assert report["summary"]["clause_recall"] == 0
    assert report["ai_annotated_contracts"] == 1
    assert report["contracts"][0]["token_usage"]["input_tokens"] == 90
    monkeypatch.setattr("evals.run.create_provider", lambda settings: FakeProvider(fail_ai=True))
    report = await evaluate(Settings(llm_provider="claude", llm_model="fixture-model"), [contract])
    assert report["failed_runs"] == 1
    assert report["ai_assessment_summary"]["gold"] == 1
    assert report["ai_assessment_summary"]["clause_recall"] == 0
