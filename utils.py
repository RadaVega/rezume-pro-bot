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

class ResumePDF(FPDF):
    """Класс для генерации PDF резюме"""
    
    def header(self):
        """Шапка PDF"""
        self.set_font('DejaVu', 'B', 20)
        self.cell(0, 10, 'АДАПТИРОВАННОЕ РЕЗЮМЕ', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        """Подвал PDF"""
        self.set_y(-15)
        self.set_font('DejaVu', 'I', 8)
        self.cell(0, 10, f'Страница {self.page_no()}', 0, 0, 'C')
    
    def chapter_title(self, title):
        """Заголовок раздела"""
        self.set_font('DejaVu', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(3)
    
    def chapter_body(self, body):
        """Текст раздела"""
        self.set_font('DejaVu', '', 11)
        self.multi_cell(0, 7, body)
        self.ln(3)

def generate_resume_pdf(resume_text: str, output_path: str):
    """
    Генерирует PDF файл с адаптированным резюме
    
    Args:
        resume_text: Текст адаптированного резюме
        output_path: Путь для сохранения PDF
    """
    try:
        pdf = ResumePDF()
        pdf.add_page()
        
        # Добавляем шрифт DejaVu (поддерживает кириллицу)
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if os.path.exists(font_path):
            pdf.add_font('DejaVu', '', font_path, uni=True)
            pdf.add_font('DejaVu', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', uni=True)
            pdf.add_font('DejaVu', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf', uni=True)
        else:
            # Если шрифта нет — используем стандартный (кириллица может не работать)
            logger.warning("⚠️ Шрифт DejaVu не найден, используем стандартный")
            pdf.set_font("Arial", size=12)
        
        # Разбиваем текст на секции
        sections = resume_text.split('\n\n')
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            # Определяем заголовок (строки с эмодзи или заглавные)
            lines = section.split('\n')
            if lines:
                first_line = lines[0].strip()
                
                # Если строка начинается с эмодзи или заглавная — это заголовок
                if any(emoji in first_line for emoji in ['📋', '📊', '💡', '✅']) or first_line.isupper():
                    pdf.chapter_title(first_line)
                    if len(lines) > 1:
                        pdf.chapter_body('\n'.join(lines[1:]))
                else:
                    pdf.chapter_body(section)
        
        # Сохраняем PDF
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
