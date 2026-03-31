# services/resume_generator.py
"""
Сервис генерации резюме с защитой от галлюцинаций.
Версия: 5.0
"""

import logging
from typing import Tuple, Optional, Dict, Any
from prompts.anti_hallucination import (
    SYSTEM_PROMPT_ANTI_HALLUCINATION,
    SYSTEM_PROMPT_COVER_LETTER,
    RETRY_CORRECTION_SUFFIX,
)
from utils.validation import validate_resume_facts, get_validation_summary

logger = logging.getLogger(__name__)


class AntiHallucinationGenerator:
    """Генератор резюме с многоуровневой защитой от галлюцинаций."""

    def __init__(self, gigachat_client, max_retries: int = 2):
        self.gigachat = gigachat_client
        self.max_retries = max_retries

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _call_gigachat(self, prompt: str, temperature: float = 0.1) -> str:
        """Call GigaChat with graceful fallback for varying SDK versions."""
        try:
            response = self.gigachat.chat(prompt, temperature=temperature)
        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                logger.warning(
                    f"⚠️ GigaChat: temperature kwarg not supported, retrying: {e}"
                )
                response = self.gigachat.chat(prompt)
            else:
                raise

        if hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content
            return content.strip() if content else ""
        if isinstance(response, str):
            return response.strip()
        if hasattr(response, "text"):
            return response.text.strip()
        return str(response).strip()

    def _build_base_prompt(self, resume_text: str, vacancy_text: str) -> str:
        return SYSTEM_PROMPT_ANTI_HALLUCINATION.format(
            resume_text=resume_text,
            vacancy_text=vacancy_text,
        )

    def _build_retry_prompt(self, base_prompt: str, issues: list, attempt: int) -> str:
        """
        Append a correction note to the BASE prompt (not to previous retries),
        so the prompt length stays bounded.
        """
        correction = RETRY_CORRECTION_SUFFIX.format(
            attempt=attempt,
            issues="; ".join(issues),
        )
        return base_prompt + correction

    @staticmethod
    def _fallback_response(resume_text: str, issues: list) -> str:
        issues_text = (
            "\n".join(f"  - {i}" for i in issues) if issues else "  — нет данных"
        )
        return (
            resume_text
            + "\n\n"
            + "─" * 60
            + "\n"
            + "⚠️ ВНИМАНИЕ: Система не смогла безопасно адаптировать резюме.\n\n"
            + "Причины:\n"
            + issues_text
            + "\n\n"
            + "Ниже — исходный текст резюме без изменений.\n"
            + "─" * 60
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_safe_resume(
        self, resume_text: str, vacancy_text: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate an adapted resume with hallucination validation.

        Returns (adapted_text, metadata).
        If all attempts fail (validation or exception), returns the original
        resume with a warning — never raises to the caller.
        """
        metadata: Dict[str, Any] = {
            "attempts": 0,
            "validation_passed": False,
            "fallback_used": False,
            "issues": [],
            "validation": None,
        }

        base_prompt = self._build_base_prompt(resume_text, vacancy_text)

        for attempt in range(self.max_retries + 1):
            metadata["attempts"] = attempt + 1

            try:
                # ── Build prompt ──────────────────────────────────────────────
                if attempt == 0:
                    prompt = base_prompt
                else:
                    # Retry: append correction note to the ORIGINAL base prompt
                    prompt = self._build_retry_prompt(
                        base_prompt, metadata["issues"], attempt
                    )

                # ── Generate ──────────────────────────────────────────────────
                adapted_text = self._call_gigachat(prompt, temperature=0.1)
                if not adapted_text:
                    logger.warning(f"⚠️ Empty response on attempt {attempt + 1}")
                    continue

                # ── Validate ──────────────────────────────────────────────────
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

                # ── Collect issues for next retry ─────────────────────────────
                # Replace (not accumulate) so the retry prompt stays concise
                metadata["issues"] = validation["issues"]

            except Exception as e:
                logger.error(f"❌ Generation error on attempt {attempt + 1}: {e}")
                # Do NOT re-raise: fall through loop → use fallback

        # ── All attempts exhausted → safe fallback ────────────────────────────
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
        Generate a cover letter with basic hallucination validation.

        Returns (letter_text, metadata).
        """
        metadata: Dict[str, Any] = {
            "attempts": 0,
            "validation_passed": False,
            "fallback_used": False,
            "issues": [],
            "validation": None,
        }

        base_prompt = SYSTEM_PROMPT_COVER_LETTER.format(
            resume_text=resume_text,
            vacancy_text=vacancy_text,
        )

        for attempt in range(self.max_retries + 1):
            metadata["attempts"] = attempt + 1

            try:
                prompt = (
                    base_prompt
                    if attempt == 0
                    else (
                        self._build_retry_prompt(
                            base_prompt, metadata["issues"], attempt
                        )
                    )
                )

                letter_text = self._call_gigachat(prompt, temperature=0.2)
                if not letter_text:
                    continue

                # Cover letters are checked with the same validator.
                # We use the original resume as the source-of-truth.
                validation = validate_resume_facts(resume_text, letter_text)
                metadata["validation"] = validation

                logger.info(
                    f"Cover letter attempt {attempt + 1}: "
                    f"{'PASS' if validation['is_safe'] else 'FAIL'} | "
                    f"confidence={validation['confidence']:.2f}"
                )

                if validation["is_safe"]:
                    metadata["validation_passed"] = True
                    return letter_text, metadata

                metadata["issues"] = validation["issues"]

            except Exception as e:
                logger.error(f"❌ Cover letter error on attempt {attempt + 1}: {e}")

        metadata["fallback_used"] = True
        fallback_letter = (
            "⚠️ Не удалось безопасно сгенерировать сопроводительное письмо.\n\n"
            "Пожалуйста, напишите его вручную на основе вашего резюме."
        )
        return fallback_letter, metadata
