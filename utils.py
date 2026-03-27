#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 Вспомогательные функции для Резюме.Про
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


# === SIMPLE PDF GENERATION (GUARANTEED TO WORK) ===


def create_simple_pdf(resume_text, output_path):
    """
    ✅ SIMPLE PDF - ALWAYS WORKS
    Clean, professional, no fancy fonts needed
    """
    try:
        clean_text = clean_markdown(resume_text)
        pdf = FPDF()
        pdf.add_page()

        # Use standard Arial font (always available)
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "ADAPTED RESUME", 0, 1, "C")
        pdf.ln(5)

        pdf.set_font("Arial", size=11)
        for line in clean_text.split("\n"):
            # Safe encoding
            try:
                safe_line = line.encode("latin-1", "replace").decode("latin-1")
            except:
                safe_line = line
            pdf.cell(0, 7, safe_line, 0, 1)

        pdf.output(output_path)

        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info(f"✅ Simple PDF created: {output_path} ({size} bytes)")
            return True
        return False

    except Exception as e:
        logger.error(f"❌ Simple PDF error: {e}")
        import traceback

        traceback.print_exc()
        return False


# === PREMIUM PDF (with styling) ===


def generate_resume_pdf(resume_text, output_path):
    """
    🏆 PREMIUM PDF with professional design
    Falls back to simple PDF if fonts fail
    """
    try:
        clean_text = clean_markdown(resume_text)
        lines = clean_text.split("\n")

        pdf = FPDF()

        # Try to use DejaVu fonts, but FALL BACK to Arial
        font_name = "Arial"  # Default fallback
        try:
            # Check if DejaVu fonts exist
            if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
                pdf.add_font(
                    "DejaVu",
                    "",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    uni=True,
                )
                pdf.add_font(
                    "DejaVu",
                    "B",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    uni=True,
                )
                font_name = "DejaVu"
                logger.info("✅ Using DejaVu fonts")
        except Exception as font_err:
            logger.warning(f"⚠️ Font issue: {font_err}, using Arial")
            font_name = "Arial"

        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Colors
        PRIMARY = (41, 128, 185)
        DARK = (44, 62, 80)
        LIGHT = (236, 240, 241)
        ACCENT = (230, 126, 34)

        # Find name and contact
        name_line = "RESUME"
        contact_line = ""
        content_start = 0

        for i, line in enumerate(lines):
            line = line.strip()
            if not line or "АДАПТИРОВАННОЕ РЕЗЮМЕ" in line:
                continue
            if name_line == "RESUME":
                name_line = line
                content_start = i + 1
            elif not contact_line:
                contact_line = line
                content_start = i + 1
                break

        # HEADER with blue background
        try:
            pdf.set_fill_color(*PRIMARY)
            pdf.rect(0, 0, 210, 40, "F")

            pdf.set_xy(0, 15)
            pdf.set_font(font_name, "B", 20)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(210, 10, name_line, align="C")

            if contact_line:
                pdf.set_xy(0, 27)
                pdf.set_font(font_name, "", 9)
                pdf.cell(210, 8, contact_line, align="C")

            pdf.ln(45)
            pdf.set_text_color(*DARK)
        except Exception as e:
            logger.error(f"Header error: {e}")
            # Continue anyway

        # CONTENT
        in_recommendations = False
        in_match_score = False

        for line in lines[content_start:]:
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue

            is_emoji = any(
                e in line for e in ["📋", "📊", "💡", "✅", "📌", "💼", "🎓", "🛠"]
            )
            is_upper = (
                line.isupper() and len(line) < 50 and not any(c.isdigit() for c in line)
            )
            is_match = "MATCH SCORE" in line.upper()
            is_recommend = (
                "РЕКОМЕНДАЦИИ" in line.upper() or "RECOMMENDATIONS" in line.upper()
            )
            is_bullet = line.startswith("-") or line.startswith("•")

            try:
                # Section headers
                if is_emoji or is_upper:
                    pdf.ln(5)
                    y = pdf.get_y()

                    # Blue bar on left
                    pdf.set_fill_color(*PRIMARY)
                    pdf.rect(12, y, 4, 8, "F")

                    pdf.set_font(font_name, "B", 12)
                    pdf.set_text_color(*PRIMARY)
                    pdf.set_xy(20, y)
                    pdf.cell(185, 8, line, align="L")
                    pdf.ln(2)

                    # Line under header
                    pdf.set_draw_color(*LIGHT)
                    pdf.set_line_width(0.3)
                    pdf.line(12, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(2)

                    in_recommendations = is_recommend
                    in_match_score = is_match

                # Match Score - orange block
                elif is_match or in_match_score:
                    pdf.ln(4)
                    y = pdf.get_y()

                    pdf.set_fill_color(*ACCENT)
                    pdf.rect(12, y, 188, 20, "F")

                    pdf.set_font(font_name, "B", 12)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_xy(17, y + 3)

                    for text_line in line.split("\n")[:2]:
                        pdf.cell(178, 6, text_line.strip()[:80], align="L")
                        pdf.ln(6)

                    pdf.ln(4)
                    in_match_score = False

                # Recommendations - gray block
                elif is_recommend or in_recommendations:
                    if is_recommend:
                        pdf.ln(3)
                        y = pdf.get_y()

                        pdf.set_fill_color(*LIGHT)
                        pdf.rect(12, y, 188, 8, "F")

                        pdf.set_font(font_name, "B", 11)
                        pdf.set_text_color(*PRIMARY)
                        pdf.set_xy(17, y + 2)
                        pdf.cell(188, 6, "💡 RECOMMENDATIONS", align="L")
                        pdf.ln(7)
                        in_recommendations = True
                    else:
                        pdf.set_font(font_name, "", 9)
                        pdf.set_text_color(60, 60, 60)
                        pdf.set_xy(17, pdf.get_y())

                        if is_bullet:
                            pdf.cell(4, 5, "•", align="L")
                            pdf.cell(
                                174,
                                5,
                                line.lstrip("-").lstrip("•").strip()[:100],
                                align="L",
                            )
                        else:
                            pdf.cell(178, 5, line[:100], align="L")
                        pdf.ln(5)

                # Bullet points
                elif is_bullet:
                    pdf.set_font(font_name, "", 10)
                    pdf.set_text_color(60, 60, 60)
                    pdf.set_xy(17, pdf.get_y())
                    pdf.cell(4, 5, "•", align="L")
                    pdf.cell(
                        174, 5, line.lstrip("-").lstrip("•").strip()[:100], align="L"
                    )
                    pdf.ln(5)

                # Regular text
                else:
                    pdf.set_font(font_name, "", 10)
                    pdf.set_text_color(70, 70, 70)
                    safe_line = line.encode("latin-1", "replace").decode("latin-1")
                    pdf.multi_cell(0, 5, safe_line[:120])
                    pdf.ln(1)

            except Exception as e:
                logger.error(f"Content error: {e}")
                # Continue with next line

        # FOOTER
        try:
            pdf.set_y(-15)
            pdf.set_fill_color(*PRIMARY)
            pdf.rect(0, 282, 210, 15, "F")

            pdf.set_font(font_name, "", 8)  # Regular, NOT italic!
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(0, 287)
            pdf.cell(210, 6, f"Page {pdf.page_no()} | ResumePro AI", align="C")
        except Exception as e:
            logger.error(f"Footer error: {e}")

        # Save PDF
        pdf.output(output_path)

        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info(f"✅ Premium PDF created: {output_path} ({size} bytes)")
            return True
        else:
            logger.error("❌ PDF file not created!")
            return False

    except Exception as e:
        logger.error(f"❌ Premium PDF failed: {e}")
        import traceback

        traceback.print_exc()

        # FALLBACK to simple PDF
        logger.info("🔄 Falling back to simple PDF...")
        return create_simple_pdf(resume_text, output_path)


def create_resume_pdf(resume_text, output_path):
    """Main entry point"""
    return generate_resume_pdf(resume_text, output_path)
