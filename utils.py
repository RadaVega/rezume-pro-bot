#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 Вспомогательные функции для Резюме.Про
- Чтение PDF/DOCX
- Парсинг HH.ru
- Генерация PDF
"""

import os
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document
from fpdf import FPDF
import tempfile
import logging

logger = logging.getLogger(__name__)

# === ЧТЕНИЕ ФАЙЛОВ ===

def read_pdf(file_path: str) -> str:
    """Извлекает текст из PDF файла"""
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Ошибка чтения PDF: {e}")
        return ""

def read_docx(file_path: str) -> str:
    """Извлекает текст из DOCX файла"""
    try:
        doc = Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Ошибка чтения DOCX: {e}")
        return ""

def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Извлекает текст из файла в зависимости от типа"""
    if file_type.lower() == 'pdf':
        return read_pdf(file_path)
    elif file_type.lower() in ['docx', 'doc']:
        return read_docx(file_path)
    else:
        logger.error(f"❌ Неизвестный тип файла: {file_type}")
        return ""

# === ПАРСИНГ HH.RU ===

def parse_hh_vacancy(url: str) -> str:
    """
    Получает вакансию с HH.ru через официальный публичный API.
    Поддерживает ссылки вида: https://hh.ru/vacancy/12345678
    """
    try:
        import re as _re
        match = _re.search(r'hh\.ru/vacancy/(\d+)', url)
        if not match:
            return "Не удалось извлечь ID вакансии из ссылки. Убедись, что ссылка вида https://hh.ru/vacancy/12345678"

        vacancy_id = match.group(1)
        api_url = f"https://api.hh.ru/vacancies/{vacancy_id}"

        headers = {
            'User-Agent': 'ResumePro-Bot/1.0 (rubyalbe@school21.ru)'
        }

        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        title = data.get('name', '')
        company = data.get('employer', {}).get('name', '')

        # Описание приходит в HTML — очищаем теги
        description_html = data.get('description', '')
        description = BeautifulSoup(description_html, 'html.parser').get_text('\n', strip=True)

        # Ключевые навыки
        skills = ', '.join(s.get('name', '') for s in data.get('key_skills', []))

        # Опыт и занятость
        experience = data.get('experience', {}).get('name', '')
        employment = data.get('employment', {}).get('name', '')

        vacancy_text = f"""НАЗВАНИЕ ВАКАНСИИ: {title}
КОМПАНИЯ: {company}
ОПЫТ: {experience}
ЗАНЯТОСТЬ: {employment}
КЛЮЧЕВЫЕ НАВЫКИ: {skills}

ОПИСАНИЕ:
{description}""".strip()

        logger.info(f"✅ Получена вакансия через API: {title} ({company})")
        return vacancy_text

    except Exception as e:
        logger.error(f"❌ Ошибка получения вакансии с HH.ru: {e}")
        return f"Ошибка при получении вакансии: {str(e)}"

# === ГЕНЕРАЦИЯ PDF ===

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTS_AVAILABLE = os.path.exists(FONT_REGULAR) and os.path.exists(FONT_BOLD)

def generate_resume_pdf(resume_text: str, output_path: str):
    """
    Генерирует PDF файл с адаптированным резюме.
    Шрифты регистрируются ДО add_page(), чтобы header() их нашёл.
    """
    try:
        pdf = FPDF()

        # Регистрируем шрифты ПЕРЕД add_page()
        if FONTS_AVAILABLE:
            pdf.add_font('DejaVu', '', FONT_REGULAR)
            pdf.add_font('DejaVu', 'B', FONT_BOLD)
            font_name = 'DejaVu'
            logger.info("✅ Шрифт DejaVu загружен")
        else:
            font_name = 'Helvetica'
            logger.warning("⚠️ Шрифт DejaVu не найден, используем Helvetica")

        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Заголовок
        pdf.set_font(font_name, 'B', 18)
        pdf.set_fill_color(41, 128, 185)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 12, 'АДАПТИРОВАННОЕ РЕЗЮМЕ', new_x='LMARGIN', new_y='NEXT', align='C', fill=True)
        pdf.ln(4)
        pdf.set_text_color(0, 0, 0)

        # Текст по секциям
        sections = resume_text.split('\n\n')
        for section in sections:
            section = section.strip()
            if not section:
                continue

            lines = section.split('\n')
            first_line = lines[0].strip()

            # Заголовок секции — строка с эмодзи или полностью заглавная
            is_heading = (
                any(e in first_line for e in ['📋', '📊', '💡', '✅', '⚠️'])
                or first_line.isupper()
            )

            if is_heading:
                pdf.set_font(font_name, 'B', 13)
                pdf.set_fill_color(220, 235, 255)
                pdf.cell(0, 9, first_line, new_x='LMARGIN', new_y='NEXT', fill=True)
                pdf.ln(1)
                body = '\n'.join(lines[1:]).strip()
                if body:
                    pdf.set_font(font_name, '', 11)
                    pdf.multi_cell(0, 6, body)
                    pdf.ln(2)
            else:
                pdf.set_font(font_name, '', 11)
                pdf.multi_cell(0, 6, section)
                pdf.ln(2)

        # Нижний колонтитул
        pdf.set_y(-15)
        pdf.set_font(font_name, '', 8)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 10, f'Страница {pdf.page_no()} | Резюме.Про AI', align='C')

        pdf.output(output_path)
        logger.info(f"✅ PDF сохранён: {output_path}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка генерации PDF: {e}")
        return False

def create_resume_pdf(resume_text: str, output_path: str):
    """Алиас для generate_resume_pdf — используется в main.py"""
    return generate_resume_pdf(resume_text, output_path)

def create_simple_pdf(resume_text: str, output_path: str):
    """
    Упрощённая версия генерации PDF (без сложных шрифтов)
    """
    try:
        from fpdf import FPDF
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Заголовок
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "ADAPTED RESUME", 0, 1, 'C')
        pdf.ln(5)
        
        # Текст резюме
        pdf.set_font("Arial", size=11)
        for line in resume_text.split('\n'):
            pdf.cell(0, 7, line.encode('latin-1', 'replace').decode('latin-1'), 0, 1)
        
        pdf.output(output_path)
        logger.info(f"✅ PDF сохранён: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации PDF: {e}")
        return False
