"""Render the authored synthetic contracts and materialize human-selected evidence spans.

Run from repository root: backend/.venv/bin/python scripts/build_contracts.py
The evaluation labels and quotations are authored explicitly in evals/contracts.json;
this script computes only their offsets in the rendered PDF's normalized text.
"""

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.analysis.evidence import normalize_text  # noqa: E402
from app.analysis.pdf import extract_pdf  # noqa: E402
from app.config import Settings  # noqa: E402

INK = colors.HexColor("#173f48")
TEXT = colors.HexColor("#40575b")
DISCLAIMER = "Contract analysis demo. Not legal advice."


def render(path, title, paragraphs, language="english"):
    title_style = ParagraphStyle(
        "Title", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=INK, spaceAfter=18
    )
    body = ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=10.5,
        leading=17,
        textColor=TEXT,
        spaceAfter=13,
        alignment=TA_LEFT,
    )
    eyebrow = ParagraphStyle(
        "Eyebrow",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#66897e"),
        spaceAfter=12,
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbe6df"))
        canvas.line(54, 50, 558, 50)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#829a8e"))
        canvas.drawString(54, 35, DISCLAIMER)
        canvas.drawRightString(558, 35, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=(612, 792),
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=72,
        title=title,
        author="Contract Risk Radar - synthetic demo",
    )
    story = [
        Paragraph("CONTRACT RISK RADAR / SYNTHETIC EXAMPLE", eyebrow),
        Paragraph(escape(title), title_style),
        Paragraph(
            (
                "Dies ist ein frei erfundener Wohnraummietvertrag ausschließlich für Softwaretests."
                if language == "german"
                else "This is a fictional residential rental contract created solely for software demonstration and evaluation."
            ),
            body,
        ),
        Spacer(1, 0.1 * inch),
    ]
    story.extend(Paragraph(escape(paragraph), body) for paragraph in paragraphs)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only-new",
        action="store_true",
        help="Preserve existing PDFs and render only new evaluation cases.",
    )
    args = parser.parse_args()
    samples = json.loads((ROOT / "samples/contracts.json").read_text())
    for name, contract in samples.items():
        if not args.only_new:
            render(ROOT / f"samples/{name}.pdf", contract["title"], contract["paragraphs"])
    eval_dir = ROOT / "evals/contracts"
    eval_dir.mkdir(exist_ok=True)
    gold = []
    for contract in json.loads((ROOT / "evals/contracts.json").read_text()):
        paragraphs = [
            contract["context"],
            *[clause["quote"] for clause in contract["clauses"]],
            *dict.fromkeys(
                item["quote"]
                for item in contract.get("ai_findings", [])
                if item["quote"] not in {clause["quote"] for clause in contract["clauses"]}
            ),
        ]
        if contract.get("untrusted_text"):
            paragraphs.insert(1, contract["untrusted_text"])
        path = eval_dir / f"{contract['id']}.pdf"
        if not args.only_new or not path.exists():
            render(path, contract["title"], paragraphs, contract.get("language", "english"))
        text, _ = extract_pdf(path.read_bytes(), Settings())
        normalized = normalize_text(text)
        clauses = []
        for clause in contract["clauses"]:
            quote = normalize_text(clause["quote"])
            start = normalized.index(quote)
            clauses.append({**clause, "start": start, "end": start + len(quote)})
        entry = {
            "id": contract["id"],
            "pdf": f"contracts/{contract['id']}.pdf",
            "clauses": clauses,
            "language": contract.get("language", "english"),
        }
        if "ai_findings" in contract:
            entry["ai_findings"] = []
            for item in contract["ai_findings"]:
                quote = normalize_text(item["quote"])
                start = normalized.index(quote)
                entry["ai_findings"].append({**item, "start": start, "end": start + len(quote)})
        gold.append(entry)
        (eval_dir / f"{contract['id']}.txt").write_text("\n\n".join(paragraphs) + "\n")
    (ROOT / "evals/ground_truth.json").write_text(json.dumps(gold, indent=2) + "\n")
    print(f"Created {len(samples)} demo PDFs and {len(gold)} evaluation PDFs.")


if __name__ == "__main__":
    main()
