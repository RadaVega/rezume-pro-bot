# main.py
"""
Точка входа бота ResumePro AI с защитой от галлюцинаций.
Версия: 5.0
"""

import os
import logging
from flask import Flask, request, jsonify
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.exceptions import ApiError as VkApiError
from gigachat import GigaChat

from services.resume_generator import AntiHallucinationGenerator
from utils.validation import get_validation_summary
from config.settings import Config

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── VK ────────────────────────────────────────────────────────────────────────
logger.info("🔄 Connecting to VK...")
vk_session = VkApi(token=os.getenv("VK_TOKEN"))

if not Config.VK_GROUP_ID:
    logger.error("❌ VK_GROUP_ID is not set! Check Replit Secrets.")
    raise ValueError("VK_GROUP_ID is required")

logger.info(f"✅ VK Group ID: {Config.VK_GROUP_ID}")
longpoll = VkBotLongPoll(vk_session, Config.VK_GROUP_ID)

# ── GigaChat + Generator ──────────────────────────────────────────────────────
logger.info("🔄 Connecting to GigaChat...")
gigachat = GigaChat(credentials=Config.GIGACHAT_API_KEY, verify_ssl_certs=False)
generator = AntiHallucinationGenerator(gigachat, max_retries=Config.MAX_RETRIES)
logger.info("✅ Bot started! Group: %s", Config.VK_GROUP_ID)

# ── Helpers ───────────────────────────────────────────────────────────────────


def send_vk_message(user_id: int, text: str) -> bool:
    """
    Send a message to a VK user, truncating if too long.
    Returns True if sent successfully, False if failed.
    """
    try:
        MAX_LEN = 4096
        if len(text) > MAX_LEN:
            text = text[: MAX_LEN - 3] + "..."

        vk_session.method(
            "messages.send",
            {"user_id": user_id, "message": text, "random_id": 0},
        )
        return True
    except VkApiError as e:
        # Handle VK API errors gracefully
        if e.code == 901:  # Can't send messages for users without permission
            logger.warning(
                f"⚠️ Cannot message user {user_id}: permission denied (VK error 901)"
            )
            return False
        logger.error(f"❌ VK API error sending to user {user_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"❌ Unexpected error sending to user {user_id}: {e}")
        return False


def build_resume_response(result: str, metadata: dict) -> str:
    """Format the resume generation response for the user."""
    if metadata.get("fallback_used"):
        return (
            "⚠️ Не удалось безопасно адаптировать резюме после нескольких попыток.\n"
            "Возвращаем оригинал — ваши данные не изменены.\n\n" + result
        )

    if metadata.get("validation_passed"):
        conf = metadata.get("validation", {}).get("confidence", 1.0) * 100
        return f"✅ Резюме адаптировано (уверенность: {conf:.0f}%)\n\n{result}"

    # Passed but with only INFO-level warnings
    warnings = "; ".join(metadata.get("issues", []))
    return f"✅ Резюме адаптировано с замечаниями:\n{warnings}\n\n{result}"


def build_cover_letter_response(letter: str, metadata: dict) -> str:
    """Format the cover letter response for the user."""
    if metadata.get("fallback_used"):
        return letter  # Already contains the fallback message

    conf = metadata.get("validation", {}).get("confidence", 1.0) * 100
    return f"📝 Сопроводительное письмо (уверенность: {conf:.0f}%):\n\n{letter}"


# ── Routes ────────────────────────────────────────────────────────────────────


@app.route("/webhook", methods=["POST"])
def webhook():
    """VK Webhook handler."""
    data = request.json or {}

    # ── Confirmation handshake ────────────────────────────────────────────────
    if data.get("type") == "confirmation":
        # Return confirmation token from config, or fallback to "ok"
        token = getattr(Config, "VK_CONFIRMATION_TOKEN", None) or os.getenv(
            "VK_CONFIRMATION_TOKEN", "ok"
        )
        return str(token)

    if data.get("type") != "message_new":
        return jsonify({"status": "ok"})

    msg = data.get("object", {}).get("message", {})
    user_id = msg.get("from_id")
    text = (msg.get("text") or "").strip()

    if not user_id or not text:
        return jsonify({"status": "ok"})

    logger.info("📨 Message from user %s: %.80s", user_id, text)

    try:
        # ── Resume adaptation ─────────────────────────────────────────────────
        if "hh.ru/vacancy" in text:
            from utils.utils import parse_hh_vacancy, extract_text_from_file

            vacancy_text = parse_hh_vacancy(text)

            # In production: extract resume from user's previously uploaded file.
            # Stub for demo:
            resume_text = (
                "Иван Иванов, разработчик.\n"
                "Опыт: 2020–2023 Яндекс — Python-разработчик.\n"
                "Навыки: Python, Django, PostgreSQL, Git, Docker."
            )

            result, metadata = generator.generate_safe_resume(resume_text, vacancy_text)
            response = build_resume_response(result, metadata)

        # ── Cover letter ──────────────────────────────────────────────────────
        elif text.lower().startswith("/letter"):
            # Usage: /letter <hh.ru/vacancy/...>
            url = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
            if not url:
                response = (
                    "❌ Укажите ссылку на вакансию: /letter https://hh.ru/vacancy/..."
                )
            else:
                from utils.utils import parse_hh_vacancy

                vacancy_text = parse_hh_vacancy(url)
                resume_text = "Иван Иванов ..."  # replace with real resume

                # generate_cover_letter returns (text, metadata)
                letter, metadata = generator.generate_cover_letter(
                    resume_text, vacancy_text
                )
                response = build_cover_letter_response(letter, metadata)

        # ── Help ──────────────────────────────────────────────────────────────
        else:
            response = (
                "👋 ResumePro AI\n\n"
                "Команды:\n"
                "• Пришлите ссылку hh.ru/vacancy/... — адаптируем резюме\n"
                "• /letter <ссылка> — сопроводительное письмо\n"
                "• /health — статус бота"
            )

        # Send response, but don't fail if VK permission error
        if not send_vk_message(user_id, response):
            logger.warning(f"⚠️ Failed to send response to user {user_id}")

        logger.info("✅ Response sent to user %s", user_id)

    except Exception as e:
        logger.exception("Error processing message from user %s: %s", user_id, e)
        # Try to send error message, but don't fail the webhook if this also fails
        send_vk_message(user_id, "❌ Произошла ошибка. Попробуйте позже.")

    # Always return 200 to VK — they expect this
    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    """Health check for UptimeRobot."""
    return jsonify(
        {
            "status": "healthy",
            "version": "5.0.0",
            "vk_group_id": Config.VK_GROUP_ID,
            "gigachat_connected": bool(Config.GIGACHAT_API_KEY),
        }
    )


@app.route("/validate", methods=["POST"])
def validate_endpoint():
    """
    Debug endpoint: validate an adapted resume against the original.
    Body: { "original": "...", "adapted": "..." }
    """
    body = request.json or {}
    original = body.get("original", "")
    adapted = body.get("adapted", "")

    if not original or not adapted:
        return jsonify({"error": "original and adapted fields are required"}), 400

    from utils.validation import validate_resume_facts

    result = validate_resume_facts(original, adapted)
    result["summary"] = get_validation_summary(result)

    # Convert sets to lists for JSON serialisation
    result["original_entities"] = {
        k: list(v) if hasattr(v, "__iter__") and not isinstance(v, str) else v
        for k, v in result.get("original_entities", {}).items()
    }
    result["adapted_entities"] = {
        k: list(v) if hasattr(v, "__iter__") and not isinstance(v, str) else v
        for k, v in result.get("adapted_entities", {}).items()
    }

    return jsonify(result)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("🚀 Starting ResumePro AI bot v5.0...")
    logger.info("📋 Config: VK_GROUP_ID=%s, PORT=%s", Config.VK_GROUP_ID, Config.PORT)
    app.run(host="0.0.0.0", port=Config.PORT)
