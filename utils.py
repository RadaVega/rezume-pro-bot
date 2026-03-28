#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ResumePro AI — Utilities
Professional Cyrillic PDF + robust section parser + HH.ru API
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

FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY    = (22,  55, 100)
WHITE   = (255, 255, 255)
DARK    = (25,  25,  25)
GRAY    = (110, 110, 110)
LGRAY   = (235, 240, 248)
ACCENT  = (52, 120, 196)   # lighter blue for accent bar
LINE_C  = (195, 210, 230)
GREEN   = (34, 139, 34)
BG_ALT  = (248, 250, 253)


# ── Text utilities ────────────────────────────────────────────────────────────

def clean_markdown(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__',     r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'^#{1,6}\s*',    '',    text, flags=re.MULTILINE)
    text = re.sub(r'^[-_*]{3,}$',   '',    text, flags=re.MULTILINE)
    text = re.sub(r'```[\s\S]*?```','',    text)
    text = re.sub(r'`(.+?)`',       r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'\n{3,}',        '\n\n', text)
    return text.strip()

def remove_emojis(text):
    return re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
        r'\U00002702-\U000027B0\U000024C2-\U0001F251]+',
        '', text, flags=re.UNICODE)


# ── File readers ──────────────────────────────────────────────────────────────

def read_pdf(path):
    try:
        r = PdfReader(path)
        return "\n".join(p.extract_text() or "" for p in r.pages).strip()
    except Exception as e:
        logger.error(f"PDF read: {e}"); return ""

def read_docx(path):
    try:
        d = Document(path)
        return "\n".join(p.text for p in d.paragraphs if p.text.strip()).strip()
    except Exception as e:
        logger.error(f"DOCX read: {e}"); return ""

def extract_text_from_file(path, ftype):
    ft = ftype.lower()
    if ft == "pdf":   return read_pdf(path)
    if ft in ("docx","doc"): return read_docx(path)
    return ""


# ── HH.ru parser ──────────────────────────────────────────────────────────────

def parse_hh_vacancy(url):
    try:
        m = re.search(r'hh\.ru/vacancy/(\d+)', url)
        if not m: return "Некорректная ссылка HH.ru"
        r = requests.get(
            f"https://api.hh.ru/vacancies/{m.group(1)}",
            headers={"User-Agent": "ResumePro-Bot/1.0"}, timeout=10)
        r.raise_for_status()
        d = r.json()
        title   = d.get("name", "")
        company = d.get("employer", {}).get("name", "")
        exp     = d.get("experience", {}).get("name", "")
        emp     = d.get("employment", {}).get("name", "")
        skills  = ", ".join(s.get("name","") for s in d.get("key_skills",[]))
        desc    = BeautifulSoup(d.get("description",""),"html.parser").get_text(" ",strip=True)
        sal = d.get("salary")
        sal_str = ""
        if sal:
            fr, to, cur = sal.get("from") or "", sal.get("to") or "", sal.get("currency","")
            sal_str = f"{fr}–{to} {cur}".strip("–").strip()
        logger.info(f"✅ Получена вакансия через API: {title} ({company})")
        return (f"ВАКАНСИЯ: {title}\nКОМПАНИЯ: {company}\nОПЫТ: {exp}\n"
                f"ЗАНЯТОСТЬ: {emp}\nЗАРПЛАТА: {sal_str}\nКЛЮЧЕВЫЕ НАВЫКИ: {skills}\n\n"
                f"ОПИСАНИЕ ВАКАНСИИ:\n{desc}")
    except Exception as e:
        logger.error(f"HH.ru: {e}"); return f"Ошибка загрузки вакансии: {e}"


# ── Robust section parser ─────────────────────────────────────────────────────

SECTION_KEYS = ["ИМЯ", "ДОЛЖНОСТЬ", "КОНТАКТЫ", "ПРОФИЛЬ",
                "ОПЫТ", "ОБРАЗОВАНИЕ", "НАВЫКИ", "MATCH", "РЕКОМЕНДАЦИИ"]

def parse_sections(raw):
    """
    Parses GigaChat output which uses 'KEY: value' or 'KEY:' on its own line.
    Also handles === KEY === marker style as fallback.
    Returns dict of section_name -> content.
    """
    text = remove_emojis(clean_markdown(raw))
    sections = {}

    # Build a combined pattern that matches any known section label
    # Matches: "ИМЯ: value" OR "ИМЯ:" (with content following on next lines)
    combined = "|".join(re.escape(k) for k in SECTION_KEYS)
    splitter = re.compile(
        rf'^({combined})\s*:[ \t]*(.*)',
        re.MULTILINE | re.IGNORECASE
    )

    matches = list(splitter.finditer(text))

    for i, m in enumerate(matches):
        key     = m.group(1).upper()
        inline  = m.group(2).strip()
        start   = m.end()
        end     = matches[i+1].start() if i+1 < len(matches) else len(text)
        rest    = text[start:end].strip()
        content = (inline + "\n" + rest).strip() if inline else rest
        sections[key] = content

    # Fallback: try === VALUE === at start of text (older format)
    if not sections:
        eq_blocks = re.findall(r'===\s*([^=\n]+?)\s*===', text)
        if eq_blocks:
            sections["ИМЯ"]      = eq_blocks[0].strip() if len(eq_blocks) > 0 else ""
            sections["ДОЛЖНОСТЬ"]= eq_blocks[1].strip() if len(eq_blocks) > 1 else ""
            # Try plain uppercase headers for the rest
            for key in SECTION_KEYS[2:]:
                m2 = re.search(rf'\b{key}\b\s*\n(.*?)(?=\n[А-ЯA-Z]{{4,}}|\Z)',
                               text, re.DOTALL | re.IGNORECASE)
                if m2:
                    sections[key] = m2.group(1).strip()

    logger.info(f"📄 PDF sections found: {list(sections.keys())}")
    return sections


# ── Professional PDF class ────────────────────────────────────────────────────

class ResumePDF(FPDF):
    def __init__(self, candidate_name="", job_title="", contacts=""):
        super().__init__()
        self.add_font("Sans",  "",  FONT_REG)
        self.add_font("Sans",  "B", FONT_BOLD)
        self.set_margins(16, 0, 16)
        self.set_auto_page_break(auto=True, margin=14)
        self._cname    = candidate_name
        self._ctitle   = job_title
        self._contacts = contacts

    # ── Page header ──────────────────────────────────────────────────────────
    def header(self):
        W = 210
        # Navy rectangle (45mm)
        self.set_fill_color(*NAVY)
        self.rect(0, 0, W, 45, "F")

        # Left white accent stripe
        self.set_fill_color(*ACCENT)
        self.rect(0, 0, 5, 45, "F")

        # Candidate name
        self.set_font("Sans", "B", 22)
        self.set_text_color(*WHITE)
        self.set_xy(8, 8)
        self.cell(W - 8, 11, self._cname, align="L")

        # Job title
        self.set_font("Sans", "", 12)
        self.set_xy(8, 21)
        self.cell(W - 8, 7, self._ctitle, align="L")

        # Contact bar (light blue strip, 8mm)
        self.set_fill_color(*LGRAY)
        self.rect(0, 45, W, 9, "F")
        self.set_font("Sans", "", 8)
        self.set_text_color(*NAVY)
        self.set_xy(0, 46.5)
        self.cell(W, 5, self._contacts, align="C")

        self.set_text_color(*DARK)
        self.set_y(58)   # content starts here

    # ── Page footer ──────────────────────────────────────────────────────────
    def footer(self):
        self.set_y(-11)
        self.set_draw_color(*LINE_C)
        self.set_line_width(0.3)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(1)
        self.set_font("Sans", "", 7.5)
        self.set_text_color(*GRAY)
        self.cell(0, 5, f"Страница {self.page_no()} | ResumePro AI — адаптировано под вакансию", align="C")
        self.set_text_color(*DARK)

    # ── Design helpers ────────────────────────────────────────────────────────
    def section_title(self, title):
        self.ln(5)
        # Navy accent bar left of the title
        x, y = self.get_x(), self.get_y()
        self.set_fill_color(*NAVY)
        self.rect(16, y, 3, 6.5, "F")
        self.set_font("Sans", "B", 10.5)
        self.set_text_color(*NAVY)
        self.set_xy(21, y)
        self.cell(0, 6.5, title.upper())
        self.ln(0.5)
        # Full-width divider line
        yy = self.get_y()
        self.set_draw_color(*LINE_C)
        self.set_line_width(0.3)
        self.line(16, yy, 194, yy)
        self.ln(3)
        self.set_x(16)
        self.set_text_color(*DARK)

    def body(self, text, indent=0):
        self.set_font("Sans", "", 9.5)
        self.set_x(16 + indent)
        self.multi_cell(178 - indent, 5.5, text)

    def bullet(self, text):
        self.set_font("Sans", "", 9.5)
        self.set_x(18)
        self.set_text_color(*ACCENT)
        self.cell(5, 5.5, chr(8226))   # bullet char
        self.set_text_color(*DARK)
        self.set_x(23)
        self.multi_cell(171, 5.5, text.strip())

    def job_row(self, title, meta):
        """Job title bold left, company|dates gray below."""
        self.set_font("Sans", "B", 10)
        self.set_text_color(*DARK)
        self.set_x(16)
        self.multi_cell(178, 6, title)
        if meta:
            self.set_font("Sans", "", 8.5)
            self.set_text_color(*GRAY)
            self.set_x(16)
            self.multi_cell(178, 5, meta)
            self.set_text_color(*DARK)
        self.ln(1)

    def match_box(self, score, matches, advantages):
        self.ln(2)
        # Light-blue background box
        bx, by = 16, self.get_y()
        self.set_fill_color(*LGRAY)
        self.rect(bx, by, 178, 1, "F")   # top border only; height grows
        self.set_font("Sans", "B", 13)
        self.set_text_color(*GREEN)
        self.set_x(bx)
        self.cell(178, 9, score, align="C")
        self.ln(1)
        if matches:
            self.set_font("Sans", "", 9)
            self.set_text_color(*DARK)
            self.set_x(bx)
            self.multi_cell(178, 5.5, matches)
        if advantages:
            self.set_font("Sans", "", 9)
            self.set_text_color(*NAVY)
            self.set_x(bx)
            self.multi_cell(178, 5.5, advantages)
        self.set_text_color(*DARK)

    def skills_block(self, text):
        """Render skills as wrapped groups."""
        items = [s.strip() for s in re.split(r'[,;\n]', text) if s.strip()]
        self.set_font("Sans", "", 9.5)
        self.set_x(16)
        line_buf = []
        line_w   = 0
        cell_pad = 4
        for item in items:
            w = self.get_string_width(item) + cell_pad * 2 + 4
            if line_w + w > 178 and line_buf:
                self._draw_skill_row(line_buf)
                line_buf, line_w = [], 0
            line_buf.append(item)
            line_w += w
        if line_buf:
            self._draw_skill_row(line_buf)

    def _draw_skill_row(self, items):
        x0 = 16
        y0 = self.get_y()
        h  = 6.5
        pad = 4
        self.set_font("Sans", "", 9)
        for item in items:
            w = self.get_string_width(item) + pad * 2
            self.set_fill_color(*LGRAY)
            self.set_draw_color(*LINE_C)
            self.set_line_width(0.2)
            self.rect(x0, y0, w, h, "FD")
            self.set_text_color(*NAVY)
            self.set_xy(x0 + pad * 0.5, y0 + 0.8)
            self.cell(w - pad, h - 1.5, item)
            x0 += w + 3
        self.set_text_color(*DARK)
        self.ln(h + 2)
        self.set_x(16)


# ── Experience block renderer ─────────────────────────────────────────────────

def _render_experience(pdf, block):
    entries = re.split(r'\n(?=[^\s\-•])', block.strip())
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        lines  = entry.splitlines()
        title  = ""
        meta   = ""
        bullets = []
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if s.startswith(('-', '•', '–')):
                bullets.append(s.lstrip('-•– '))
            elif not title:
                title = s
            elif not meta:
                meta = s
            else:
                # Extra non-bullet line — treat as continuation of meta or a bullet
                if '|' in s or re.search(r'\d{4}', s):
                    meta = (meta + ' ' + s).strip()
                else:
                    bullets.append(s)
        if title:
            pdf.job_row(title, meta)
        for b in bullets:
            pdf.bullet(b)
        pdf.ln(3)


# ── Main PDF builder ──────────────────────────────────────────────────────────

def create_resume_pdf(resume_text, output_path):
    """Generate a professional, send-ready Russian resume PDF."""
    try:
        raw = remove_emojis(clean_markdown(resume_text))
        sec = parse_sections(raw)

        name      = sec.get("ИМЯ", "").strip()      or "Кандидат"
        title     = sec.get("ДОЛЖНОСТЬ", "").strip() or ""
        contacts  = sec.get("КОНТАКТЫ", "").strip()  or ""
        profile   = sec.get("ПРОФИЛЬ", "").strip()
        exp_blk   = sec.get("ОПЫТ", "").strip()
        edu_blk   = sec.get("ОБРАЗОВАНИЕ", "").strip()
        skills    = sec.get("НАВЫКИ", "").strip()
        match_blk = sec.get("MATCH", "").strip()
        recs      = sec.get("РЕКОМЕНДАЦИИ", "").strip()

        pdf = ResumePDF(
            candidate_name=name,
            job_title=title,
            contacts=contacts,
        )
        pdf.add_page()

        # PROFILE
        if profile:
            pdf.section_title("Профессиональный профиль")
            pdf.body(profile)

        # WORK EXPERIENCE
        if exp_blk:
            pdf.section_title("Опыт работы")
            _render_experience(pdf, exp_blk)

        # EDUCATION
        if edu_blk:
            pdf.section_title("Образование")
            for ln in edu_blk.splitlines():
                s = ln.strip()
                if not s:
                    pdf.ln(2)
                elif s.startswith(('-','•')):
                    pdf.bullet(s.lstrip('-• '))
                else:
                    pdf.body(s)

        # SKILLS
        if skills:
            pdf.section_title("Ключевые навыки")
            pdf.skills_block(skills)

        # MATCH SCORE
        if match_blk:
            pdf.section_title("ATS Match Score")
            lines = match_blk.splitlines()
            score = next((l for l in lines if re.search(r'\d+\s*%', l)), lines[0] if lines else "")
            rest  = [l for l in lines if l.strip() and l.strip() != score.strip()]
            matches    = ""
            advantages = ""
            for l in rest:
                if re.search(r'(Совпад|совпад|Match|match)', l):
                    matches = l
                elif re.search(r'(Преимущ|преимущ)', l):
                    advantages = l
                else:
                    if not matches:   matches = l
                    else:             advantages += " " + l
            pdf.match_box(score.strip(), matches.strip(), advantages.strip())

        # RECOMMENDATIONS
        if recs:
            pdf.section_title("Рекомендации")
            for ln in recs.splitlines():
                s = ln.strip().lstrip('-•– ')
                if s:
                    pdf.bullet(s)

        # Fallback if nothing parsed
        if not any([profile, exp_blk, edu_blk, skills, match_blk]):
            logger.warning("⚠️ No sections parsed — plain text fallback")
            pdf.section_title("Адаптированное резюме")
            for ln in raw.splitlines():
                s = ln.strip()
                if not s:        pdf.ln(2)
                elif s.startswith(('-','•')): pdf.bullet(s.lstrip('-• '))
                else:            pdf.body(s)

        pdf.output(output_path)
        sz = os.path.getsize(output_path)
        logger.info(f"✅ PDF created: {output_path} ({sz} bytes)")
        return True

    except Exception as e:
        logger.error(f"❌ PDF error: {e}")
        import traceback; traceback.print_exc()
        return False


def generate_resume_pdf(t, p): return create_resume_pdf(t, p)
def create_simple_pdf(t, p):   return create_resume_pdf(t, p)
