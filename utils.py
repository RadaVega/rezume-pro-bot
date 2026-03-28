#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 ResumePro AI - Utilities
✅ FIXED: Dictionary-based Cyrillic transliteration (no maketrans length issue)
✅ Cyrillic-safe PDF generation
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

logger = logging.getLogger(__name__)

# === MARKDOWN CLEANING ===


def clean_markdown(text):
    """Remove ALL markdown formatting"""
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
    """Remove emojis - cause PDF encoding errors"""
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


# === FILE READING ===


def read_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text.strip()
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
        return text.strip()
    except Exception as e:
        logger.error(f"DOCX read error: {e}")
        return ""


def extract_text_from_file(file_path, file_type):
    if file_type.lower() == "pdf":
        return read_pdf(file_path)
    elif file_type.lower() in ["docx", "doc"]:
        return read_docx(file_path)
    return ""


# === HH.RU PARSING ===


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
            "\n", strip=True
        )
        skills = ", ".join(s.get("name", "") for s in data.get("key_skills", []))
        experience = data.get("experience", {}).get("name", "")
        employment = data.get("employment", {}).get("name", "")
        return f"VACANCY: {title}\nCOMPANY: {company}\nEXPERIENCE: {experience}\nEMPLOYMENT: {employment}\nSKILLS: {skills}\n\nDESCRIPTION:\n{description}"
    except Exception as e:
        logger.error(f"HH.ru error: {e}")
        return f"Error: {str(e)}"


# === CYRILLIC TRANSLITERATION (DICTIONARY-BASED) ===

CYR_DICT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
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
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Е": "E",
    "Ё": "Yo",
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
    "Х": "Kh",
    "Ц": "Ts",
    "Ч": "Ch",
    "Ш": "Sh",
    "Щ": "Shch",
    "Ъ": "",
    "Ы": "Y",
    "Ь": "",
    "Э": "E",
    "Ю": "Yu",
    "Я": "Ya",
}


def transliterate(text):
    """Convert Cyrillic to Latin using dictionary (supports multi-char mappings)"""
    result = []
    for char in text:
        result.append(CYR_DICT.get(char, char))
    return "".join(result)


# === PDF GENERATION (CYRILLIC-SAFE) ===


def create_resume_pdf(resume_text, output_path):
    """
    ✅ CYRILLIC-SAFE PDF GENERATION
    - Dictionary-based transliteration (no maketrans length issue)
    - Uses standard Helvetica font (always available)
    - Professional styling with colors
    """
    try:
        # Clean and transliterate
        clean_text = clean_markdown(resume_text)
        clean_text = remove_emojis(clean_text)
        pdf_text = transliterate(clean_text)

        pdf = FPDF()
        pdf.add_page()

        # === HEADER (Blue) ===
        pdf.set_fill_color(41, 128, 185)
        pdf.rect(0, 0, 210, 35, "F")

        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 12)
        pdf.cell(210, 10, "ADAPTED RESUME", 0, 1, "C")

        pdf.set_font("Helvetica", "", 9)
        pdf.set_xy(0, 24)
        pdf.cell(210, 8, "Created by ResumePro AI", 0, 1, "C")

        pdf.ln(40)
        pdf.set_text_color(0, 0, 0)

        # === CONTENT ===
        lines = pdf_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue

            # Section headers
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
                pdf.set_text_color(41, 128, 185)
                pdf.set_fill_color(236, 240, 241)
                pdf.cell(0, 7, line, 0, 1, "L", fill=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 10)

            # Match Score - orange
            elif "MATCH SCORE" in line.upper():
                pdf.ln(3)
                pdf.set_fill_color(230, 126, 34)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(255, 255, 255)
                pdf.multi_cell(0, 5, line, 0, "L", fill=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 10)

            # Recommendations - gray
            elif "RECOMMENDATIONS" in line.upper():
                pdf.ln(3)
                pdf.set_fill_color(236, 240, 241)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(41, 128, 185)
                pdf.cell(0, 6, line, 0, 1, "L", fill=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 9)

            # Bullet points
            elif line.startswith("-") or line.startswith("•"):
                pdf.set_font("Helvetica", "", 10)
                bullet = line.lstrip("-").lstrip("•").strip()
                pdf.cell(3, 5, "-", 0, 0)
                pdf.multi_cell(0, 5, bullet, 0, "L")

            # Regular text
            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(0, 5, line, 0, "L")

        # === FOOTER ===
        pdf.set_y(-15)
        pdf.set_fill_color(41, 128, 185)
        pdf.rect(0, 282, 210, 15, "F")

        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 287)
        pdf.cell(210, 6, f"Page {pdf.page_no()} | ResumePro AI", 0, 1, "C")

        # Save
        pdf.output(output_path)

        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info(f"✅ PDF created: {output_path} ({size} bytes)")
            return True
        return False

    except Exception as e:
        logger.error(f"❌ PDF error: {e}")
        return False


# Aliases
def generate_resume_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)


def create_simple_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)
