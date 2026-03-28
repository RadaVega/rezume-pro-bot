#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 ResumePro AI - Utilities
✅ FINAL FIX: Aggressive Cyrillic removal + simple PDF
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document
from fpdf import FPDF
import tempfile
import logging
import unicodedata

logger = logging.getLogger(__name__)

# === MARKDOWN CLEANING ===


def clean_markdown(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\*\-\_]{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_emojis(text):
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"
        "\U0001f300-\U0001f5ff"
        "\U0001f680-\U0001f6ff"
        "\U0001f1e0-\U0001f1ff"
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub(r"", text)


# === AGGRESSIVE CYRILLIC REMOVAL ===


def to_ascii_safe(text):
    """
    Convert ANY text to ASCII-safe Latin characters only.
    Removes/transliterates Cyrillic, emojis, special chars.
    """
    # Step 1: Normalize Unicode
    text = unicodedata.normalize("NFKD", text)

    # Step 2: Remove diacritics (accents)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Step 3: Manual Cyrillic mapping (dictionary-based)
    cyr_map = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sh",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "u",
        "я": "ya",
        "А": "A",
        "Б": "B",
        "В": "V",
        "Г": "G",
        "Д": "D",
        "Е": "E",
        "Ё": "E",
        "Ж": "Zh",
        "З": "Z",
        "И": "I",
        "Й": "Y",
        "К": "K",
        "Л": "L",
        "М": "M",
        "Н": "N",
        "О": "O",
        "П": "P",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "У": "U",
        "Ф": "F",
        "Х": "H",
        "Ц": "C",
        "Ч": "Ch",
        "Ш": "Sh",
        "Щ": "Sh",
        "Ъ": "",
        "Ы": "Y",
        "Ь": "",
        "Э": "E",
        "Ю": "U",
        "Я": "Ya",
    }

    result = []
    for char in text:
        # Try dictionary mapping first
        if char in cyr_map:
            result.append(cyr_map[char])
        # Keep ASCII letters, digits, basic punctuation
        elif ord(char) < 128 and (
            char.isalnum() or char in " .,;:!?-()[]/\\@#%&*+=<>|_"
        ):
            result.append(char)
        # Skip everything else (Cyrillic, emojis, etc.)
        else:
            result.append(" ")

    # Step 4: Clean up extra spaces
    text = "".join(result)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# === FILE READING ===


def read_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return to_ascii_safe(text.strip())
    except Exception as e:
        logger.error(f"PDF read error: {e}")
        return ""


def read_docx(file_path):
    try:
        doc = Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text += paragraph.text + "\n"
        return to_ascii_safe(text.strip())
    except Exception as e:
        logger.error(f"DOCX read error: {e}")
        return ""


def extract_text_from_file(file_path, file_type):
    if file_type.lower() == "pdf":
        return read_pdf(file_path)
    elif file_type.lower() in ["docx", "doc"]:
        return read_docx(file_path)
    return ""


# === HH.RU PARSING (ASCII-Only Output) ===


def parse_hh_vacancy(url):
    try:
        match = re.search(r"hh\.ru/vacancy/(\d+)", url)
        if not match:
            return "Invalid HH.ru URL"
        vacancy_id = match.group(1)
        api_url = f"https://api.hh.ru/vacancies/{vacancy_id}"
        headers = {"User-Agent": "ResumePro-Bot/1.0"}
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        title = data.get("name", "")
        company = data.get("employer", {}).get("name", "")
        description_html = data.get("description", "")
        description = BeautifulSoup(description_html, "html.parser").get_text(
            " ", strip=True
        )
        skills = ", ".join(s.get("name", "") for s in data.get("key_skills", []))
        experience = data.get("experience", {}).get("name", "")
        employment = data.get("employment", {}).get("name", "")

        # Return ASCII-safe text
        return to_ascii_safe(
            f"VACANCY: {title}\nCOMPANY: {company}\nEXPERIENCE: {experience}\nEMPLOYMENT: {employment}\nSKILLS: {skills}\n\nDESCRIPTION:\n{description}"
        )
    except Exception as e:
        logger.error(f"HH.ru error: {e}")
        return f"Error: {str(e)}"


# === SIMPLE, BULLETPROOF PDF GENERATION ===


def create_resume_pdf(resume_text, output_path):
    """
    ✅ BULLETPROOF PDF: ASCII-only text, simple operations
    - Converts ALL input to ASCII-safe Latin
    - Uses only basic Helvetica font operations
    - No complex formatting that could fail
    """
    try:
        # Aggressively clean text to ASCII-only
        clean_text = clean_markdown(resume_text)
        clean_text = remove_emojis(clean_text)
        pdf_text = to_ascii_safe(clean_text)

        # Debug: log first 200 chars to verify ASCII
        logger.info(f"📄 PDF text sample: {pdf_text[:200]}")

        pdf = FPDF()
        pdf.add_page()

        # === SIMPLE HEADER ===
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "ADAPTED RESUME", 0, 1, "C")
        pdf.ln(3)

        # === CONTENT - Simple cell operations only ===
        lines = pdf_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue

            # Skip any line that might have non-ASCII (safety check)
            if any(ord(c) > 127 for c in line):
                continue

            # Section headers (simple)
            if any(
                word in line.upper()
                for word in [
                    "PROFILE",
                    "EXPERIENCE",
                    "EDUCATION",
                    "SKILLS",
                    "MATCH",
                    "RECOMMENDATIONS",
                ]
            ):
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 7, line, 0, 1)
                pdf.set_font("Helvetica", "", 10)

            # Match Score
            elif "MATCH SCORE" in line.upper():
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, line, 0, 1)
                pdf.set_font("Helvetica", "", 10)

            # Recommendations
            elif "RECOMMENDATIONS" in line.upper():
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, line, 0, 1)
                pdf.set_font("Helvetica", "", 9)

            # Bullet points - use simple cell, not multi_cell
            elif line.startswith("-"):
                pdf.set_font("Helvetica", "", 10)
                bullet = line[1:].strip()
                pdf.cell(3, 5, "-", 0, 0)
                pdf.cell(0, 5, bullet, 0, 1)

            # Regular text - use cell with auto-wrap simulation
            else:
                pdf.set_font("Helvetica", "", 10)
                # Break long lines manually to avoid multi_cell issues
                words = line.split()
                current_line = ""
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    # Approximate width check (Helvetica ~0.6mm per char at size 10)
                    if len(test_line) < 180:
                        current_line = test_line
                    else:
                        pdf.cell(0, 5, current_line, 0, 1)
                        current_line = word
                if current_line:
                    pdf.cell(0, 5, current_line, 0, 1)

        # === SIMPLE FOOTER ===
        pdf.ln(5)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 8, f"Page {pdf.page_no()} | ResumePro AI", 0, 1, "C")

        # Save PDF
        pdf.output(output_path)

        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info(f"✅ PDF created: {output_path} ({size} bytes)")
            return True
        return False

    except Exception as e:
        logger.error(f"❌ PDF error: {e}")
        import traceback

        traceback.print_exc()
        return False


# Aliases
def generate_resume_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)


def create_simple_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)
