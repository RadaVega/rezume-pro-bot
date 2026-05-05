# services/resume_generator.py
"""
Сервис генерации резюме с защитой от галлюцинаций.
Версия: 5.5 – added logging and truncation
"""

import logging
from typing import Tuple, Dict, Any
from prompts.anti_hallucination import (
    SYSTEM_PROMPT_ANTI_HALLUCINATION,
    SYSTEM_PROMPT_COVER_LETTER,
    RETRY_CORRECTION_SUFFIX,
)
from utils.validation import validate_resume_facts

logger = logging.getLogger(__name__)


class AntiHallucinationGenerator:
    """Генератор резюме с многоуровневой защитой от галлюцинаций."""

    def __init__(self, gigachat_client, max_retries: int = 2):
        self.gigachat = gigachat_client
        self.max_retries = max_retries

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _call_gigachat(self, prompt: str) -> str:
        """
        Call GigaChat with a plain string prompt.
        Logs prompt length and response details to debug empty responses.
        """
        logger.info(f"📤 Calling GigaChat, prompt length: {len(prompt)} chars")
        try:
            response = self.gigachat.chat(prompt)
            logger.info(f"📥 Response type: {type(response)}")
            
            if hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content
                logger.info(f"✅ Content length: {len(content) if content else 0}")
                if content:
                    logger.debug(f"Content preview: {content[:200]}")
                return content.strip() if content else ""
            if isinstance(response, str):
                logger.info(f"✅ String response length: {len(response)}")
                return response.strip()
            if hasattr(response, "text"):
                logger.info(f"✅ Response.text length: {len(response.text)}")
                return response.text.strip()
            logger.warning(f"Unexpected response structure: {response}")
            return ""
        except Exception as e:
            logger.error(f"❌ GigaChat call failed: {e}", exc_info=True)
            return ""

    def _build_base_prompt(self, resume_text: str, vacancy_text: str) -> str:
        # Truncate to avoid token limits
        resume_text = (resume_text[:3000] + "…") if len(resume_text) > 3000 else resume_text
        vacancy_text = (vacancy_text[:2000] + "…") if len(vacancy_text) > 2000 else vacancy_text
        return SYSTEM_PROMPT_ANTI_HALLUCINATION.format(
            resume_text=resume_text,
            vacancy_text=vacancy_text,
        )

    def _enrich_prompt(self, base_prompt: str, resume_text: str) -> str:
        from utils.validation import extract_entities, TECH_SKILLS

        entities = extract_entities(resume_text)
        allowed_tech = sorted(entities["skills"] & TECH_SKILLS)
        allowed_companies = sorted(entities["companies"])
        allowed_years = sorted(entities["years"])

        lines = [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📋 ТОЧНЫЙ СПИСОК ТОГО, ЧТО ЕСТЬ В РЕЗЮМЕ:",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if allowed_tech:
            lines.append(f"  ✅ Технические навыки: {', '.join(allowed_tech)}")
        else:
            lines.append("  ✅ Технические навыки: НЕ УКАЗАНЫ (не добавляй ни одного)")

        if allowed_companies:
            lines.append(f"  ✅ Компании: {', '.join(allowed_companies)}")

        if allowed_years:
            lines.append(f"  ✅ Годы работы: {', '.join(allowed_years)}")

        lines += [
            "",
            "⛔ АБСОЛЮТНЫЙ ЗАПРЕТ: не добавляй НИ ОДНОГО технического навыка,",
            "   компании или даты, которых нет в списке выше.",
            "   Если вакансия требует навык не из списка — просто пропусти его.",
            "   НЕ ПИШИ '[Нет в резюме]' или 'Навык не указан' — просто пропусти.",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        return base_prompt + "\n".join(lines)

    def _build_retry_prompt(self, base_prompt: str, issues: list, attempt: int) -> str:
        correction = RETRY_CORRECTION_SUFFIX.format(
            attempt=attempt,
            issues="; ".join(issues),
        )
        return base_prompt + correction

    @staticmethod
    def _fallback_response(resume_text: str, issues: list) -> str:
        attempt_count = len(issues)
        return (
            resume_text
            + "\n\n"
            + "─" * 60
            + "\n"
            + "⚠️ ВНИМАНИЕ: Не удалось безопасно адаптировать резюме "
            + f"после {attempt_count} попыток.\n"
            + "Возвращаем исходный текст без изменений.\n"
            + "─" * 60
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_safe_resume(
        self, resume_text: str, vacancy_text: str
    ) -> Tuple[str, Dict[str, Any]]:
        metadata: Dict[str, Any] = {
            "attempts": 0,
            "validation_passed": False,
            "fallback_used": False,
            "issues": [],
            "validation": None,
        }

        base_prompt = self._enrich_prompt(
            self._build_base_prompt(resume_text, vacancy_text),
            resume_text,
        )

        for attempt in range(self.max_retries + 1):
            metadata["attempts"] = attempt + 1

            try:
                if attempt == 0:
                    prompt = base_prompt
                else:
                    prompt = self._build_retry_prompt(
                        base_prompt, metadata["issues"], attempt
                    )

                adapted_text = self._call_gigachat(prompt)
                if not adapted_text:
                    logger.warning(f"⚠️ Empty response on attempt {attempt + 1}")
                    continue

                validation = validate_resume_facts(resume_text, adapted_text)
                metadata["validation"] = validation

                logger.info(
                    f"Attempt {attempt + 1}: "
                    f"{'PASS' if validation['is_safe'] else 'FAIL'} | "
                    f"confidence={validation['confidence']:.2f} | "
                    f"issues={len(validation['issues'])}"
                )

                if validation["is_safe"]:
                    metadata["validation_passed"] = True
                    return adapted_text, metadata

                metadata["issues"] = validation["issues"]

            except Exception as e:
                logger.error(f"❌ Generation error on attempt {attempt + 1}: {e}")

        metadata["fallback_used"] = True
        logger.error(
            f"❌ All {self.max_retries + 1} attempts failed. "
            f"Using fallback. Last issues: {metadata['issues']}"
        )
        return self._fallback_response(resume_text, metadata["issues"]), metadata

    def generate_cover_letter(
        self, resume_text: str, vacancy_text: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate a cover letter. Truncates inputs and bypasses all validation.
        """
        metadata: Dict[str, Any] = {
            "attempts": 0,
            "validation_passed": False,
            "fallback_used": False,
            "issues": [],
            "validation": None,
        }

        # Truncate to avoid excessive token usage
        resume_text = (resume_text[:2500] + "…") if len(resume_text) > 2500 else resume_text
        vacancy_text = (vacancy_text[:2000] + "…") if len(vacancy_text) > 2000 else vacancy_text

        base_prompt = self._enrich_prompt(
            SYSTEM_PROMPT_COVER_LETTER.format(
                resume_text=resume_text,
                vacancy_text=vacancy_text,
            ),
            resume_text,
        )

        for attempt in range(self.max_retries + 1):
            metadata["attempts"] = attempt + 1

            try:
                prompt = (
                    base_prompt
                    if attempt == 0
                    else self._build_retry_prompt(base_prompt, metadata["issues"], attempt)
                )

                letter_text = self._call_gigachat(prompt)
                if not letter_text:
                    logger.warning(f"Empty response on attempt {attempt + 1}")
                    continue

                # Accept any non‑empty response
                logger.info(f"Cover letter attempt {attempt + 1}: ACCEPTED (length={len(letter_text)})")
                metadata["validation_passed"] = True
                return letter_text, metadata

            except Exception as e:
                logger.error(f"❌ Cover letter error on attempt {attempt + 1}: {e}")

        metadata["fallback_used"] = True
        fallback_letter = (
            "⚠️ Не удалось сгенерировать сопроводительное письмо.\n\n"
            "Пожалуйста, напишите его вручную на основе вашего резюме."
        )
        return fallback_letter, metadata