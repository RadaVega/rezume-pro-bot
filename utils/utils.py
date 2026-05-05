#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# utils/utils.py
"""ResumePro AI — Utilities: file reading, HH.ru parsing, text cleaning."""

import re
import json
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document

logger = logging.getLogger(__name__)

# ── Browser-like headers for web scraping ────────────────────────────────────
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

# ── API headers (fallback) ───────────────────────────────────────────────────
_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "HH-User-Agent": "ResumePro-Bot/1.0 (support@rezume.pro)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


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


# ── HH.ru vacancy parsing ────────────────────────────────────────────────────

def parse_hh_vacancy(url: str) -> str:
    """
    Fetch a vacancy from hh.ru.

    Strategy 1 (primary): Scrape the HTML page at hh.ru/vacancy/{id}
      with browser-like headers. Extracts data from JSON-LD (most reliable)
      or falls back to data-qa HTML attributes.

    Strategy 2 (fallback): Call the public JSON API at api.hh.ru/vacancies/{id}
      with exponential backoff and retries. This was the original approach that
      fails with 403 from cloud IPs like Railway — kept as a last resort.

    Returns an error string starting with "Error:" on complete failure.
    """
    try:
        match = re.search(r"hh\.ru/vacancy/(\d+)", url)
        if not match:
            return "Invalid HH.ru URL"

        vacancy_id = match.group(1)

        # Strategy 1: HTML scraping (resilient, bypasses API IP blocks)
        result = _scrape_hh_page(vacancy_id)
        if not result.startswith("Error:"):
            logger.info("✅ Parsed vacancy via scraping: id=%s", vacancy_id)
            return result

        logger.warning("⚠️ Scraping failed (%s), trying API fallback", result)

        # Strategy 2: Public API with retries
        return _fetch_hh_api(vacancy_id)

    except Exception as e:
        logger.error("HH.ru parse error: %s", e)
        return f"Error: {e}"


def _scrape_hh_page(vacancy_id: str) -> str:
    """
    Scrape the hh.ru vacancy HTML page and extract vacancy data.
    Uses a session so cookies are handled automatically.
    """
    page_url = f"https://hh.ru/vacancy/{vacancy_id}"

    # Small random delay to be polite and avoid rate-limiting
    time.sleep(random.uniform(0.3, 0.9))

    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)

    try:
        resp = session.get(page_url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return f"Error: HTTP {code} scraping {page_url}"
    except requests.RequestException as e:
        return f"Error: network error scraping {page_url}: {e}"

    soup = BeautifulSoup(resp.text, "lxml")

    # Preferred: extract from JSON-LD structured data (fast, clean, complete)
    result = _parse_json_ld(soup, vacancy_id)
    if result:
        return result

    # Fallback: parse from HTML data-qa attributes
    return _parse_html_elements(soup, vacancy_id)


def _parse_json_ld(soup: BeautifulSoup, vacancy_id: str) -> str:
    """
    Extract vacancy data from the JSON-LD <script type="application/ld+json"> block.
    hh.ru embeds a JobPosting schema on every vacancy page — this is the most
    reliable extraction method and requires no HTML structure assumptions.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, AttributeError):
            continue

        if data.get("@type") != "JobPosting":
            continue

        title = data.get("title", "").strip()
        org = data.get("hiringOrganization", {})
        company = org.get("name", "").strip() if isinstance(org, dict) else ""
        description_html = data.get("description", "")
        description = BeautifulSoup(description_html, "html.parser").get_text(
            " ", strip=True
        )

        # Enrich with experience/employment/salary from data-qa (not in JSON-LD)
        experience = _get_dqa_text(soup, "vacancy-experience")
        employment = _get_dqa_text(soup, "common-employment-text")
        salary = _get_dqa_text(soup, "vacancy-salary")

        lines = [f"ВАКАНСИЯ: {title}"]
        if company:
            lines.append(f"КОМПАНИЯ: {company}")
        if salary:
            lines.append(f"ЗАРПЛАТА: {salary}")
        if experience:
            lines.append(f"ОПЫТ: {experience}")
        if employment:
            lines.append(f"ЗАНЯТОСТЬ: {employment}")
        if description:
            lines.append(f"\nОПИСАНИЕ:\n{description}")

        return "\n".join(lines)

    return ""  # No JobPosting JSON-LD found


def _parse_html_elements(soup: BeautifulSoup, vacancy_id: str) -> str:
    """
    Parse vacancy data from HTML data-qa attributes.
    Used when JSON-LD is absent (unlikely on hh.ru, but kept as safety net).
    """
    title = _get_dqa_text(soup, "vacancy-title")
    company = _get_dqa_text(soup, "vacancy-company-name")
    experience = _get_dqa_text(soup, "vacancy-experience")
    employment = _get_dqa_text(soup, "common-employment-text")
    salary = _get_dqa_text(soup, "vacancy-salary")

    desc_el = soup.find(attrs={"data-qa": "vacancy-description"})
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    if not title and not description:
        return (
            f"Error: не удалось распознать страницу вакансии {vacancy_id}. "
            "Возможно, вакансия удалена или временно недоступна."
        )

    lines = [f"ВАКАНСИЯ: {title}"]
    if company:
        lines.append(f"КОМПАНИЯ: {company}")
    if salary:
        lines.append(f"ЗАРПЛАТА: {salary}")
    if experience:
        lines.append(f"ОПЫТ: {experience}")
    if employment:
        lines.append(f"ЗАНЯТОСТЬ: {employment}")
    if description:
        lines.append(f"\nОПИСАНИЕ:\n{description}")

    return "\n".join(lines)


def _get_dqa_text(soup: BeautifulSoup, data_qa: str) -> str:
    """Return stripped text for the first element matching data-qa=<value>."""
    el = soup.find(attrs={"data-qa": data_qa})
    return el.get_text(" ", strip=True) if el else ""


def _fetch_hh_api(vacancy_id: str, retries: int = 3) -> str:
    """
    Fallback: fetch from the hh.ru public JSON API with exponential backoff.
    This was the original implementation — it fails with 403 from cloud IPs
    (Railway, Render, etc.) but may work from other environments.
    """
    api_url = f"https://api.hh.ru/vacancies/{vacancy_id}"

    for attempt in range(retries):
        if attempt > 0:
            delay = (2 ** attempt) + random.uniform(0.0, 1.0)
            logger.info(
                "HH API retry %d/%d, waiting %.1fs", attempt + 1, retries, delay
            )
            time.sleep(delay)

        try:
            resp = requests.get(api_url, headers=_API_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            title = data.get("name", "")
            company = data.get("employer", {}).get("name", "")
            experience = data.get("experience", {}).get("name", "")
            employment = data.get("employment", {}).get("name", "")
            skills = ", ".join(
                s.get("name", "") for s in data.get("key_skills", [])
            )
            description = BeautifulSoup(
                data.get("description", ""), "html.parser"
            ).get_text(" ", strip=True)

            logger.info("✅ API parsed vacancy: %s (%s)", title, company)
            lines = [f"ВАКАНСИЯ: {title}"]
            if company:
                lines.append(f"КОМПАНИЯ: {company}")
            if experience:
                lines.append(f"ОПЫТ: {experience}")
            if employment:
                lines.append(f"ЗАНЯТОСТЬ: {employment}")
            if skills:
                lines.append(f"НАВЫКИ: {skills}")
            if description:
                lines.append(f"\nОПИСАНИЕ:\n{description}")
            return "\n".join(lines)

        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            if code in (403, 404):
                logger.error("HH API %s: %s", code, e)
                return f"Error: вакансия не найдена или недоступна ({e})"
            logger.warning("HH API attempt %d/%d failed: %s", attempt + 1, retries, e)
        except Exception as e:
            logger.warning("HH API attempt %d/%d error: %s", attempt + 1, retries, e)

    return (
        "Error: не удалось получить вакансию через API после нескольких попыток. "
        "Убедитесь, что ссылка корректна и вакансия не удалена."
    )