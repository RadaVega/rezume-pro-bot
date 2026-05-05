#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# utils/utils.py
"""ResumePro AI — Utilities: file reading, multi-platform vacancy parsing, text cleaning."""

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

# ── Shared browser headers ────────────────────────────────────────────────────
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

# ── HH.ru API headers (fallback only) ────────────────────────────────────────
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


# ════════════════════════════════════════════════════════════════════════════
# File utilities
# ════════════════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════════════════
# Universal dispatcher
# ════════════════════════════════════════════════════════════════════════════

def scrape_any_vacancy(url: str) -> str:
    """
    Universal vacancy scraper — detects the platform from the URL and
    calls the appropriate parser.

    Supported platforms:
      • hh.ru / headhunter.ru
      • superjob.ru
      • rabota.ru
      • linkedin.com
      • any other site (generic JSON-LD / og-tags fallback)

    Returns a formatted string with vacancy details, or a string starting
    with "Error:" on failure.
    """
    url_lower = url.lower()

    if "hh.ru" in url_lower or "headhunter" in url_lower:
        return parse_hh_vacancy(url)
    elif "superjob" in url_lower:
        return parse_superjob_vacancy(url)
    elif "rabota.ru" in url_lower:
        return parse_rabota_vacancy(url)
    elif "linkedin.com" in url_lower:
        return parse_linkedin_vacancy(url)
    else:
        logger.info("Unknown job site, using generic parser for: %s", url)
        return _parse_generic_vacancy(url)


# ════════════════════════════════════════════════════════════════════════════
# HH.ru parser
# ════════════════════════════════════════════════════════════════════════════

def parse_hh_vacancy(url: str) -> str:
    """
    Fetch a vacancy from hh.ru.

    Strategy 1 (primary): Scrape the HTML page with browser headers,
      extract from JSON-LD JobPosting schema (embedded on every hh.ru page),
      enrich with data-qa elements for salary/experience/employment.

    Strategy 2 (fallback): Public JSON API at api.hh.ru/vacancies/{id}
      with exponential backoff. Blocked by 403 from cloud IPs (Railway etc.)
      but kept as a last resort.
    """
    try:
        match = re.search(r"hh\.ru/vacancy/(\d+)", url)
        if not match:
            return "Error: Invalid HH.ru URL — expected hh.ru/vacancy/{id}"

        vacancy_id = match.group(1)

        result = _hh_scrape_page(vacancy_id)
        if not result.startswith("Error:"):
            logger.info("✅ HH.ru parsed via scraping: id=%s", vacancy_id)
            return result

        logger.warning("⚠️ HH.ru scraping failed (%s), trying API fallback", result)
        return _hh_fetch_api(vacancy_id)

    except Exception as e:
        logger.error("HH.ru parse error: %s", e)
        return f"Error: {e}"


def _hh_scrape_page(vacancy_id: str) -> str:
    page_url = f"https://hh.ru/vacancy/{vacancy_id}"
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

    # JSON-LD (hh.ru always embeds a JobPosting block)
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
        description = BeautifulSoup(
            data.get("description", ""), "html.parser"
        ).get_text(" ", strip=True)

        experience = _dqa(soup, "vacancy-experience")
        employment = _dqa(soup, "common-employment-text")
        salary = _dqa(soup, "vacancy-salary")

        return _format_vacancy(
            title=title, company=company, salary=salary,
            experience=experience, employment=employment,
            description=description,
        )

    # HTML data-qa fallback
    title = _dqa(soup, "vacancy-title")
    company = _dqa(soup, "vacancy-company-name")
    experience = _dqa(soup, "vacancy-experience")
    employment = _dqa(soup, "common-employment-text")
    salary = _dqa(soup, "vacancy-salary")
    desc_el = soup.find(attrs={"data-qa": "vacancy-description"})
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    if not title and not description:
        return (
            f"Error: не удалось распознать страницу вакансии HH.ru {vacancy_id}. "
            "Возможно, вакансия удалена."
        )

    return _format_vacancy(
        title=title, company=company, salary=salary,
        experience=experience, employment=employment,
        description=description,
    )


def _hh_fetch_api(vacancy_id: str, retries: int = 3) -> str:
    """Fallback: HH.ru public JSON API with exponential backoff."""
    api_url = f"https://api.hh.ru/vacancies/{vacancy_id}"

    for attempt in range(retries):
        if attempt > 0:
            delay = (2 ** attempt) + random.uniform(0.0, 1.0)
            logger.info("HH API retry %d/%d, waiting %.1fs", attempt + 1, retries, delay)
            time.sleep(delay)

        try:
            resp = requests.get(api_url, headers=_API_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            title = data.get("name", "")
            company = data.get("employer", {}).get("name", "")
            experience = data.get("experience", {}).get("name", "")
            employment = data.get("employment", {}).get("name", "")
            skills = ", ".join(s.get("name", "") for s in data.get("key_skills", []))
            description = BeautifulSoup(
                data.get("description", ""), "html.parser"
            ).get_text(" ", strip=True)
            if skills:
                description = f"Навыки: {skills}\n\n{description}"

            logger.info("✅ HH API parsed: %s (%s)", title, company)
            return _format_vacancy(
                title=title, company=company, experience=experience,
                employment=employment, description=description,
            )

        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            if code in (403, 404):
                return f"Error: вакансия не найдена или недоступна ({e})"
            logger.warning("HH API attempt %d failed: %s", attempt + 1, e)
        except Exception as e:
            logger.warning("HH API attempt %d error: %s", attempt + 1, e)

    return "Error: не удалось получить вакансию через API после нескольких попыток."


# ════════════════════════════════════════════════════════════════════════════
# SuperJob parser
# ════════════════════════════════════════════════════════════════════════════

def parse_superjob_vacancy(url: str) -> str:
    """
    Fetch a vacancy from superjob.ru.

    Strategy 1 (primary): Parse the embedded window.APP_STATE JSON object
      (a Redux-style store SuperJob injects into every page). Extracts title,
      company, salary, duties, requirements, and conditions with no
      fragile CSS-class dependencies.

    Strategy 2 (fallback): og: meta tags — og:title carries the job title
      and og:description gives a short summary.

    URL pattern: superjob.ru/vakansii/{slug}-{id}.html
    """
    try:
        match = re.search(r"-(\d+)\.html", url)
        if not match:
            return "Error: Invalid SuperJob URL — expected superjob.ru/vakansii/{slug}-{id}.html"

        vacancy_id = match.group(1)
        time.sleep(random.uniform(0.3, 0.9))

        session = requests.Session()
        session.headers.update(_BROWSER_HEADERS)

        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            return f"Error: HTTP {code} fetching SuperJob vacancy"
        except requests.RequestException as e:
            return f"Error: network error fetching SuperJob vacancy: {e}"

        soup = BeautifulSoup(resp.text, "lxml")

        # Strategy 1: window.APP_STATE embedded JSON
        for script in soup.find_all("script"):
            txt = script.string or ""
            if "window.APP_STATE=" not in txt:
                continue
            m = re.search(r"window\.APP_STATE=(\{.+\});?\s*$", txt, re.DOTALL)
            if not m:
                continue
            try:
                state = json.loads(m.group(1))
            except json.JSONDecodeError:
                break

            ents = state.get("entities", {})
            vmi  = ents.get("vacancyMainInfo",   {}).get(vacancy_id, {}).get("attributes", {})
            vdi  = ents.get("vacancyDetailInfo",  {}).get(vacancy_id, {}).get("attributes", {})
            vsal = ents.get("vacancySalary",      {}).get(vacancy_id, {}).get("attributes", {})
            vci  = ents.get("vacancyCompanyInfo", {}).get(vacancy_id, {}).get("attributes", {})

            title = vmi.get("profession", "")
            if not title:
                break  # APP_STATE present but vacancy not found by id

            company = vci.get("name", "")
            min_sal = vsal.get("minSalary") or vmi.get("minSalary")
            max_sal = vsal.get("maxSalary") or vmi.get("maxSalary")
            salary  = _format_salary_range(min_sal, max_sal, currency="руб.")

            full_text = vdi.get("fullTextPlain") or vdi.get("fullText", "")
            if full_text:
                raw = BeautifulSoup(full_text, "html.parser").get_text(" ", strip=True)
                description = _clean_vacancy_text(raw)
            else:
                parts = [vdi.get("duties", ""), vdi.get("requirements", ""), vdi.get("conditions", "")]
                combined = "\n".join(p for p in parts if p)
                raw = BeautifulSoup(combined, "html.parser").get_text(" ", strip=True)
                description = _clean_vacancy_text(raw)

            logger.info("✅ SuperJob parsed via APP_STATE: id=%s", vacancy_id)
            return _format_vacancy(title=title, company=company, salary=salary, description=description)

        # Strategy 2: og: meta tags
        og_title = soup.find("meta", property="og:title")
        og_desc  = soup.find("meta", property="og:description")
        h1       = soup.find("h1")

        title = h1.get_text(strip=True) if h1 else (
            og_title.get("content", "").split(" в компании")[0].strip() if og_title else ""
        )
        description = og_desc.get("content", "") if og_desc else ""

        if not title:
            return "Error: не удалось распознать вакансию SuperJob"

        logger.info("✅ SuperJob parsed via og-tags: id=%s", vacancy_id)
        return _format_vacancy(title=title, description=description)

    except Exception as e:
        logger.error("SuperJob parse error: %s", e)
        return f"Error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# Rabota.ru parser
# ════════════════════════════════════════════════════════════════════════════

def parse_rabota_vacancy(url: str) -> str:
    """
    Fetch a vacancy from rabota.ru.

    Strategy 1: itemprop microdata (title + description). Company and salary
      are extracted from og:title ("работа в компании X, зарплата Y") because
      the itemprop="hiringOrganization" element wraps a verification badge
      before the real name.
    Strategy 2: JSON-LD JobPosting (if present on the page).
    Strategy 3: og:title + og:description meta tags.

    URL pattern: rabota.ru/vacancy/{id}/
    """
    try:
        if "rabota.ru" not in url.lower():
            return "Error: URL does not appear to be a rabota.ru vacancy"

        time.sleep(random.uniform(0.3, 0.9))
        session = requests.Session()
        session.headers.update(_BROWSER_HEADERS)

        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            return f"Error: HTTP {code} fetching Rabota.ru vacancy"
        except requests.RequestException as e:
            return f"Error: network error fetching Rabota.ru vacancy: {e}"

        soup = BeautifulSoup(resp.text, "lxml")

        # Strategy 1: itemprop microdata
        title_el = (
            soup.find(attrs={"itemprop": "title"}) or
            soup.find(attrs={"itemprop": "name"}) or
            soup.find("h1")
        )
        desc_el = soup.find(attrs={"itemprop": "description"})
        title       = title_el.get_text(strip=True) if title_el else ""
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        # og:title = "Вакансия X в Москве с зарплатой Y, работа в компании Z"
        og_title_el = soup.find("meta", property="og:title")
        salary, company = "", ""
        if og_title_el:
            og_t = og_title_el.get("content", "")
            sal_m  = re.search(r"зарплатой\s+(.+?)(?:,|$)", og_t, re.IGNORECASE)
            comp_m = re.search(r"работа в компании\s+(.+?)$", og_t, re.IGNORECASE)
            if sal_m:
                salary = sal_m.group(1).strip()
            if comp_m:
                company = comp_m.group(1).strip()

        if title and description:
            logger.info("✅ Rabota.ru parsed via itemprop: %s", title)
            return _format_vacancy(title=title, company=company, salary=salary, description=description)

        # Strategy 2: JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, AttributeError):
                continue
            if data.get("@type") != "JobPosting":
                continue
            title       = data.get("title", "").strip()
            org         = data.get("hiringOrganization", {})
            company     = org.get("name", "").strip() if isinstance(org, dict) else ""
            description = BeautifulSoup(data.get("description", ""), "html.parser").get_text(" ", strip=True)
            logger.info("✅ Rabota.ru parsed via JSON-LD: %s", title)
            return _format_vacancy(title=title, company=company, description=description)

        # Strategy 3: og tags
        og_desc_el = soup.find("meta", property="og:description")
        h1 = soup.find("h1")
        title = (h1.get_text(strip=True) if h1 else "") or (
            og_title_el.get("content", "").split(" в ")[0].strip() if og_title_el else ""
        )
        description = og_desc_el.get("content", "") if og_desc_el else ""

        if not title:
            return "Error: не удалось распознать вакансию Rabota.ru"

        logger.info("✅ Rabota.ru parsed via og-tags: %s", title)
        return _format_vacancy(title=title, description=description)

    except Exception as e:
        logger.error("Rabota.ru parse error: %s", e)
        return f"Error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# LinkedIn parser
# ════════════════════════════════════════════════════════════════════════════

def parse_linkedin_vacancy(url: str) -> str:
    """
    Fetch a vacancy from linkedin.com/jobs.

    LinkedIn public job pages (linkedin.com/jobs/view/{id}) render server-side:
      • h1                              → job title
      • .topcard__org-name-link         → company name
      • .topcard__flavor--bullet        → location
      • .description__text              → full job description
      • .description__job-criteria-item → seniority / employment type

    Always use linkedin.com/jobs/view/{id} format — other LinkedIn URLs
    redirect to the login wall.
    """
    try:
        if "linkedin.com" not in url.lower():
            return "Error: URL does not appear to be a LinkedIn vacancy"

        url = re.sub(r"\?.*$", "", url.rstrip("/"))
        time.sleep(random.uniform(0.5, 1.2))

        session = requests.Session()
        session.headers.update(_BROWSER_HEADERS)

        try:
            resp = session.get(url, timeout=20, allow_redirects=True)
            resp.raise_for_status()
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            return f"Error: HTTP {code} fetching LinkedIn vacancy"
        except requests.RequestException as e:
            return f"Error: network error fetching LinkedIn vacancy: {e}"

        soup = BeautifulSoup(resp.text, "lxml")

        h1          = soup.find("h1")
        title       = h1.get_text(strip=True) if h1 else ""
        company_el  = soup.find(class_=re.compile(r"topcard__org-name-link"))
        company     = company_el.get_text(strip=True) if company_el else ""
        loc_el      = soup.find(class_=re.compile(r"topcard__flavor--bullet"))
        location    = loc_el.get_text(strip=True) if loc_el else ""
        desc_el     = soup.find(class_=re.compile(r"description__text"))
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        # Strip leading title LinkedIn injects into the description block
        if description.startswith(title):
            description = description[len(title):].strip()

        criteria_items = soup.find_all(class_="description__job-criteria-item")
        criteria_lines = []
        for item in criteria_items:
            label_el = item.find("h3")
            value_el = item.find("span")
            if label_el and value_el:
                label = label_el.get_text(strip=True)
                value = value_el.get_text(strip=True)
                if any(kw in label.lower() for kw in
                       ("уровень", "занятость", "тип", "seniority", "employment", "level")):
                    criteria_lines.append(f"{label}: {value}")

        if not title:
            if "authwall" in resp.url or "login" in resp.url:
                return "Error: LinkedIn redirected to login — используйте linkedin.com/jobs/view/{id}"
            return "Error: не удалось распознать вакансию LinkedIn"

        employment = "; ".join(criteria_lines) if criteria_lines else ""
        logger.info("✅ LinkedIn parsed: %s (%s)", title, company)
        return _format_vacancy(
            title=title, company=company, location=location,
            employment=employment, description=description,
        )

    except Exception as e:
        logger.error("LinkedIn parse error: %s", e)
        return f"Error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# Generic fallback parser (any site)
# ════════════════════════════════════════════════════════════════════════════

def _parse_generic_vacancy(url: str) -> str:
    """
    Generic parser for unsupported job sites.  Tries in order:
      1. JSON-LD JobPosting schema
      2. Schema.org itemprop microdata
      3. Open Graph og:title + og:description
      4. h1 + largest paragraph block
    """
    try:
        time.sleep(random.uniform(0.3, 0.9))
        session = requests.Session()
        session.headers.update(_BROWSER_HEADERS)

        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            return f"Error: HTTP {code} fetching {url}"
        except requests.RequestException as e:
            return f"Error: network error: {e}"

        soup = BeautifulSoup(resp.text, "lxml")

        # 1. JSON-LD JobPosting
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, AttributeError):
                continue
            if data.get("@type") != "JobPosting":
                continue
            title   = data.get("title", "").strip()
            org     = data.get("hiringOrganization", {})
            company = org.get("name", "").strip() if isinstance(org, dict) else ""
            description = BeautifulSoup(
                data.get("description", ""), "html.parser"
            ).get_text(" ", strip=True)
            loc, location = data.get("jobLocation", {}), ""
            if isinstance(loc, dict):
                addr = loc.get("address", {})
                if isinstance(addr, dict):
                    location = ", ".join(filter(None, [
                        addr.get("addressLocality", ""), addr.get("addressCountry", ""),
                    ]))
            logger.info("✅ Generic JSON-LD parse: %s", url)
            return _format_vacancy(title=title, company=company, location=location, description=description)

        # 2. itemprop
        title_el = soup.find(attrs={"itemprop": "title"}) or soup.find(attrs={"itemprop": "name"})
        desc_el  = soup.find(attrs={"itemprop": "description"})
        if title_el and desc_el:
            return _format_vacancy(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(" ", strip=True),
            )

        # 3. og: meta
        og_title = soup.find("meta", property="og:title")
        og_desc  = soup.find("meta", property="og:description")
        if og_title:
            return _format_vacancy(
                title=og_title.get("content", "").strip(),
                description=og_desc.get("content", "").strip() if og_desc else "",
            )

        # 4. h1 + biggest paragraph
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""
        if title:
            paragraphs = sorted(
                [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text()) > 100],
                key=len, reverse=True,
            )
            description = paragraphs[0][:2000] if paragraphs else ""
            return _format_vacancy(title=title, description=description)

        return f"Error: не удалось распознать вакансию на странице {url}"

    except Exception as e:
        logger.error("Generic vacancy parse error: %s", e)
        return f"Error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ════════════════════════════════════════════════════════════════════════════

def is_linkedin_url(url: str) -> bool:
    """Check if a URL belongs to LinkedIn."""
    return "linkedin.com" in url.lower()


def is_superjob_url(url: str) -> bool:
    """Check if a URL belongs to SuperJob."""
    return "superjob.ru" in url.lower()


def is_rabota_url(url: str) -> bool:
    """Check if a URL belongs to Rabota.ru."""
    return "rabota.ru" in url.lower()


def _dqa(soup: BeautifulSoup, data_qa: str) -> str:
    """Return stripped text for the first element with data-qa=<value>."""
    el = soup.find(attrs={"data-qa": data_qa})
    return el.get_text(" ", strip=True) if el else ""


def _clean_vacancy_text(text: str) -> str:
    """
    Normalise whitespace in vacancy text from embedded JS state objects
    (e.g. SuperJob's window.APP_STATE plain-text fields).
    Collapses mixed \\r/\\n sequences and removes blank-only lines.
    """
    text = re.sub(r'\r\n?', '\n', text)
    lines = [ln.rstrip() for ln in text.split('\n')]
    lines = [ln for ln in lines if ln.strip()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _format_salary_range(
    min_sal: int | None,
    max_sal: int | None,
    currency: str = "руб.",
) -> str:
    """Format a salary range string from min/max integers."""
    if min_sal and max_sal:
        return f"от {min_sal:,} до {max_sal:,} {currency}".replace(",", "\u00a0")
    if min_sal:
        return f"от {min_sal:,} {currency}".replace(",", "\u00a0")
    if max_sal:
        return f"до {max_sal:,} {currency}".replace(",", "\u00a0")
    return ""


def _format_vacancy(
    title: str = "",
    company: str = "",
    salary: str = "",
    location: str = "",
    experience: str = "",
    employment: str = "",
    description: str = "",
) -> str:
    """Assemble the final vacancy string from its parts."""
    lines = []
    if title:       lines.append(f"ВАКАНСИЯ: {title}")
    if company:     lines.append(f"КОМПАНИЯ: {company}")
    if salary:      lines.append(f"ЗАРПЛАТА: {salary}")
    if location:    lines.append(f"ГОРОД: {location}")
    if experience:  lines.append(f"ОПЫТ: {experience}")
    if employment:  lines.append(f"ЗАНЯТОСТЬ: {employment}")
    if description: lines.append(f"\nОПИСАНИЕ:\n{description}")
    return "\n".join(lines)