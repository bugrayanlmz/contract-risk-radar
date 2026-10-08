"""Standalone evaluation; does not import API routes, queue, or database code."""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.analysis.evidence import normalize_text
from app.analysis.pdf import AnalysisError, extract_pdf
from app.analysis.pipeline import PROMPT_VERSION, analyze_text
from app.analysis.scoring import RULES_VERSION
from app.config import Settings
from app.providers.factory import create_provider
from app.schemas.extraction import AI_RUBRIC_VERSION, SCHEMA_VERSION, AiFindingBatch, ContractFacts
from evals.metrics import measure, summarize

ROOT = Path(__file__).resolve().parent


class RecordingProvider:
    def __init__(self, provider):
        self.provider, self.predictions, self.ai_predictions = provider, [], []
        self.token_usage = {"input_tokens": 0, "output_tokens": 0}

    async def extract(self, text, instruction, response_model):
        response = await self.provider.extract(text, instruction, response_model)
        for key in self.token_usage:
            self.token_usage[key] += response.token_usage.get(key, 0)
        if response_model is AiFindingBatch:
            self.ai_predictions.extend(
                {
                    **finding.model_dump(mode="json"),
                    "category": finding.related_category.value
                    if finding.related_category
                    else "ADDITIONAL",
                }
                for finding in response.data.findings
            )
        elif response_model is not ContractFacts:
            self.predictions.extend(
                clause.model_dump(mode="json") for clause in response.data.clauses
            )
        return response


def load_contracts():
    contracts = json.loads((ROOT / "ground_truth.json").read_text())
    settings = Settings()
    for contract in contracts:
        text, warnings = extract_pdf((ROOT / contract["pdf"]).read_bytes(), settings)
        normalized = normalize_text(text)
        for clause in [*contract["clauses"], *contract.get("ai_findings", [])]:
            if normalized[clause["start"] : clause["end"]] != normalize_text(clause["quote"]):
                raise ValueError(
                    f"Ground truth is stale for {contract['id']}; regenerate after reviewing changed source contracts."
                )
        contract["text"], contract["warnings"] = text, warnings
    return contracts


async def evaluate(settings, contracts):
    provider = create_provider(settings)
    ai_rows = []
    rows, usage = [], {"input_tokens": 0, "output_tokens": 0}
    for contract in contracts:
        started = time.perf_counter()
        recording = RecordingProvider(provider)
        try:
            await analyze_text(contract["text"], uuid4(), recording, contract["warnings"])
            row = measure(contract["text"], recording.predictions, contract["clauses"])
            row["status"] = "completed"
        except AnalysisError as error:
            # Failed contracts remain in the recall denominator; no successful-run-only result.
            row = measure(contract["text"], recording.predictions, contract["clauses"])
            row["matched"] = row["correct_category"] = 0
            row["unmatched_predictions"] = row["returned"]
            row["category_pairs"] = row["matched_pairs"] = []
            for category in row["by_category"].values():
                category["matched"] = category["correct_category"] = 0
            row.update(status="failed", error_code=error.code)
        if "ai_findings" in contract:
            ai_row = measure(contract["text"], recording.ai_predictions, contract["ai_findings"])
            if row["status"] == "failed":
                ai_row["matched"] = ai_row["correct_category"] = 0
                ai_row["unmatched_predictions"] = ai_row["returned"]
                ai_row["category_pairs"] = ai_row["matched_pairs"] = []
                for counts in ai_row["by_category"].values():
                    counts["matched"] = counts["correct_category"] = 0
            # A manual practical-impact reference, never a legal accuracy label.
            errors = [
                abs(
                    recording.ai_predictions[pair["predicted"]]["model_score"]
                    - contract["ai_findings"][pair["gold"]]["model_score"]
                )
                for pair in ai_row["matched_pairs"]
            ]
            ai_row["score_reference_errors"] = errors
            ai_rows.append(ai_row)
            row["ai_assessment"] = ai_row
        row["ai_evaluation_available"] = "ai_findings" in contract
        row["ai_returned"] = len(recording.ai_predictions)
        row["token_usage"] = recording.token_usage
        row["language"] = contract.get("language", "english")
        for key in usage:
            usage[key] += recording.token_usage[key]
        row.update(id=contract["id"], seconds=round(time.perf_counter() - started, 3))
        rows.append(row)
        print(f"{settings.llm_provider} {contract['id']}: {row['status']} ({row['seconds']}s)")
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "summary": summarize(rows),
        "ai_rubric_version": AI_RUBRIC_VERSION,
        "ai_assessment_summary": summarize(ai_rows),
        "ai_annotated_contracts": len(ai_rows),
        "ai_score_reference_mean_absolute_error": (
            sum(error for row in ai_rows for error in row["score_reference_errors"])
            / sum(len(row["score_reference_errors"]) for row in ai_rows)
        )
        if any(row["score_reference_errors"] for row in ai_rows)
        else None,
        "failed_runs": sum(row["status"] == "failed" for row in rows),
        "total_seconds": sum(row["seconds"] for row in rows),
        "token_usage": usage,
        "contracts": rows,
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Compare clause extraction on 21 held-out synthetic rental contracts."
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate PDFs and gold evidence without calling providers.",
    )
    parser.add_argument("--provider", choices=["claude", "gemini", "both"], default="both")
    parser.add_argument("--claude-model")
    parser.add_argument("--gemini-model")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/comparison.json")
    args = parser.parse_args()
    contracts = load_contracts()
    if args.validate:
        print(
            f"Validated {len(contracts)} PDFs and {sum(len(item['clauses']) for item in contracts)} manually selected rule spans and {sum(len(item.get('ai_findings', [])) for item in contracts)} additional AI spans."
        )
        return
    settings = Settings()
    names = ["claude", "gemini"] if args.provider == "both" else [args.provider]
    configurations = []
    for name in names:
        model = getattr(args, f"{name}_model") or (
            settings.llm_model if settings.llm_provider == name else ""
        )
        if not model:
            parser.error(
                f"Specify --{name}-model or matching LLM_PROVIDER/LLM_MODEL configuration."
            )
        configuration = settings.model_copy(update={"llm_provider": name, "llm_model": model})
        create_provider(configuration)  # Validate credentials before starting either run.
        configurations.append(configuration)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "synthetic-rentals-v2",
        "iou_threshold": 0.5,
        "note": "Software extraction evaluation on synthetic data; not legal accuracy.",
        "providers": [await evaluate(configuration, contracts) for configuration in configurations],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
