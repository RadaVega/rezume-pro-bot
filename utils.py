#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 Вспомогательные функции для Резюме.Про
- Чтение PDF/DOCX
- Парсинг HH.ru
- Генерация ПРЕМИУМ PDF
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

# === ОЧИСТКА MARKDOWN ===


def clean_markdown(text):
    """Удаляет все markdown символы"""
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


# === ЧТЕНИЕ ФАЙЛОВ ===


def read_pdf(file_path):
    """Извлекает текст из PDF"""
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
    """Извлекает текст из DOCX"""
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
    """Извлекает текст из файла"""
    if file_type.lower() == "pdf":
        return read_pdf(file_path)
    elif file_type.lower() in ["docx", "doc"]:
        return read_docx(file_path)
    return ""


# === ПАРСИНГ HH.RU ===


def parse_hh_vacancy(url):
    """Парсит вакансию с HH.ru API"""
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


# === ГЕНЕРАЦИЯ PDF ===

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTS_AVAILABLE = os.path.exists(FONT_REGULAR) and os.path.exists(FONT_BOLD)


def generate_resume_pdf(resume_text, output_path):
    """
    🏆 ГЕНЕРИРУЕТ ПРЕМИУМ PDF
    Дизайн как в Adapted_Resume1.pdf
    """
    try:
        clean_text = clean_markdown(resume_text)
        lines = clean_text.split("\n")

        pdf = FPDF()

        # Шрифты
        font_loaded = False
        try:
            if FONTS_AVAILABLE:
                pdf.add_font("DejaVu", "", FONT_REGULAR, uni=True)
                pdf.add_font("DejaVu", "B", FONT_BOLD, uni=True)
                font = "DejaVu"
                font_loaded = True
                logger.info("✅ DejaVu fonts loaded")
        except Exception as font_err:
            logger.warning(f"⚠️ Font error: {font_err}")
            font_loaded = False

        if not font_loaded:
            font = "Arial"

        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.add_page()

        # Цвета
        PRIMARY = (41, 128, 185)
        DARK = (44, 62, 80)
        LIGHT = (236, 240, 241)
        ACCENT = (230, 126, 34)

        # Находим имя и контакты
        name_line = "РЕЗЮМЕ КАНДИДАТА"
        contact_line = ""
        content_start = 0

        for i, line in enumerate(lines):
            line = line.strip()
            if not line or "АДАПТИРОВАННОЕ РЕЗЮМЕ" in line:
                continue
            if name_line == "РЕЗЮМЕ КАНДИДАТА":
                name_line = line
                content_start = i + 1
            elif not contact_line:
                contact_line = line
                content_start = i + 1
                break

        # Шапка с синим фоном
        pdf.set_fill_color(*PRIMARY)
        pdf.rect(0, 0, 210, 42, "F")

        pdf.set_xy(0, 12)
        pdf.set_font(font, "B", 22)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(210, 10, name_line, align="C")

        if contact_line:
            pdf.set_xy(0, 24)
            pdf.set_font(font, "", 9)
            pdf.cell(210, 8, contact_line, align="C")

        pdf.ln(48)
        pdf.set_text_color(*DARK)

        # Основной контент
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
            is_recommend = "РЕКОМЕНДАЦИИ" in line.upper()
            is_bullet = line.startswith("-") or line.startswith("•")

            # Заголовки секций
            if is_emoji or is_upper:
                pdf.ln(5)
                y = pdf.get_y()

                # Синяя полоса слева
                pdf.set_fill_color(*PRIMARY)
                pdf.rect(12, y, 4, 8, "F")

                pdf.set_font(font, "B", 12)
                pdf.set_text_color(*PRIMARY)
                pdf.set_xy(20, y)
                pdf.cell(185, 8, line, align="L")
                pdf.ln(2)

                # Тонкая линия
                pdf.set_draw_color(*LIGHT)
                pdf.set_line_width(0.3)
                pdf.line(12, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(2)

                in_recommendations = is_recommend
                in_match_score = is_match

            # Match Score - оранжевый блок
            elif is_match or in_match_score:
                pdf.ln(4)
                y = pdf.get_y()

                pdf.set_fill_color(*ACCENT)
                pdf.rect(12, y, 188, 22, "F")

                pdf.set_font(font, "B", 13)
                pdf.set_text_color(255, 255, 255)
                pdf.set_xy(17, y + 3)

                for text_line in line.split("\n")[:2]:
                    pdf.cell(178, 6, text_line.strip(), align="L")
                    pdf.ln(6)

                pdf.ln(4)
                in_match_score = False

            # Рекомендации - серый блок
            elif is_recommend or in_recommendations:
                if is_recommend:
                    pdf.ln(3)
                    y = pdf.get_y()

                    pdf.set_fill_color(*LIGHT)
                    pdf.rect(12, y, 188, 8, "F")

                    pdf.set_font(font, "B", 11)
                    pdf.set_text_color(*PRIMARY)
                    pdf.set_xy(17, y + 2)
                    pdf.cell(188, 6, "💡 РЕКОМЕНДАЦИИ", align="L")
                    pdf.ln(7)
                    in_recommendations = True
                else:
                    pdf.set_font(font, "", 9)
                    pdf.set_text_color(60, 60, 60)
                    pdf.set_xy(17, pdf.get_y())

                    if is_bullet:
                        pdf.cell(4, 5, "•", align="L")
                        pdf.cell(
                            174, 5, line.lstrip("-").lstrip("•").strip(), align="L"
                        )
                    else:
                        pdf.cell(178, 5, line, align="L")
                    pdf.ln(5)

            # Bullet points
            elif is_bullet:
                pdf.set_font(font, "", 10)
                pdf.set_text_color(60, 60, 60)
                pdf.set_xy(17, pdf.get_y())
                pdf.cell(4, 5, "•", align="L")
                pdf.cell(174, 5, line.lstrip("-").lstrip("•").strip(), align="L")
                pdf.ln(5)

            # Опыт работы (с датой)
            elif "|" in line and any(
                y in line.upper() for y in ["201", "202", "НАСТОЯЩЕЕ", "CURRENT"]
            ):
                pdf.set_font(font, "B", 10)
                pdf.set_text_color(*DARK)
                pdf.multi_cell(0, 5, line)
                pdf.ln(1)

            # Обычный текст
            else:
                pdf.set_font(font, "", 10)
                pdf.set_text_color(70, 70, 70)
                pdf.multi_cell(0, 5, line)
                pdf.ln(1)

        # Подвал
        pdf.set_y(-15)
        pdf.set_fill_color(*PRIMARY)
        pdf.rect(0, 282, 210, 15, "F")

        pdf.set_font(font, "I", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(0, 287)
        pdf.cell(210, 6, f"Страница {pdf.page_no()} | Резюме.Про AI", align="C")

        pdf.output(output_path)

        # Проверяем что файл создан
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ PDF создан: {output_path} ({file_size} bytes)")
            return True
        else:
            logger.error("❌ PDF файл не создан!")
            return False

    except Exception as e:
        logger.error(f"❌ Ошибка генерации PDF: {e}")
        import traceback

        traceback.print_exc()
        return False


def create_resume_pdf(resume_text, output_path):
    """Алиас для generate_resume_pdf"""
    return generate_resume_pdf(resume_text, output_path)


def create_simple_pdf(resume_text, output_path):
    """Простая версия (резервная)"""
    try:
        clean_text = clean_markdown(resume_text)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "ADAPTED RESUME", 0, 1, "C")
        pdf.ln(5)
        pdf.set_font("Arial", size=11)
        for line in clean_text.split("\n"):
            safe_line = line.encode("latin-1", "replace").decode("latin-1")
            pdf.cell(0, 7, safe_line, 0, 1)
        pdf.output(output_path)
        return True
    except Exception as e:
        logger.error(f"Simple PDF error: {e}")
        return False
