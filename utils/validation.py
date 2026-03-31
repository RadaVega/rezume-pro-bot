# utils/validation.py
"""
Утилиты для валидации сущностей и обнаружения галлюцинаций.
Версия: 5.0
"""

import re
from typing import Dict, Set, List, Any
from difflib import SequenceMatcher


# ── GENERIC STOP-WORDS (false-positive noise for NER) ───────────────────────
# Only generic Russian nouns that are NOT company/position names.
# Tech skills have been intentionally REMOVED from here — see TECH_SKILLS below.
STOP_WORDS: Set[str] = {
    # GigaChat's own output phrases must not be parsed as skills
    "нет в резюме",
    "нет данных",
    "не указан",
    "не указано",
    "не указана",
    "навык не указан",
    "отсутствует",
    "не упомянут",
    # Generic nouns
    "компания",
    "организация",
    "работал",
    "работала",
    "проект",
    "навык",
    "умение",
    "должность",
    "позиция",
    "резюме",
    "через",
    "качество",
    "работа",
    "сотрудник",
    "суд",
    "договор",
    "право",
    "закон",
    "данные",
    "анализ",
    "рынок",
    "клиент",
    "команда",
    "эффективность",
    "реализация",
    "рамки",
    "уровень",
    "методология",
    "социальные сети",
    "соцсети",
    "бизнес",
    "исполнение",
    "соблюдение",
    "законодательство",
    "информация",
    "дела",
    "сроки",
    "качества",
    "иван",
    "иванович",
    "тестировании",
    "по",
    "опыт",
    "стаж",
    "лет",
    "года",
    "год",
    "месяцев",
    "недель",
    "обязанности",
    "функции",
    "задачи",
    "достижения",
    "результаты",
    "ответственность",
    "управление",
    "координация",
    "разработка",
    "внедрение",
    "поддержка",
    "обеспечение",
    "контроль",
    "мониторинг",
    "оптимизация",
    "улучшение",
    "повышение",
    "снижение",
    "увеличение",
    "участие",
    "взаимодействие",
    "коммуникация",
    "сотрудничество",
    "вакансия",
    "hh",
    "headhunter",
    "superjob",
    "rabota",
    "авито",
    "тенчэт",
    "tenchat",
    "linkedin",
    "hh.ru",
    "москва",
    "санкт-петербург",
    "екатеринбург",
    "новосибирск",
    "казань",
    "нижний новгород",
    "челябинск",
    "самара",
    "уфа",
    "ростов-на-дону",
    "красноярск",
    "воронеж",
    "пермь",
    "волгоград",
    "россия",
    "снг",
    "казахстан",
    "беларусь",
    "украина",
    "удаленка",
    "удалённо",
    "офис",
    "гибрид",
    "релокация",
    "сроков",
    "реализации",
    "проектов",
    "релизов",
    "выполнения",
    "процессов",
    "систем",
    "версий",
    "клиентов",
    "рынков",
    "соцсетях",
    "разработчик",
    "менеджер",
    "аналитик",
    "инженер",
    "специалист",
    "руководитель",
    "директор",
    "ведущий",
    "старший",
    "младший",
}

# ── TECH SKILLS TO VALIDATE ──────────────────────────────────────────────────
# If any of these appear in the ADAPTED text but NOT in the ORIGINAL,
# it is a hallucinated skill.  All entries are lowercase for matching.
TECH_SKILLS: Set[str] = {
    # Languages
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c#",
    "golang",
    "go",
    "rust",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "r",
    "perl",
    "lua",
    "dart",
    "elixir",
    "clojure",
    "haskell",
    "matlab",
    "fortran",
    "cobol",
    # Databases
    "sql",
    "nosql",
    "postgresql",
    "mysql",
    "sqlite",
    "mongodb",
    "redis",
    "elasticsearch",
    "cassandra",
    "dynamodb",
    "neo4j",
    "clickhouse",
    "oracle",
    "mssql",
    "mariadb",
    # DevOps / Cloud
    "docker",
    "kubernetes",
    "k8s",
    "terraform",
    "ansible",
    "puppet",
    "chef",
    "jenkins",
    "gitlab",
    "github",
    "bitbucket",
    "git",
    "svn",
    "linux",
    "bash",
    "shell",
    "powershell",
    "aws",
    "azure",
    "gcp",
    "google cloud",
    "heroku",
    "digitalocean",
    "prometheus",
    "grafana",
    "kibana",
    "datadog",
    "newrelic",
    "nginx",
    "apache",
    "haproxy",
    # Frameworks / Libraries
    "react",
    "vue",
    "angular",
    "svelte",
    "next.js",
    "nuxt",
    "node.js",
    "nodejs",
    "express",
    "fastify",
    "django",
    "flask",
    "fastapi",
    "aiohttp",
    "spring",
    "spring boot",
    "hibernate",
    "quarkus",
    "micronaut",
    "rails",
    "laravel",
    "symfony",
    "graphql",
    "rest",
    "grpc",
    "soap",
    "websocket",
    # Data / ML / AI
    "kafka",
    "rabbitmq",
    "celery",
    "airflow",
    "spark",
    "hadoop",
    "flink",
    "pandas",
    "numpy",
    "scipy",
    "matplotlib",
    "seaborn",
    "plotly",
    "tensorflow",
    "pytorch",
    "keras",
    "scikit-learn",
    "xgboost",
    "lightgbm",
    "hugging face",
    "langchain",
    "openai",
    "llm",
    "rag",
    # Methodologies / Tools
    "agile",
    "scrum",
    "kanban",
    "safe",
    "waterfall",
    "jira",
    "confluence",
    "trello",
    "asana",
    "notion",
    "figma",
    "sketch",
    "photoshop",
    "illustrator",
    "tableau",
    "power bi",
    "looker",
    "metabase",
}

# ── COMPANY PATTERNS ─────────────────────────────────────────────────────────
COMPANY_PATTERNS = [
    r"(?:Яндекс|Google|Microsoft|Amazon|Apple|Meta|Netflix|Uber|Airbnb|Spotify"
    r"|Telegram|VK|Mail\.ru|Ozon|Wildberries|Tinkoff|Сбер|Сбербанк|ВТБ"
    r"|Альфа-Банк|Тинькофф|МТС|Билайн|МегаФон|Tele2|Ростелеком)",
    r"(?:работал в|работала в|трудился в|в компании|из компании)\s+"
    r"([А-Я][а-яА-Я0-9]+(?:\s+[А-Я][а-яА-Я0-9]+)*)",
    r"([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*\s+(?:ООО|ЗАО|АО|ИП|Ltd|LLC|Inc|GmbH|S\.A\.))",
]

# ── POSITION PATTERNS ────────────────────────────────────────────────────────
POSITION_PATTERNS = [
    r'(?:должность|позиция|роль|работал как|работала как)\s*[":\-]?\s*'
    r"([А-Яа-я][А-Яа-я\s\-]{5,50})(?:[,\.\n]|$)",
]


def _scan_tech_skills(text: str) -> Set[str]:
    """Return all TECH_SKILLS that appear (word-boundary match) in text."""
    found: Set[str] = set()
    text_lower = text.lower()
    for skill in TECH_SKILLS:
        # Use word boundaries; handle skills like 'c++' that have special chars
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, text_lower):
            found.add(skill)
    return found


def _extract_years(text: str) -> Set[str]:
    """Extract 4-digit employment years (1990–2030) from text."""
    return set(re.findall(r"\b(199\d|20[0-2]\d|2030)\b", text))


def extract_entities(text: str) -> Dict[str, Set[str]]:
    """Extract named entities from text."""
    entities: Dict[str, Set[str]] = {
        "companies": set(),
        "dates": set(),
        "years": set(),
        "skills": set(),
        "projects": set(),
        "positions": set(),
    }

    # ── Companies ────────────────────────────────────────────────────────────
    for pattern in COMPANY_PATTERNS:
        for m in re.findall(pattern, text, re.IGNORECASE):
            company = m.strip() if isinstance(m, str) else m
            if len(company) > 3 and company.lower() not in STOP_WORDS:
                if any(c.isupper() for c in company):
                    entities["companies"].add(company)

    # ── Dates (full spans, for reference) ────────────────────────────────────
    date_patterns = [
        r"(\d{4}\s*[–\-]\s*\d{4})",
        r"(\d{4}\s*[–\-]\s*н\.?\s*в\.?)",
        r"([а-яА-Я]{3,}\s+\d{4}\s*[–\-]\s*[а-яА-Я]{3,}\s+\d{4})",
    ]
    for pattern in date_patterns:
        for m in re.findall(pattern, text, re.IGNORECASE):
            d = m.strip()
            if len(d) >= 7:
                entities["dates"].add(d)

    # ── Years (validated individually) ───────────────────────────────────────
    entities["years"] = _extract_years(text)

    # ── Tech skills (full-text scan against whitelist) ────────────────────────
    entities["skills"] = _scan_tech_skills(text)

    # ── Additional skills from section headers (Cyrillic soft skills) ─────────
    skill_markers = [
        "навыки:",
        "умения:",
        "компетенции:",
        "технологии:",
        "ключевые слова:",
        "стек:",
        "skills:",
        "technologies:",
    ]
    for marker in skill_markers:
        idx = text.lower().find(marker)
        if idx != -1:
            section = text[idx + len(marker) :].split("\n\n")[0]
            cyrillic_skills = re.findall(
                r"[А-ЯA-Za-z][А-Яа-яA-Za-z\+\#\.]+(?:\s+[А-ЯA-Za-za-я\+\#\.]+)*",
                section,
            )
            for s in cyrillic_skills:
                if len(s) > 3 and s.lower() not in STOP_WORDS:
                    entities["skills"].add(s.strip().lower())

    # ── Positions ─────────────────────────────────────────────────────────────
    for pattern in POSITION_PATTERNS:
        for m in re.findall(pattern, text, re.IGNORECASE):
            position = m.strip()
            bad_words = {
                "сроков",
                "качества",
                "реализации",
                "проектов",
                "релизов",
                "выполнения",
                "задач",
                "работы",
            }
            if len(position) > 5 and position.lower() not in STOP_WORDS:
                if not any(w in position.lower() for w in bad_words):
                    entities["positions"].add(position)

    # ── Projects ──────────────────────────────────────────────────────────────
    # Only match "проект: Name" with an explicit colon separator.
    # Non-greedy match stops at em-dash, comma, period, or newline.
    # This prevents sentence fragments ("ами и командами") from matching.
    project_patterns = [
        r"(?:проект|project)\s*:\s*([А-ЯA-Za-z][^\n—–]{5,45}?)(?:\s*[—–,\.]|\n|$)",
    ]
    for pattern in project_patterns:
        for m in re.findall(pattern, text, re.IGNORECASE):
            project = m.strip()
            # Must start with a capital letter (proper noun) and not be a stop phrase
            if (
                len(project) > 5
                and project[0].isupper()
                and project.lower() not in STOP_WORDS
            ):
                entities["projects"].add(project)

    return entities


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _filter_truly_new(
    new_items: Set[str], original_items: Set[str], threshold: float = 0.75
) -> List[str]:
    """Return items from new_items that have no similar match in original_items."""
    truly_new = []
    for item in new_items:
        if not any(_similarity(item, orig) >= threshold for orig in original_items):
            truly_new.append(item)
    return truly_new


def validate_resume_facts(original_text: str, adapted_text: str) -> Dict[str, Any]:
    """
    Compare original and adapted resumes and detect hallucinated entities.

    Severity levels used in issues list:
      🚨  CRITICAL  — fabricated company, year, or position
      ⚠️  WARNING   — new tech skills or many new soft skills
      ℹ️  INFO      — minor stylistic additions (≤2 new soft skills)

    is_safe = True only when there are zero CRITICAL or WARNING issues.
    confidence  ∈ [0.0, 1.0]: probability estimate that the text is clean.
    """
    issues: List[str] = []
    penalty: float = 0.0

    orig = extract_entities(original_text)
    adpt = extract_entities(adapted_text)

    # ── 1. Companies (CRITICAL) ───────────────────────────────────────────────
    new_companies = adpt["companies"] - orig["companies"]
    truly_new_companies = _filter_truly_new(
        new_companies, orig["companies"], threshold=0.70
    )
    if truly_new_companies:
        issues.append(f"🚨 Новые компании: {', '.join(truly_new_companies)}")
        penalty += 0.5 * len(truly_new_companies)

    # ── 2. Years / dates (CRITICAL) ───────────────────────────────────────────
    new_years = adpt["years"] - orig["years"]
    if new_years:
        issues.append(f"🚨 Новые годы (не из резюме): {', '.join(sorted(new_years))}")
        penalty += 0.4 * len(new_years)

    # ── 3. Positions (CRITICAL) ───────────────────────────────────────────────
    new_positions = adpt["positions"] - orig["positions"]
    truly_new_positions = _filter_truly_new(
        new_positions, orig["positions"], threshold=0.60
    )
    if truly_new_positions:
        issues.append(f"🚨 Новые должности: {', '.join(truly_new_positions)}")
        penalty += 0.4 * len(truly_new_positions)

    # ── 4. Tech skills (WARNING) ──────────────────────────────────────────────
    # Only skills that are in our validated TECH_SKILLS set are checked here.
    orig_tech = orig["skills"] & TECH_SKILLS
    adpt_tech = adpt["skills"] & TECH_SKILLS
    new_tech_skills = adpt_tech - orig_tech
    if new_tech_skills:
        issues.append(
            f"⚠️ Новые технические навыки: {', '.join(sorted(new_tech_skills))}"
        )
        penalty += 0.25 * len(new_tech_skills)

    # ── 5. Soft / general skills (WARNING / INFO) ─────────────────────────────
    orig_soft = orig["skills"] - TECH_SKILLS
    adpt_soft = adpt["skills"] - TECH_SKILLS
    new_soft = adpt_soft - orig_soft
    truly_new_soft = _filter_truly_new(new_soft, orig_soft, threshold=0.65)
    if len(truly_new_soft) > 3:
        issues.append(f"⚠️ Много новых навыков: {', '.join(list(truly_new_soft)[:5])}…")
        penalty += 0.15
    elif len(truly_new_soft) > 0:
        issues.append(f"ℹ️ Незначительные новые навыки: {', '.join(truly_new_soft)}")
        # no penalty for 1-3 minor soft skills

    # ── 6. Projects (WARNING) ─────────────────────────────────────────────────
    new_projects = adpt["projects"] - orig["projects"]
    truly_new_projects = _filter_truly_new(
        new_projects, orig["projects"], threshold=0.65
    )
    if truly_new_projects:
        issues.append(f"⚠️ Новые проекты: {', '.join(truly_new_projects)}")
        penalty += 0.2 * len(truly_new_projects)

    # ── Result ────────────────────────────────────────────────────────────────
    critical_or_warning = [i for i in issues if i.startswith("🚨") or i.startswith("⚠️")]
    is_safe = len(critical_or_warning) == 0
    confidence = max(0.0, round(1.0 - min(penalty, 1.0), 3))

    return {
        "is_safe": is_safe,
        "issues": issues,
        "confidence": confidence,
        "original_entities": {k: list(v) for k, v in orig.items()},
        "adapted_entities": {k: list(v) for k, v in adpt.items()},
        "new_tech_skills": sorted(new_tech_skills),
        "new_years": sorted(new_years),
    }


def get_validation_summary(result: Dict[str, Any]) -> str:
    """Return a human-readable summary of validation results."""
    if result["is_safe"]:
        conf = result["confidence"] * 100
        extra = ""
        if result["issues"]:  # only INFO issues
            extra = "\n  " + "\n  ".join(result["issues"])
        return f"✅ Валидация пройдена (уверенность: {conf:.0f}%){extra}"

    summary_lines = [
        f"❌ Обнаружены галлюцинации (уверенность: {result['confidence'] * 100:.0f}%):"
    ]
    for issue in result["issues"]:
        summary_lines.append(f"  {issue}")
    return "\n".join(summary_lines)
