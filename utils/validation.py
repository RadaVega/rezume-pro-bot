# utils/validation.py
"""
Утилиты для валидации сущностей и обнаружения галлюцинаций.
Версия: 6.0 (Исправлены ложные срабатывания)
"""

import re
from typing import Dict, Set, List
from difflib import SequenceMatcher


# === СТОП-СЛОВА ДЛЯ КОМПАНИЙ ===
COMPANY_STOP_WORDS = {
    "компания",
    "организация",
    "ооо",
    "зао",
    "ао",
    "ип",
    "ltd",
    "llc",
    "inc",
    "гмбх",
    "s.a.",
    "резюме",
    "вакансия",
    "hh",
    "headhunter",
    "superjob",
    "работа",
    "авито",
    "тенчэт",
    "tenchat",
    "linkedin",
    "hh.ru",
    "rabota",
    "москва",
    "санкт-петербург",
    "екатеринбург",
    "новосибирск",
    "казань",
    "россия",
    "снг",
    "удаленка",
    "удалённо",
    "офис",
    "гибрид",
    # Критично: слова которые НЕ являются компаниями
    "качество",
    "распредел",
    "резюме",
    "через",
    "работы",
    "проекты",
    "внутренними",
    "корпоративными",
    "ами",
    "командами",
    "ной",
    "численностью",
}

# === ИЗВЕСТНЫЕ КОМПАНИИ (БЕЛЫЙ СПИСОК) ===
KNOWN_COMPANIES = {
    "яндекс",
    "google",
    "microsoft",
    "amazon",
    "apple",
    "meta",
    "netflix",
    "uber",
    "airbnb",
    "spotify",
    "telegram",
    "vk",
    "mail.ru",
    "ozon",
    "wildberries",
    "tinkoff",
    "сбер",
    "сбербанк",
    "втб",
    "альфа-банк",
    "тинькофф",
    "mts",
    "билайн",
    "мегафон",
    "tele2",
    "rostelecom",
}

# === СТОП-СЛОВА ДЛЯ НАВЫКОВ (Исключаем ложные срабатывания) ===
SKILL_STOP_WORDS = {
    # Методологии (не технические навыки)
    "agile",
    "scrum",
    "kanban",
    "waterfall",
    "lean",
    # Общие слова
    "rest",
    "api",
    "web",
    "mobile",
    "desktop",
    "cloud",
    # Части слов (артефакты парсинга)
    "ами",
    "командами",
    "ной",
    "распредел",
    "качество",
    # Фразы из резюме
    "навык работы",
    "нет в резюме",
    "правовыми базами",
}

# === СТОП-СЛОВА ДЛЯ ДОЛЖНОСТЕЙ ===
POSITION_STOP_WORDS = {
    "сроков",
    "качества",
    "реализации",
    "проектов",
    "релизов",
    "выполнения",
    "задач",
    "работы",
    "процессов",
    "систем",
    "разработки",
    "внедрения",
    "поддержки",
    "управления",
    "команды",
    "клиентов",
    "рынков",
    "соцсетях",
    "версий",
}


def extract_companies(text: str) -> Set[str]:
    """Извлекает компании из текста с умной фильтрацией."""
    companies = set()

    # Паттерн 1: Компании с организационно-правовой формой
    pattern1 = (
        r"([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*(?:\s+(?:ООО|ЗАО|АО|ИП|Ltd|LLC|Inc|GmbH)))"
    )
    for match in re.findall(pattern1, text, re.IGNORECASE):
        company = match.strip()
        if len(company) > 4 and company.lower() not in COMPANY_STOP_WORDS:
            companies.add(company)

    # Паттерн 2: Известные компании
    for known in KNOWN_COMPANIES:
        pattern = rf"\b{known}\b"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            companies.add(match.group())

    # Паттерн 3: После предлогов "в", "из", "работал в"
    pattern3 = r"(?:работал в|работала в|трудился в|в компании|из компании)\s+([А-Я][а-яА-Я0-9]+(?:\s+[А-Я][а-яА-Я0-9]+)*)"
    for match in re.findall(pattern3, text, re.IGNORECASE):
        company = match.strip()
        if len(company) > 3 and company.lower() not in COMPANY_STOP_WORDS:
            companies.add(company)

    return companies


def extract_skills(text: str) -> Set[str]:
    """Извлекает технические навыки из текста."""
    skills = set()

    # Ищем в секциях навыков
    skill_markers = [
        "навыки:",
        "умения:",
        "технологии:",
        "ключевые слова:",
        "стек:",
        "skills:",
        "technologies:",
    ]
    for marker in skill_markers:
        if marker in text.lower():
            section = text.split(marker.lower())[-1].split("\n\n")[0]
            # Извлекаем слова с заглавной буквы или технические термины
            candidates = re.findall(
                r"[А-Я][а-я]+(?:\s+[А-Я][а-я]+)*|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*",
                section,
            )
            for c in candidates:
                skill = c.strip()
                if len(skill) > 2 and skill.lower() not in SKILL_STOP_WORDS:
                    # Исключаем части предложений
                    if not any(
                        word in skill.lower()
                        for word in ["ами", "командами", "ной", "распредел"]
                    ):
                        skills.add(skill)

    return skills


def extract_positions(text: str) -> Set[str]:
    """Извлекает должности из текста."""
    positions = set()

    pattern = r'(?:должность|позиция|роль|работал как)\s*[":\-]?\s*([А-Я][а-яА-я\s\-]{5,50})(?:[,\.\n]|$)'
    for match in re.findall(pattern, text, re.IGNORECASE):
        position = match.strip()
        if len(position) > 5 and position.lower() not in POSITION_STOP_WORDS:
            positions.add(position)

    return positions


def normalize_company_name(company: str) -> str:
    """Нормализует название компании для сравнения."""
    normalized = re.sub(
        r"\s+(?:ООО|ЗАО|АО|ИП|Ltd|LLC|Inc|GmbH|S\.A\.)",
        "",
        company,
        flags=re.IGNORECASE,
    )
    normalized = normalized.lower().strip()
    normalized = " ".join(normalized.split())
    return normalized


def companies_are_similar(comp1: str, comp2: str) -> bool:
    """Проверяет, являются ли две компании одинаковыми."""
    norm1 = normalize_company_name(comp1)
    norm2 = normalize_company_name(comp2)

    if norm1 == norm2:
        return True

    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    if similarity > 0.7:
        return True

    if norm1 in norm2 or norm2 in norm1:
        return True

    return False


def validate_resume_facts(original_text: str, adapted_text: str) -> Dict[str, any]:
    """
    Проверяет, не добавил ли ИИ новые сущности.
    ДАТЫ ИСКЛЮЧЕНЫ ИЗ ВАЛИДАЦИИ.
    """
    issues = []
    confidence_scores = []

    # Извлекаем сущности
    original_companies = extract_companies(original_text)
    adapted_companies = extract_companies(adapted_text)

    original_skills = extract_skills(original_text)
    adapted_skills = extract_skills(adapted_text)

    original_positions = extract_positions(original_text)
    adapted_positions = extract_positions(adapted_text)

    # === Проверка компаний ===
    truly_new_companies = []
    for new_comp in adapted_companies:
        is_duplicate = False
        for orig_comp in original_companies:
            if companies_are_similar(new_comp, orig_comp):
                is_duplicate = True
                break
        if not is_duplicate:
            truly_new_companies.append(new_comp)

    if truly_new_companies:
        issues.append(f"⚠️ Новые компании: {', '.join(truly_new_companies)}")
        confidence_scores.append(0.3)

    # === Проверка навыков (только критичные) ===
    new_skills = adapted_skills - original_skills
    # Фильтруем не-технические навыки
    critical_new_skills = [
        s for s in new_skills if s.lower() not in SKILL_STOP_WORDS and len(s) > 3
    ]

    if len(critical_new_skills) > 2:  # Только если много новых навыков
        issues.append(
            f"⚠️ Новые технические навыки: {', '.join(critical_new_skills[:3])}"
        )
        confidence_scores.append(0.5)
    elif len(critical_new_skills) > 0:
        issues.append(
            f"ℹ️ Незначительные новые навыки: {', '.join(critical_new_skills)}"
        )
        confidence_scores.append(0.8)  # Высокая уверенность, но не критично

    # === Проверка должностей ===
    truly_new_positions = []
    for new_pos in adapted_positions:
        is_duplicate = False
        for orig_pos in original_positions:
            similarity = SequenceMatcher(
                None, new_pos.lower(), orig_pos.lower()
            ).ratio()
            if similarity > 0.6:
                is_duplicate = True
                break
        if not is_duplicate:
            truly_new_positions.append(new_pos)

    if truly_new_positions:
        issues.append(f"⚠️ Новые должности: {', '.join(truly_new_positions)}")
        confidence_scores.append(0.5)

    # === Итоговая оценка ===
    # is_safe = true если нет критических проблем (компании)
    has_critical_issues = any("⚠️ Новые компании" in issue for issue in issues)
    is_safe = not has_critical_issues

    avg_confidence = (
        sum(confidence_scores) / len(confidence_scores) if confidence_scores else 1.0
    )

    return {
        "is_safe": is_safe,
        "issues": issues,
        "confidence": avg_confidence,
        "original_companies_count": len(original_companies),
        "adapted_companies_count": len(adapted_companies),
        "dates_excluded": True,
    }


def get_validation_summary(validation_result: Dict[str, any]) -> str:
    """Генерирует читаемое резюме результатов валидации."""
    if validation_result["is_safe"]:
        return "✅ Валидация пройдена"
    else:
        summary = "⚠️ Проблемы валидации:\n"
        for issue in validation_result["issues"]:
            summary += f"  - {issue}\n"
        summary += f"Уверенность: {validation_result['confidence'] * 100:.1f}%"
        return summary
