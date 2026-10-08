"""Synthetic evidence-layout fixture; never an evaluation contract or a user document."""

from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

font = Path(reportlab.__file__).parent / "fonts/Vera.ttf"
pdfmetrics.registerFont(TTFont("FixtureVera", str(font)))
path = Path(__file__).resolve().parents[1] / "frontend/e2e/assets/evidence-layout.pdf"
canvas = Canvas(str(path), pagesize=(612, 792), invariant=True)
canvas.setTitle("Synthetic PDF evidence layout fixture")
canvas.setAuthor("Contract Risk Radar")


def line(text, y, x=50):
    canvas.setFont("FixtureVera", 12)
    canvas.drawString(x, y, text)


line("Synthetic evidence layout fixture", 735)
line("Contract analysis demo. Not legal advice.", 710)
line("The lease automatically renews for twelve months.", 650)
line("Der Mieter haftet unbegrenzt für alle Schäden.", 590)
line("A ﬁnancial obligation remains.", 530)
canvas.showPage()
line("The lease automatically renews for twelve months.", 730)
line("„Die Überwa-", 650)
line("chung der Straße ist vorgeschrieben.“", 630)
line("The tenant must pay", 50)
canvas.showPage()
line("unlimited extra charges.", 750)
line("This fixture spans four pages for browser navigation tests.", 660)
canvas.showPage()
canvas.setPageRotation(90)
line("A rotated notice requires monthly inspection.", 450)
canvas.showPage()
canvas.save()
print(path)
