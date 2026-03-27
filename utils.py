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

def parse_hh_vacancy(url: str) -> dict:
    """
    Парсит вакансию с HH.ru
    Возвращает: название, компания, описание, требования
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Извлекаем данные
        vacancy_data = {
            'title': '',
            'company': '',
            'description': '',
            'requirements': '',
            'full_text': ''
        }
        
        # Заголовок вакансии
        title_tag = soup.find('h1', {'data-qa': 'vacancy-title'})
        if title_tag:
            vacancy_data['title'] = title_tag.text.strip()
        
        # Компания
        company_tag = soup.find('a', {'data-qa': 'vacancy-company-name'})
        if company_tag:
            vacancy_data['company'] = company_tag.text.strip()
        
        # Описание и требования
        description_div = soup.find('div', {'data-qa': 'vacancy-description'})
        if description_div:
            vacancy_data['description'] = description_div.get_text('\n', strip=True)
        
        # Полный текст (если не нашли по data-qa)
        if not vacancy_data['description']:
            # Пробуем найти по классам
            main_content = soup.find('div', class_='vacancy-description')
            if main_content:
                vacancy_data['full_text'] = main_content.get_text('\n', strip=True)
            else:
                # Если совсем ничего не нашли — берём весь текст страницы
                vacancy_data['full_text'] = soup.get_text('\n', strip=True)[:3000]
        
        # Формируем итоговый текст
        vacancy_text = f"""
НАЗВАНИЕ ВАКАНСИИ: {vacancy_data['title']}
КОМПАНИЯ: {vacancy_data['company']}

ОПИСАНИЕ:
{vacancy_data['description'] or vacancy_data['full_text']}

ТРЕБОВАНИЯ:
{vacancy_data['requirements']}
""".strip()
        
        logger.info(f"✅ Спарсено вакансию: {vacancy_data['title']}")
        return vacancy_text
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга HH.ru: {e}")
        return f"Ошибка при парсинге вакансии: {str(e)}"

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
