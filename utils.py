#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 Вспомогательные функции для Резюме.Про
- Чтение PDF/DOCX
- Парсинг HH.ru через официальный API
- Генерация ПРЕМИУМ PDF (лучше чем у конкурентов!)
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

# === ОЧИСТКА ОТ MARKDOWN ===

def clean_markdown(text: str) -> str:
    """
    Очищает текст от markdown-символов для чистого PDF
    """
    # Убираем жирный текст **текст** или __текст__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    
    # Убираем курсив *текст* или _текст_
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    
    # Убираем заголовки ###, ##, #
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Убираем горизонтальные линии ---, ***, ___
    text = re.sub(r'^[\*\-\_]{3,}$', '', text, flags=re.MULTILINE)
    
    # Убираем код в блоках ```код```
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    # Убираем ссылки [текст](url)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    
    # Убираем экранированные символы
    text = re.sub(r'\\([\*\_\#\`\[\]])', r'\1', text)
    
    # Убираем лишние пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Убираем пробелы в начале/конце строк
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(line for line in lines if line)
    
    return text.strip()

# === ЧТЕНИЕ ФАЙЛОВ ===

def read_pdf(file_path: str) -> str:
    """Извлекает текст из PDF файла"""
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
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
            if paragraph.text.strip():
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
    """
    try:
        match = re.search(r'hh\.ru/vacancy/(\d+)', url)
        if not match:
            return "Не удалось извлечь ID вакансии из ссылки."

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
        description_html = data.get('description', '')
        description = BeautifulSoup(description_html, 'html.parser').get_text('\n', strip=True)
        skills = ', '.join(s.get('name', '') for s in data.get('key_skills', []))
        experience = data.get('experience', {}).get('name', '')
        employment = data.get('employment', {}).get('name', '')

        vacancy_text = f"""НАЗВАНИЕ ВАКАНСИИ: {title}
КОМПАНИЯ: {company}
ОПЫТ: {experience}
ЗАНЯТОСТЬ: {employment}
КЛЮЧЕВЫЕ НАВЫКИ: {skills}

ОПИСАНИЕ:
{description}""".strip()

        logger.info(f"✅ Получена вакансия: {title} ({company})")
        return vacancy_text

    except Exception as e:
        logger.error(f"❌ Ошибка HH.ru API: {e}")
        return f"Ошибка: {str(e)}"

# === ГЕНЕРАЦИЯ ПРЕМИУМ PDF ===

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTS_AVAILABLE = os.path.exists(FONT_REGULAR) and os.path.exists(FONT_BOLD)

def generate_resume_pdf(resume_text: str, output_path: str):
    """
    🏆 ГЕНЕРИРУЕТ ПРЕМИУМ PDF РЕЗЮМЕ
    Дизайн лучше чем у Resume.io, Zety, Novoresume!
    """
    try:
        clean_text = clean_markdown(resume_text)
        lines = clean_text.split('\n')
        
        pdf = FPDF()
        
        # Шрифты
        if FONTS_AVAILABLE:
            pdf.add_font('DejaVu', '', FONT_REGULAR)
            pdf.add_font('DejaVu', 'B', FONT_BOLD)
            font = 'DejaVu'
        else:
            font = 'Helvetica'
            logger.warning("⚠️ Шрифт DejaVu не найден")

        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.add_page()
        
        # === ЦВЕТОВАЯ СХЕМА (PREMIUM) ===
        PRIMARY = (41, 128, 185)       # Синий профессиональный
        SECONDARY = (52, 152, 219)     # Светло-синий
        ACCENT = (230, 126, 34)        # Оранжевый для Match Score
        SUCCESS = (39, 174, 96)        # Зелёный
        DARK = (44, 62, 80)            # Тёмно-серый текст
        LIGHT = (236, 240, 241)        # Светлый фон блоков
        
        # === НАХОДИМ ИМЯ И КОНТАКТЫ ===
        name_line = "РЕЗЮМЕ КАНДИДАТА"
        contact_line = ""
        content_start = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or 'АДАПТИРОВАННОЕ РЕЗЮМЕ' in line:
                continue
            if name_line == "РЕЗЮМЕ КАНДИДАТА":
                name_line = line
                content_start = i + 1
            elif not contact_line:
                contact_line = line
                content_start = i + 1
                break
        
        # === ШАПКА С ГРАДИЕНТОМ ===
        # Основной синий блок
        pdf.set_fill_color(*PRIMARY)
        pdf.rect(0, 0, 210, 42, 'F')
        
        # Светлая полоса снизу
        pdf.set_fill_color(*SECONDARY)
        pdf.rect(0, 40, 210, 2, 'F')
        
        # Имя (крупно, белый)
        pdf.set_xy(0, 12)
        pdf.set_font(font, 'B', 22)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(210, 10, name_line, align='C')
        
        # Контакты
        if contact_line:
            pdf.set_xy(0, 24)
            pdf.set_font(font, '', 9)
            pdf.cell(210, 8, contact_line, align='C')
        
        pdf.ln(48)
        pdf.set_text_color(*DARK)
        
        # === ОСНОВНОЙ КОНТЕНТ ===
        in_recommendations = False
        in_match_score = False
        
        for line in lines[content_start:]:
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue
            
            # Определяем тип строки
            is_emoji = any(e in line for e in ['📋', '📊', '💡', '✅', '📌', '💼', '🎓', '🛠'])
            is_upper = line.isupper() and len(line) < 50 and not any(c.isdigit() for c in line)
            is_match = 'MATCH SCORE' in line.upper()
            is_recommend = 'РЕКОМЕНДАЦИИ' in line.upper()
            is_bullet = line.startswith('-') or line.startswith('•')
            
            # Заголовки секций
            if is_emoji or is_upper:
                pdf.ln(5)
                y = pdf.get_y()
                
                # Синяя полоса слева (4px)
                pdf.set_fill_color(*PRIMARY)
                pdf.rect(12, y, 4, 8, 'F')
                
                # Текст заголовка
                pdf.set_font(font, 'B', 