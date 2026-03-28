#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ResumePro AI - Utilities (Text Only)"""

import re
import requests
import logging
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document

logger = logging.getLogger(__name__)


def clean_markdown(text):
    """Remove markdown formatting"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-_*]{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_pdf(path):
    """Extract text from PDF"""
    try:
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return ""


def read_docx(path):
    """Extract text from DOCX"""
    try:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    except Exception as e:
        logger.error(f"DOCX error: {e}")
        return ""


def extract_text_from_file(path, ftype):
    """Extract text based on file type"""
    ftype = ftype.lower()
    if ftype == "pdf":
        return read_pdf(path)
    if ftype in ("docx", "doc"):
        return read_docx(path)
    return ""


def parse_hh_vacancy(url):
    """Parse HH.ru vacancy"""
    try:
        match = re.search(r"hh\.ru/vacancy/(\d+)", url)
        if not match:
            return "Invalid HH.ru URL"

        response = requests.get(
            f"https://api.hh.ru/vacancies/{match.group(1)}",
            headers={"User-Agent": "ResumePro-Bot/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        title = data.get("name", "")
        company = data.get("employer", {}).get("name", "")
        experience = data.get("experience", {}).get("name", "")
        employment = data.get("employment", {}).get("name", "")
        skills = ", ".join(s.get("name", "") for s in data.get("key_skills", []))
        description = BeautifulSoup(
            data.get("description", ""), "html.parser"
        ).get_text(" ", strip=True)

        logger.info(f"✅ Получена вакансия: {title} ({company})")

        return f"ВАКАНСИЯ: {title}\nКОМПАНИЯ: {company}\nОПЫТ: {experience}\nЗАНЯТОСТЬ: {employment}\nНАВЫКИ: {skills}\n\nОПИСАНИЕ:\n{description}"
    except Exception as e:
        logger.error(f"HH.ru error: {e}")
        return f"Error: {e}"
