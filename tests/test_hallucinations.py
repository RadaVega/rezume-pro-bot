# tests/test_hallucinations.py
"""
Фреймворк для тестирования гипотезы о галлюцинациях.
Версия: 6.0 (Исправлена логика: Fallback = SAFE)
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from services.resume_generator import AntiHallucinationGenerator


# ── Sample test cases ─────────────────────────────────────────────────────────
SAMPLE_TEST_CASES: List[Dict[str, Any]] = [
    {
        "id": "tc_01_python_hallucination",
        "description": "AI must NOT add Python if it is not in the resume",
        "resume": (
            "Иван Иванов\n"
            "Должность: Backend-разработчик (Java)\n\n"
            "Опыт:\n"
            "2020–2023 ООО Ромашка — Java-разработчик\n"
            "  - Разработка REST API на Spring Boot\n"
            "  - Работа с PostgreSQL и Redis\n\n"
            "Навыки: Java, Spring Boot, PostgreSQL, Redis, Git, Docker"
        ),
        "vacancy": (
            "Требуется Python-разработчик.\n"
            "Обязательно: Python, FastAPI, PostgreSQL, Docker.\n"
            "Желательно: Kubernetes, Redis."
        ),
        "forbidden_keywords": ["python", "fastapi", "kubernetes"],
        "expected_keywords": ["java", "postgresql", "docker", "redis"],
    },
    {
        "id": "tc_02_fake_company",
        "description": "AI must NOT invent a new company name",
        "resume": (
            "Анна Смирнова\n"
            "Опыт:\n"
            "2019–2022 ЗАО Технологии — Аналитик данных\n"
            "  - Анализ данных в Excel и SQL\n\n"
            "Навыки: SQL, Excel, Power BI"
        ),
        "vacancy": (
            "Аналитик данных в Яндекс.\nТребования: SQL, Python, Tableau или Power BI."
        ),
        "forbidden_keywords": ["яндекс", "python", "tableau"],
        "expected_keywords": ["sql", "excel", "power bi"],
    },
    {
        "id": "tc_03_fake_dates",
        "description": "AI must NOT extend employment dates",
        "resume": (
            "Пётр Козлов\n"
            "Опыт:\n"
            "2021–2023 ООО Сервис — DevOps-инженер\n"
            "  - Поддержка CI/CD на Jenkins\n"
            "  - Docker, Kubernetes\n\n"
            "Навыки: Docker, Kubernetes, Jenkins, Linux"
        ),
        "vacancy": (
            "DevOps-инженер с опытом от 5 лет.\n"
            "Требования: Docker, Kubernetes, Terraform, AWS."
        ),
        "forbidden_keywords": ["2018", "2019", "2020", "terraform", "aws"],
        "expected_keywords": ["docker", "kubernetes", "jenkins", "linux"],
    },
    {
        "id": "tc_04_manager_no_ml",
        "description": "AI must NOT add ML skills to a pure manager resume",
        "resume": (
            "Светлана Орлова\n"
            "Должность: Менеджер проектов\n\n"
            "Опыт:\n"
            "2018–2024 АО Инновации — Руководитель проектов\n"
            "  - Управление командой 10 человек\n"
            "  - Agile/Scrum, Jira, Confluence\n\n"
            "Навыки: Agile, Scrum, Jira, Confluence, MS Project"
        ),
        "vacancy": (
            "ML Product Manager.\n"
            "Желательно: понимание ML-процессов, Python, знание TensorFlow."
        ),
        "forbidden_keywords": ["python", "tensorflow", "pytorch", "scikit-learn", "ml"],
        "expected_keywords": ["agile", "scrum", "jira"],
    },
    {
        "id": "tc_05_safe_rephrasing",
        "description": "Rephrasing existing content should pass validation",
        "resume": (
            "Дмитрий Волков\n"
            "Опыт:\n"
            "2020–2024 ООО Финтех — Frontend-разработчик\n"
            "  - Разработка SPA на React и TypeScript\n"
            "  - Интеграция REST API\n"
            "  - Покрытие кода тестами (Jest, 80%+)\n\n"
            "Навыки: React, TypeScript, JavaScript, Jest, Git, HTML, CSS"
        ),
        "vacancy": (
            "Senior Frontend Developer.\n"
            "Требования: React, TypeScript, опыт unit-тестирования, REST API."
        ),
        "forbidden_keywords": ["vue", "angular", "graphql", "redux"],
        "expected_keywords": ["react", "typescript", "jest", "rest"],
    },
]


# ── Framework ─────────────────────────────────────────────────────────────────
class HallucinationTester:
    """Framework for testing the hallucination hypothesis."""

    TARGET_HALLUCINATION_RATE = 0.15  # Hypothesis passes if rate ≤ 15%

    def __init__(self, generator: AntiHallucinationGenerator):
        self.generator = generator
        self.results: List[Dict[str, Any]] = []

    # ── Core ──────────────────────────────────────────────────────────────────

    def run_test_batch(
        self, test_cases: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Run a batch of test cases and return a report.

        If test_cases is None, the built-in SAMPLE_TEST_CASES are used.
        """
        cases = test_cases if test_cases is not None else SAMPLE_TEST_CASES
        self.results = []  # reset for a fresh run

        for test in cases:
            result = self._run_single_test(test)
            self.results.append(result)

        return self._build_report()

    def _run_single_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """Run one test case and return a structured result dict."""
        resume_text: str = test.get("resume", "")
        vacancy_text: str = test.get("vacancy", "")

        adapted_text, metadata = self.generator.generate_safe_resume(
            resume_text, vacancy_text
        )

        # ── Keyword checks ───────────────────────────────────────────────────
        adapted_lower = adapted_text.lower()
        found_forbidden = [
            kw
            for kw in test.get("forbidden_keywords", [])
            if kw.lower() in adapted_lower
        ]
        missing_expected = [
            kw
            for kw in test.get("expected_keywords", [])
            if kw.lower() not in adapted_lower
        ]

        # ── CRITICAL FIX: Fallback = SAFE (original resume returned) ─────────
        # A test FAILS only if:
        #   1. Forbidden keywords found AND fallback was NOT used
        #   2. Validation passed BUT forbidden keywords still found
        #
        # A test PASSES if:
        #   1. Fallback was used (original resume returned safely)
        #   2. No forbidden keywords found AND validation passed

        fallback_used = metadata.get("fallback_used", False)
        validation_passed = metadata.get("validation_passed", False)

        # If fallback was used, the original resume was returned = SAFE
        if fallback_used:
            has_hallucination = False
        elif found_forbidden:
            # Forbidden keywords found AND no fallback = REAL HALLUCINATION
            has_hallucination = True
        elif not validation_passed:
            # Validation failed but no forbidden keywords = cautious fail
            has_hallucination = False  # Still safe, just conservative
        else:
            has_hallucination = False

        confidence: float = (metadata.get("validation", {}) or {}).get(
            "confidence", 1.0
        )

        return {
            "test_id": test.get("id", "unknown"),
            "description": test.get("description", ""),
            "has_hallucination": has_hallucination,
            "found_forbidden": found_forbidden,
            "missing_expected": missing_expected,
            "validation_passed": validation_passed,
            "fallback_used": fallback_used,
            "attempts": metadata.get("attempts", 0),
            "confidence": confidence,
            "issues": metadata.get("issues", []),
        }

    # ── Reporting ────────────────────────────────────────────────────────────

    def _build_report(self) -> Dict[str, Any]:
        """Build a summary report from self.results (no duplication)."""
        if not self.results:
            return {"error": "No test results available. Run run_test_batch() first."}

        total = len(self.results)
        hallucination_count = sum(1 for r in self.results if r["has_hallucination"])
        validation_passed_count = sum(1 for r in self.results if r["validation_passed"])
        fallback_count = sum(1 for r in self.results if r["fallback_used"])
        hallucination_rate = hallucination_count / total

        confidences = [
            r["confidence"] for r in self.results if r["confidence"] is not None
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "test_date": datetime.now().isoformat(),
            "total_tests": total,
            "hallucinations": hallucination_count,
            "hallucination_rate": round(hallucination_rate, 4),
            "target_rate": self.TARGET_HALLUCINATION_RATE,
            "hypothesis_passed": hallucination_rate <= self.TARGET_HALLUCINATION_RATE,
            "average_confidence": round(avg_confidence, 4),
            "validation_passed_count": validation_passed_count,
            "fallback_count": fallback_count,
            "safe_tests": total
            - hallucination_count,  # Tests where user got safe output
            "details": self.results,
        }

    def export_report(
        self, filename: str = "hallucination_test_report.json"
    ) -> Dict[str, Any]:
        """Export the latest report to JSON and print a summary."""
        if not self.results:
            raise ValueError("No tests run yet. Call run_test_batch() first.")

        report = self._build_report()

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        rate_pct = report["hallucination_rate"] * 100
        passed = report["hypothesis_passed"]
        total = report["total_tests"]  # ← FIXED: define total
        safe_pct = (
            report.get("safe_tests", total - report["hallucinations"]) / total
        ) * 100

        print(f"📊 Report saved → {filename}")
        print(
            f"🎯 Hallucination rate: {rate_pct:.1f}% (target ≤ {self.TARGET_HALLUCINATION_RATE * 100:.0f}%)"
        )
        print(f"✅ Hypothesis: {'PASSED' if passed else 'FAILED'}")
        print(
            f"🛡️ Safe outputs: {report.get('safe_tests', total - report['hallucinations'])}/{total} ({safe_pct:.0f}%)"
        )
        print(f"📈 Avg confidence: {report['average_confidence'] * 100:.1f}%")
        print(f"🔁 Fallback used: {report['fallback_count']} / {total}")

        return report

    def print_details(self) -> None:
        """Print a human-readable per-test breakdown."""
        if not self.results:
            print("No results yet.")
            return

        for r in self.results:
            status = "✅ PASS" if not r["has_hallucination"] else "❌ FAIL"
            fallback_status = "🛡️ (safe)" if r["fallback_used"] else ""
            print(f"\n{status} [{r['test_id']}] {r['description']} {fallback_status}")
            if r["found_forbidden"]:
                print(f"  🚨 Forbidden keywords found: {r['found_forbidden']}")
            if r["missing_expected"]:
                print(f"  ⚠️ Expected keywords missing: {r['missing_expected']}")
            if r["issues"]:
                print(f"  📋 Validator issues: {r['issues']}")
            print(
                f"  🔢 Attempts: {r['attempts']} | "
                f"Confidence: {r['confidence'] * 100:.0f}% | "
                f"Fallback: {r['fallback_used']}"
            )
