#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ResumePro AI - Utilities
Professional PDF with Cyrillic (DejaVu) + HH.ru API parsing
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document
from fpdf import FPDF
import logging

logger = logging.getLogger(__name__)

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Design palette
C_NAVY   = (22, 55, 100)
C_WHITE  = (255, 255, 255)
C_DARK   = (30,  30,  30)
C_GRAY   = (100, 100, 100)
C_LINE   = (200, 210, 225)
C_GREEN  = (34, 139, 34)
C_LIGHT  = (245, 248, 252)


# ── Markdown / emoji cleaning ─────────────────────────────────────────────────

def clean_markdown(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__',     r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'^#{1,6}\s*',    '',    text, flags=re.MULTILINE)
    text = re.sub(r'^[\*\-\_]{3,}$','',    text, flags=re.MULTILINE)
    text = re.sub(r'```[\s\S]*?```','',    text)
    text = re.sub(r'`(.+?)`',       r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'\n{3,}',        '\n\n', text)
    return text.strip()

def remove_emojis(text):
    pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U000024C2-\U0001F251]+",
        flags=re.UNICODE
    )
    return pattern.sub('', text)


# ── File reading (keeps Russian intact) ───────────────────────────────────────

def read_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        return "\n".join(p.extract_text() or "" for p in reader.pages).strip()
    except Exception as e:
        logger.error(f"PDF read error: {e}")
        return ""

def read_docx(file_path):
    try:
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    except Exception as e:
        logger.error(f"DOCX read error: {e}")
        return ""

def extract_text_from_file(file_path, file_type):
    ft = file_type.lower()
    if ft == "pdf":
        return read_pdf(file_path)
    elif ft in ("docx", "doc"):
        return read_docx(file_path)
    return ""


# ── HH.ru vacancy parser (keeps Russian intact) ───────────────────────────────

def parse_hh_vacancy(url):
    try:
        m = re.search(r'hh\.ru/vacancy/(\d+)', url)
        if not m:
            return "Некорректная ссылка HH.ru"
        vacancy_id = m.group(1)
        r = requests.get(
            f"https://api.hh.ru/vacancies/{vacancy_id}",
            headers={"User-Agent": "ResumePro-Bot/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()

        title    = d.get("name", "")
        company  = d.get("employer", {}).get("name", "")
        exp      = d.get("experience", {}).get("name", "")
        emp_type = d.get("employment", {}).get("name", "")
        skills   = ", ".join(s.get("name", "") for s in d.get("key_skills", []))
        desc     = BeautifulSoup(d.get("description", ""), "html.parser").get_text(" ", strip=True)

        sal = d.get("salary")
        sal_text = ""
        if sal:
            fr  = sal.get("from") or ""
            to  = sal.get("to") or ""
            cur = sal.get("currency", "")
            sal_text = f"{fr}–{to} {cur}".strip("–").strip()

        logger.info(f"✅ Получена вакансия через API: {title} ({company})")
        return (
            f"ВАКАНСИЯ: {title}\n"
            f"КОМПАНИЯ: {company}\n"
            f"ОПЫТ: {exp}\n"
            f"ЗАНЯТОСТЬ: {emp_type}\n"
            f"ЗАРПЛАТА: {sal_text}\n"
            f"КЛЮЧЕВЫЕ НАВЫКИ: {skills}\n\n"
            f"ОПИСАНИЕ ВАКАНСИИ:\n{desc}"
        )
    except Exception as e:
        logger.error(f"HH.ru error: {e}")
        return f"Ошибка загрузки вакансии: {e}"


# ── Professional PDF generator ────────────────────────────────────────────────

class ResumePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("Regular", "",  FONT_REGULAR)
        self.add_font("Regular", "B", FONT_BOLD)
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)
        self._header_name  = ""
        self._header_title = ""

    def header(self):
        # Navy header bar
        self.set_fill_color(*C_NAVY)
        self.rect(0, 0, 210, 38, "F")
        # Name
        self.set_font("Regular", "B", 20)
        self.set_text_color(*C_WHITE)
        self.set_xy(0, 8)
        self.cell(210, 10, self._header_name, align="C", new_x="LMARGIN", new_y="NEXT")
        # Job title
        self.set_font("Regular", "", 11)
        self.set_xy(0, 20)
        self.cell(210, 7, self._header_title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*C_DARK)
        self.set_y(44)

    def footer(self):
        self.set_y(-12)
        self.set_font("Regular", "", 7)
        self.set_text_color(*C_GRAY)
        self.cell(0, 5, f"Страница {self.page_no()} | ResumePro AI — адаптировано под вакансию", align="C")
        self.set_text_color(*C_DARK)

    def section_title(self, title):
        self.ln(4)
        self.set_font("Regular", "B", 10)
        self.set_text_color(*C_NAVY)
        self.cell(0, 6, title.upper(), new_x="LMARGIN", new_y="NEXT")
        # Underline
        self.set_draw_color(*C_LINE)
        self.set_line_width(0.4)
        x = self.get_x()
        y = self.get_y()
        self.line(x, y, 210 - 18, y)
        self.ln(3)
        self.set_text_color(*C_DARK)

    def contact_bar(self, contacts_line):
        self.set_font("Regular", "", 8.5)
        self.set_text_color(*C_GRAY)
        self.set_fill_color(*C_LIGHT)
        self.rect(0, 38, 210, 6, "F")
        self.set_xy(0, 38.5)
        self.cell(210, 5, contacts_line, align="C")
        self.set_text_color(*C_DARK)
        self.set_y(46)

    def body_text(self, text, indent=0):
        self.set_font("Regular", "", 9.5)
        self.set_x(self.l_margin + indent)
        self.multi_cell(0, 5.5, text)

    def bullet(self, text):
        self.set_font("Regular", "", 9.5)
        x = self.l_margin + 4
        y = self.get_y()
        self.set_xy(self.l_margin + 2, y)
        self.set_text_color(*C_NAVY)
        self.cell(4, 5.5, "•")
        self.set_text_color(*C_DARK)
        self.set_x(x + 2)
        self.multi_cell(0, 5.5, text)

    def job_header(self, title, company_dates):
        self.set_font("Regular", "B", 9.5)
        self.set_text_color(*C_DARK)
        self.multi_cell(0, 5.5, title)
        self.set_font("Regular", "", 8.5)
        self.set_text_color(*C_GRAY)
        self.multi_cell(0, 5, company_dates)
        self.set_text_color(*C_DARK)

    def match_box(self, score_line, details):
        self.ln(3)
        self.set_fill_color(*C_LIGHT)
        y_start = self.get_y()
        self.rect(self.l_margin, y_start, 174, 1, "F")
        self.set_font("Regular", "B", 10)
        self.set_text_color(*C_GREEN)
        self.cell(0, 7, score_line, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Regular", "", 9)
        self.set_text_color(*C_DARK)
        if details:
            self.multi_cell(0, 5, details)


# ── Section parser ─────────────────────────────────────────────────────────────

SECTION_TAGS = {
    "ИМЯ":          r"===\s*ИМЯ\s*===",
    "ДОЛЖНОСТЬ":    r"===\s*ДОЛЖНОСТЬ\s*===",
    "КОНТАКТЫ":     r"===\s*КОНТАКТЫ\s*===",
    "ПРОФИЛЬ":      r"===\s*ПРОФИЛЬ\s*===",
    "ОПЫТ":         r"===\s*ОПЫТ\s*===",
    "ОБРАЗОВАНИЕ":  r"===\s*ОБРАЗОВАНИЕ\s*===",
    "НАВЫКИ":       r"===\s*НАВЫКИ\s*===",
    "MATCH":        r"===\s*MATCH\s*===",
    "РЕКОМЕНДАЦИИ": r"===\s*РЕКОМЕНДАЦИИ\s*===",
}

def parse_sections(text):
    """Extract tagged sections from GigaChat output."""
    sections = {}
    tag_positions = []

    for key, pattern in SECTION_TAGS.items():
        for m in re.finditer(pattern, text, re.IGNORECASE):
            tag_positions.append((m.start(), m.end(), key))

    tag_positions.sort()

    for i, (start, end, key) in enumerate(tag_positions):
        next_start = tag_positions[i + 1][0] if i + 1 < len(tag_positions) else len(text)
        content = text[end:next_start].strip()
        sections[key] = content

    return sections


def create_resume_pdf(resume_text, output_path):
    """
    Generate a professional, Cyrillic-ready resume PDF.
    Expects GigaChat output with === SECTION === markers.
    Falls back gracefully if markers are missing.
    """
    try:
        text = remove_emojis(clean_markdown(resume_text))
        sections = parse_sections(text)

        logger.info(f"📄 PDF sections found: {list(sections.keys())}")

        # Extract key fields
        name      = sections.get("ИМЯ", "").strip() or "Резюме"
        job_title = sections.get("ДОЛЖНОСТЬ", "").strip()
        contacts  = sections.get("КОНТАКТЫ", "").strip()
        profile   = sections.get("ПРОФИЛЬ", "").strip()
        exp_block = sections.get("ОПЫТ", "").strip()
        edu_block = sections.get("ОБРАЗОВАНИЕ", "").strip()
        skills    = sections.get("НАВЫКИ", "").strip()
        match     = sections.get("MATCH", "").strip()
        recs      = sections.get("РЕКОМЕНДАЦИИ", "").strip()

        pdf = ResumePDF()
        pdf._header_name  = name
        pdf._header_title = job_title
        pdf.add_page()

        # Contact bar
        if contacts:
            pdf.contact_bar(contacts)
        else:
            pdf.set_y(46)

        # PROFESSIONAL PROFILE
        if profile:
            pdf.section_title("Профессиональный профиль")
            pdf.body_text(profile)

        # WORK EXPERIENCE
        if exp_block:
            pdf.section_title("Опыт работы")
            _render_experience(pdf, exp_block)

        # EDUCATION
        if edu_block:
            pdf.section_title("Образование")
            _render_simple_block(pdf, edu_block)

        # SKILLS
        if skills:
            pdf.section_title("Ключевые навыки")
            _render_skills(pdf, skills)

        # MATCH SCORE
        if match:
            pdf.section_title("ATS Match Score")
            lines = match.strip().splitlines()
            score_line = lines[0] if lines else match
            details    = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
            pdf.match_box(score_line, details)

        # RECOMMENDATIONS
        if recs:
            pdf.section_title("Рекомендации по улучшению")
            _render_bullets(pdf, recs)

        # Fallback: if no sections found, just dump the text cleanly
        if not sections:
            logger.warning("⚠️ No section tags found — using plain text fallback")
            pdf.section_title("Адаптированное резюме")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    pdf.ln(2)
                elif line.startswith(("-", "•", "*")):
                    pdf.bullet(line.lstrip("-•* "))
                else:
                    pdf.body_text(line)

        pdf.output(output_path)
        size = os.path.getsize(output_path)
        logger.info(f"✅ PDF created: {output_path} ({size} bytes)")
        return True

    except Exception as e:
        logger.error(f"❌ PDF error: {e}")
        import traceback; traceback.print_exc()
        return False


def _render_experience(pdf, block):
    """Render work experience entries."""
    entries = re.split(r'\n(?=\S)', block)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        lines = entry.splitlines()
        header_lines = []
        bullet_lines = []
        for ln in lines:
            ln = ln.strip()
            if ln.startswith(("-", "•", "*")):
                bullet_lines.append(ln.lstrip("-•* "))
            elif ln:
                header_lines.append(ln)
        if header_lines:
            title_line   = header_lines[0]
            company_line = " | ".join(header_lines[1:]) if len(header_lines) > 1 else ""
            pdf.job_header(title_line, company_line)
        for b in bullet_lines:
            pdf.bullet(b)
        pdf.ln(3)


def _render_simple_block(pdf, block):
    """Render a plain text block, detecting bullets."""
    for line in block.splitlines():
        line = line.strip()
        if not line:
            pdf.ln(2)
        elif line.startswith(("-", "•", "*")):
            pdf.bullet(line.lstrip("-•* "))
        else:
            pdf.body_text(line)


def _render_bullets(pdf, block):
    """Render a block where every non-empty line is a bullet."""
    for line in block.splitlines():
        line = line.strip().lstrip("-•* ")
        if line:
            pdf.bullet(line)


def _render_skills(pdf, block):
    """Render skills — comma-separated or line-based."""
    skills_list = [s.strip() for s in re.split(r'[,;\n]', block) if s.strip()]
    # Wrap into rows of ~4
    row = []
    rows = []
    for s in skills_list:
        row.append(s)
        if len(row) == 4:
            rows.append("   •   ".join(row))
            row = []
    if row:
        rows.append("   •   ".join(row))
    for r in rows:
        pdf.body_text(r)


# Aliases kept for backward compatibility
def generate_resume_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)

def create_simple_pdf(resume_text, output_path):
    return create_resume_pdf(resume_text, output_path)
