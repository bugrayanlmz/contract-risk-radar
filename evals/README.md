# Held-out synthetic evaluation

The original `eval-01` through `eval-12` PDFs and their authored evidence remain preserved. `eval-13` through `eval-18` are German; `eval-19` through `eval-21` are English. All are fictional residential rental contracts. Source quotations/categories and the nine new cases' additional-AI annotations are manually authored in `contracts.json`. `ground_truth.json` contains exact normalized offsets materialized from the rendered PDFs.

New cases include German dates/amounts, business days, conflicting rent, missing facts, benign terms, instructions embedded in untrusted contract text, overlapping rule/AI evidence, and obligations outside the seven scoring rules. AI reference scores reflect a human-authored practical-impact rubric; they are not legal correctness labels. Empty AI ground truth lists are explicit negative examples. The original twelve have no AI annotations, so their AI output is not scored against empty assumed labels.

Use `PYTHONPATH=backend backend/.venv/bin/python -m evals.run --validate` from the repository root. To measure providers, configure keys and use `--provider both --claude-model MODEL --gemini-model MODEL`. The runner imports no API/database code. All nine requests must succeed for a completed run. Failed runs stay in recall denominators.

Rule extraction and additional AI assessments are reported separately. Exact verified spans match one-to-one by IoU ≥ 0.5, independent of category; recall, matched category attribution, verification rate, counts, unmatched predictions, failures, per-contract latency/token usage, versions, and matched AI score-reference absolute errors are recorded. No live benchmark results are bundled or invented.

After reviewing authored labels, render only new evaluation PDFs with `backend/.venv/bin/python scripts/build_contracts.py --only-new`. Never use a real uploaded contract in this corpus or tune prompts/rules to these held-out annotations.

Contract analysis demo. Not legal advice.
