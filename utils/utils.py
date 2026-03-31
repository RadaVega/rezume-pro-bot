#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# utils/utils.py
"""ResumePro AI — Utilities: file reading, HH.ru parsing, text cleaning."""

import re
import logging
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document

logger = logging.getLogger(__name__)


def clean_markdown(text: str) -> str:
    """Remove markdown formatting so VK messages look clean."""
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


def read_pdf(path: str) -> str:
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as e:
        logger.error("PDF read error: %s", e)
        return ""


def read_docx(path: str) -> str:
    """Extract text from a DOCX file."""
    try:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    except Exception as e:
        logger.error("DOCX read error: %s", e)
        return ""


def extract_text_from_file(path: str, ftype: str) -> str:
    """Route file extraction by type."""
    ftype = ftype.lower().lstrip(".")
    if ftype == "pdf":
        return read_pdf(path)
    if ftype in ("docx", "doc"):
        return read_docx(path)
    logger.warning("Unsupported file type: %s", ftype)
    return ""


def parse_hh_vacancy(url: str) -> str:
    """
    Fetch a vacancy from the HH.ru public API and return a formatted string.
    Returns an error string (starting with "Error:") on failure.
    """
    try:
        match = re.search(r"hh\.ru/vacancy/(\d+)", url)
        if not match:
            return "Invalid HH.ru URL"

        vacancy_id = match.group(1)
        response = requests.get(
            f"https://api.hh.ru/vacancies/{vacancy_id}",
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

        logger.info("✅ Parsed vacancy: %s (%s)", title, company)
        return (
            f"ВАКАНСИЯ: {title}\n"
            f"КОМПАНИЯ: {company}\n"
            f"ОПЫТ: {experience}\n"
            f"ЗАНЯТОСТЬ: {employment}\n"
            f"НАВЫКИ: {skills}\n\n"
            f"ОПИСАНИЕ:\n{description}"
        )

    except requests.HTTPError as e:
        logger.error("HH.ru HTTP error: %s", e)
        return f"Error: вакансия не найдена или недоступна ({e})"
    except Exception as e:
        logger.error("HH.ru error: %s", e)
        return f"Error: {e}"
