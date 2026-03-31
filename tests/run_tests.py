#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tests/run_tests.py
"""
Запуск тестов на галлюцинации с реальным GigaChat API.
Версия: 5.0
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.resume_generator import AntiHallucinationGenerator
from tests.test_hallucinations import HallucinationTester, SAMPLE_TEST_CASES
from gigachat import GigaChat


# ── Test cases ────────────────────────────────────────────────────────────────
# Rule: forbidden_keywords = words that MUST NOT appear in the final output.
#       Only list words that are NOT already in the original resume.
#       A test passes if no forbidden keyword is found in the final output —
#       even if the fallback was used (original resume returned safely).

CUSTOM_TEST_CASES = [
    {
        "id": "test_001",
        "description": "Python developer adapted for a Django vacancy",
        "resume": (
            "Иван Иванов, разработчик.\n"
            "Опыт: 2020–2023 Яндекс — Python-разработчик.\n"
            "Навыки: Python, Django, PostgreSQL, Git, Docker."
        ),
        "vacancy": "Требуется Senior Python Developer с опытом в Django, REST API.",
        "expected_keywords": ["python", "django", "яндекс"],
        # Only words NOT in the resume — we don't ban what's already there
        "forbidden_keywords": ["java", "manager", "2025", "сбер", "тинькофф"],
    },
    {
        "id": "test_002",
        "description": "Lawyer resume sent to a Data Analyst vacancy — should NOT gain SQL/Python",
        "resume": (
            "Анна Петрова, юрист.\n"
            "Опыт: 2018–2024 ООО Правозащита — Юрисконсульт.\n"
            "Работа с договорами, судебными делами, корпоративным правом.\n"
            "Навыки: MS Word, Excel, правовые базы данных."
        ),
        "vacancy": "Требуется Data Analyst с опытом в SQL, Python, визуализации данных.",
        "expected_keywords": ["договор", "юрист", "excel"],
        "forbidden_keywords": [
            "sql",
            "python",
            "tensorflow",
            "machine learning",
            "2030",
            "google",
        ],
    },
    {
        "id": "test_003",
        "description": "Marketing manager resume for Product Manager vacancy — must not gain invented companies",
        "resume": (
            "Сергей Сидоров, маркетинг-менеджер.\n"
            "Опыт: 2019–2024 ООО МедиаГрупп — Digital-маркетолог.\n"
            "SMM, контекстная реклама, аналитика, управление командой 5 человек.\n"
            "Навыки: Google Ads, Яндекс.Директ, Excel, Tableau."
        ),
        "vacancy": "Требуется Product Manager с опытом в IT-продуктах, Agile, Scrum.",
        "expected_keywords": ["маркетинг", "smm", "аналитика"],
        # Google Ads and Яндекс.Директ ARE in the resume, so we don't ban them.
        # We ban companies that could be invented from scratch.
        "forbidden_keywords": ["сбер", "tinkoff", "тинькофф", "мтс", "ozon", "2030"],
    },
]


def main():
    print("🔍 Инициализация GigaChat API...")
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key:
        print("❌ Ошибка: GIGACHAT_API_KEY не найден!")
        print("🔧 Добавьте ключ в Replit Secrets / .env")
        return None

    try:
        gigachat = GigaChat(credentials=api_key, verify_ssl_certs=False)
        print("✅ GigaChat подключён успешно!")
    except Exception as e:
        print(f"❌ Ошибка подключения к GigaChat: {e}")
        return None

    generator = AntiHallucinationGenerator(gigachat, max_retries=2)
    tester = HallucinationTester(generator)

    # Combine built-in sample cases with our custom ones
    all_cases = CUSTOM_TEST_CASES + SAMPLE_TEST_CASES

    print(f"\n🧪 Запуск {len(all_cases)} тестов...")
    print("=" * 60)

    report = tester.run_test_batch(all_cases)
    tester.print_details()
    tester.export_report("hallucination_test_report.json")

    return report


if __name__ == "__main__":
    result = main()
    if not result:
        print("\n❌ Тесты не были запущены из-за ошибки подключения!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)

    total = result["total_tests"]
    h_count = result["hallucinations"]
    h_rate = result["hallucination_rate"] * 100
    fallback = result["fallback_count"]
    passed = result["hypothesis_passed"]

    print(f"  Всего тестов         : {total}")
    print(f"  Галлюцинаций         : {h_count}  ({h_rate:.1f}%)   ← цель ≤ 15%")
    print(f"  Использован fallback : {fallback}  (оригинал вернулся без изменений)")
    print(f"  Валидация пройдена   : {result['validation_passed_count']} / {total}")
    print(f"  Средняя уверенность  : {result['average_confidence'] * 100:.1f}%")
    print()

    if passed:
        print("  ✅ ГИПОТЕЗА ПОДТВЕРЖДЕНА — галлюцинаций ≤ 15%")
    else:
        print("  ❌ ГИПОТЕЗА НЕ ПОДТВЕРЖДЕНА — нужна доработка промптов")
        # Print failing tests so it's clear what to fix
        failing = [r for r in result["details"] if r["has_hallucination"]]
        for f in failing:
            print(f"\n  ⚠️  [{f['test_id']}] {f.get('description', '')}")
            print(f"      Forbidden found : {f['found_forbidden']}")
            print(f"      Validator issues: {f['issues']}")

    print("=" * 60)
    sys.exit(0 if passed else 1)
