from app.analysis.evidence import normalize_text, verify_quote


def quote_spans(quote: str, text: str) -> list[tuple[int, int]]:
    quote, text = normalize_text(quote), normalize_text(text)
    if not quote:
        return []
    spans, offset = [], 0
    while (start := text.find(quote, offset)) >= 0:
        spans.append((start, start + len(quote)))
        offset = start + 1
    return spans


def intersection_over_union(a, b):
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return intersection / union if union else 0


def measure(text, predictions, gold):
    # Maximum-cardinality bipartite matching, independent of predicted category.
    # Edges are exact verified spans meeting the fixed IoU threshold, never fuzzy text matches.
    edges, verified = {}, []
    for index, prediction in enumerate(predictions):
        valid = verify_quote(prediction["quote"], text)
        verified.append(valid)
        spans = quote_spans(prediction["quote"], text) if valid else []
        candidates = []
        for gold_index, expected in enumerate(gold):
            overlap = max(
                (
                    intersection_over_union(span, (expected["start"], expected["end"]))
                    for span in spans
                ),
                default=0,
            )
            if overlap >= 0.5:
                candidates.append((gold_index, overlap))
        edges[index] = [
            gold_index for gold_index, _ in sorted(candidates, key=lambda pair: (-pair[1], pair[0]))
        ]
    matches = {}

    def augment(predicted, visited):
        for expected in edges[predicted]:
            if expected in visited:
                continue
            visited.add(expected)
            if expected not in matches or augment(matches[expected], visited):
                matches[expected] = predicted
                return True
        return False

    for index in range(len(predictions)):
        augment(index, set())
    correct = sum(
        predictions[predicted]["category"] == gold[expected]["category"]
        for expected, predicted in matches.items()
    )
    counts = {}
    for index, expected in enumerate(gold):
        category = expected["category"]
        row = counts.setdefault(category, {"gold": 0, "matched": 0, "correct_category": 0})
        row["gold"] += 1
        if index in matches:
            row["matched"] += 1
            row["correct_category"] += predictions[matches[index]]["category"] == category
    confusion = [
        {"gold": gold[expected]["category"], "predicted": predictions[predicted]["category"]}
        for expected, predicted in sorted(matches.items())
    ]
    return {
        "gold": len(gold),
        "returned": len(predictions),
        "verified": sum(verified),
        "matched": len(matches),
        "correct_category": correct,
        "unmatched_predictions": len(predictions) - len(matches),
        "by_category": counts,
        "category_pairs": confusion,
        "matched_pairs": [
            {"gold": expected, "predicted": predicted}
            for expected, predicted in sorted(matches.items())
        ],
    }


def summarize(rows):
    keys = ("gold", "returned", "verified", "matched", "correct_category", "unmatched_predictions")
    totals = {key: sum(row[key] for row in rows) for key in keys}
    categories = {}
    for row in rows:
        for category, counts in row["by_category"].items():
            target = categories.setdefault(
                category, {"gold": 0, "matched": 0, "correct_category": 0}
            )
            for key, value in counts.items():
                target[key] += value

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    return {
        **totals,
        "clause_recall": ratio(totals["matched"], totals["gold"]),
        "category_accuracy": ratio(totals["correct_category"], totals["matched"]),
        "quote_verification_rate": ratio(totals["verified"], totals["returned"]),
        "by_category": categories,
    }
