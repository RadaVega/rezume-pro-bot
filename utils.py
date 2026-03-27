#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 ResumePro AI - PDF Generation
✅ FIXED: Unicode errors, emojis, text truncation
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
    """Remove emojis - they cause encoding errors"""
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub(r"", text)


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
        logger.error(f"PDF error: {e}")
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
        logger.error(f"DOCX error: {e}")
        return ""


def extract_text_from_file(file_path, file_type):
    if file_type.lower() == "pdf":
        return read_pdf(file_path)
    elif file_type.lower() in ["docx", "doc"]:
        return read_docx(file_path)
    return ""


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
        return f"ВАКАНСИЯ: {title}\nКОМПАНИЯ: {company}\nОПЫТ: {experience}\nЗАНЯТОСТЬ: {employment}\nНАВЫКИ: {skills}\n\nОПИСАНИЕ:\n{description}"
    except Exception as e:
        logger.error(f"HH.ru error: {e}")
        return f"Error: {str(e)}"


# === ✅ PROFESSIONAL PDF - NO EMOJIS, PROPER ENCODING ===


def create_resume_pdf(resume_text, output_path):
    """
    🏆 GENERATES PROFESSIONAL PDF
    - Removes emojis (cause encoding errors)
    - Uses DejaVu fonts for Cyrillic
    - Proper text wrapping
    """
    try:
        clean_text = clean_markdown(resume_text)
        clean_text = remove_emojis(clean_text)  # Remove emojis

        pdf = FPDF()
        pdf.add_page()

        # Use DejaVu fonts for Cyrillic support
        font_family = "Arial"  # Default fallback
        try:
            font_path = "/usr/share/fonts/truetype/dejavu"
            if os.path.exists(font_path):
                pdf.add_font("DejaVu", "", f"{font_path}/DejaVuSans.ttf", uni=True)
                pdf.add_font(
                    "DejaVu", "B", f"{font_path}/DejaVuSans-Bold.ttf", uni=True
                )
                pdf.add_font(
                    "DejaVu", "I", f"{font_path}/DejaVuSans-Oblique.ttf", uni=True
                )
                font_family = "DejaVu"
                logger.info("✅ Using DejaVu fonts for Cyrillic")
            else:
                logger.warning("⚠️ DejaVu fonts not found, using Arial")
        except Exception as e:
            logger.warning(f"⚠️ Font error: {e}, using Arial")

        # === HEADER ===
        pdf.set_fill_color(41, 128, 185)  # Blue
        pdf.rect(0, 0, 210, 35, "F")

        pdf.set_font(font_family, "B", 20)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 12)
        pdf.cell(210, 10, "ADAPTED RESUME", 0, 1, "C")

        pdf.set_font(font_family, "", 10)
        pdf.set_xy(0, 24)
        pdf.cell(210, 8, "Created by ResumePro AI", 0, 1, "C")

        pdf.ln(40)
        pdf.set_text_color(0, 0, 0)

        # === CONTENT ===
        lines = clean_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue

            # Section headers (no emojis now)
            if any(
                word in line.upper()
                for word in [
                    "PROFILE",
                    "EXPERIENCE",
                    "EDUCATION",
                    "SKILLS",
                    "MATCH",
                    "RECOMMENDATIONS",
                    "ПРОФИЛЬ",
                    "ОПЫТ",
                    "ОБРАЗОВАНИЕ",
                    "НАВЫКИ",
                    "РЕКОМЕНДАЦИИ",
                ]
            ):
                pdf.ln(5)
                pdf.set_font(font_family, "B", 12)
                pdf.set_text_color(41, 128, 185)  # Blue
                pdf.set_fill_color(236, 240, 241)  # Light gray
                # Safe encoding
                safe_line = line.encode("latin-1", "replace").decode("latin-1")
                pdf.cell(0, 8, safe_line, 0, 1, "L", fill=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font(font_family, "", 10)

            # Match Score - orange highlight
            elif "MATCH SCORE" in line.upper():
                pdf.ln(4)
                pdf.set_fill_color(230, 126, 34)  # Orange
                pdf.set_font(font_family, "B", 11)
                pdf.set_text_color(255, 255, 255)
                safe_line = line.encode("latin-1", "replace").decode("latin-1")
                pdf.multi_cell(0, 6, safe_line, 0, "L", fill=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font(font_family, "", 10)

            # Recommendations
            elif "RECOMMENDATIONS" in line.upper() or "РЕКОМЕНДАЦИИ" in line.upper():
                pdf.ln(4)
                pdf.set_fill_color(236, 240, 241)  # Light gray
                pdf.set_font(font_family, "B", 11)
                pdf.set_text_color(41, 128, 185)
                safe_line = line.encode("latin-1", "replace").decode("latin-1")
                pdf.cell(0, 7, safe_line, 0, 1, "L", fill=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font(font_family, "", 9)

            # Bullet points
            elif line.startswith("-") or line.startswith("•"):
                pdf.set_font(font_family, "", 10)
                bullet_text = line.lstrip("-").lstrip("•").strip()
                safe_text = bullet_text.encode("latin-1", "replace").decode("latin-1")
                pdf.cell(3, 6, "-", 0, 0)  # Use dash instead of bullet
                pdf.multi_cell(0, 5, safe_text, 0, "L")

            # Regular text with wrapping
            else:
                pdf.set_font(font_family, "", 10)
                safe_line = line.encode("latin-1", "replace").decode("latin-1")
                pdf.multi_cell(0, 5, safe_line, 0, "L")

        # === FOOTER ===
        pdf.set_y(-15)
        pdf.set_fill_color(41, 128, 185)
        pdf.rect(0, 282, 210, 15, "F")

        pdf.set_font(font_family, "I", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 287)
        pdf.cell(210, 6, f"Page {pdf.page_no()} | ResumePro AI", 0, 1, "C")

        # Save PDF
        pdf.output(output_path)

        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info(f"✅ PDF created: {output_path} ({size} bytes)")
            return True
        else:
            logger.error("❌ PDF file not created!")
            return False

    except Exception as e:
        logger.error(f"❌ PDF generation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


# Aliases
def generate_resume_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)


def create_simple_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)
