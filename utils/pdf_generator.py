# utils/pdf_generator.py
"""
Converts plain text to a PDF file using fpdf2 with Cyrillic support.
Compatible with fpdf2 >= 2.7.
"""

import os
import tempfile
import logging

logger = logging.getLogger(__name__)

_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "fonts", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/DejaVuSans.ttf",
]


def _find_font() -> str:
    for path in _FONT_CANDIDATES:
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved):
            return resolved
    raise FileNotFoundError(
        "DejaVuSans.ttf not found. Put it in bot/fonts/ or install dejavu-fonts."
    )


def text_to_pdf(text: str, title: str = "Документ") -> str:
    """
    Convert plain text to a PDF file with Cyrillic support.
    Returns the path to a temporary PDF file (caller must delete it).
    """
    from fpdf import FPDF

    font_path = _find_font()

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(left=20, top=20, right=20)

    pdf.add_font("DejaVu", style="", fname=font_path)
    pdf.set_font("DejaVu", size=13)

    # Title — use ln=1 (deprecated but universally compatible across 2.x)
    eff_w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(eff_w, 10, title)
    pdf.ln(3)

    pdf.set_font("DejaVu", size=10)

    for line in text.split("\n"):
        clean = line.rstrip()
        pdf.set_x(pdf.l_margin)
        if not clean:
            pdf.ln(4)
        else:
            pdf.multi_cell(eff_w, 6, clean)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="resumepro_")
    tmp.close()
    pdf.output(tmp.name)

    size_kb = os.path.getsize(tmp.name) // 1024
    logger.info("📄 PDF created: '%s' → %s (%d KB)", title, tmp.name, size_kb)
    return tmp.name
