# main.py
"""
ResumePro AI — VK Bot entry point.
Conversation flow:
  1. Any message / /start / /help → greeting
  2. User sends PDF or DOCX attachment → store resume text, ask for HH link
  3. User sends hh.ru/vacancy/... link → adapt stored resume, return result
  4. /demo → show example output
Версия: 5.1
"""

import os
import re
import logging
import tempfile
import requests

from flask import Flask, request, jsonify
from vk_api import VkApi
from vk_api.exceptions import ApiError as VkApiError
from gigachat import GigaChat

from services.resume_generator import AntiHallucinationGenerator
from utils.utils import extract_text_from_file, parse_hh_vacancy, clean_markdown
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
vk = vk_session.get_api()

if not Config.VK_GROUP_ID:
    logger.error("❌ VK_GROUP_ID is not set!")
    raise ValueError("VK_GROUP_ID is required")

logger.info("✅ VK Group ID: %s", Config.VK_GROUP_ID)

# ── GigaChat + Generator ──────────────────────────────────────────────────────
logger.info("🔄 Connecting to GigaChat...")
gigachat = GigaChat(credentials=Config.GIGACHAT_API_KEY, verify_ssl_certs=False)
generator = AntiHallucinationGenerator(gigachat, max_retries=Config.MAX_RETRIES)
logger.info("✅ Bot ready. Group: %s", Config.VK_GROUP_ID)

# ── In-memory session store ───────────────────────────────────────────────────
# { user_id (int): { 'resume_text': str, 'state': 'waiting_vacancy' | None } }
# Sufficient for single-process Replit deployment.
# For multi-process, replace with Redis.
USER_SESSIONS: dict = {}

# ── Static messages ───────────────────────────────────────────────────────────
GREETING = (
    "👋 Привет! Я бот Резюме.Про 🎯\n"
    "Я помогу адаптировать твоё резюме под вакансию за 30 секунд с помощью ИИ.\n\n"
    "📋 Как работать:\n"
    "1. Отправь мне текст своего резюме (файл PDF или DOCX)\n"
    "2. Добавь ссылку на вакансию (hh.ru)\n"
    "3. Получи адаптированную версию + Match Score\n\n"
    "💡 Команды:\n"
    "• /help — справка\n"
    "• /demo — показать пример\n"
    "• /start — начать адаптацию\n\n"
    "Проект Школы 21 • Готов помочь! 🚀"
)

HELP = (
    "📖 Справка ResumePro AI\n\n"
    "Что умею:\n"
    "• Адаптирую твоё резюме под конкретную вакансию\n"
    "• Выделяю ключевые слова из вакансии\n"
    "• Защита от ИИ-галлюцинаций — не добавляю несуществующий опыт\n\n"
    "Как пользоваться:\n"
    "1. Отправь файл резюме (PDF или DOCX)\n"
    "2. После подтверждения пришли ссылку на вакансию hh.ru\n\n"
    "⚠️ Бот работает только с вакансиями с сайта hh.ru"
)

DEMO_RESUME = (
    "📄 Пример: исходное резюме\n"
    "──────────────────────────\n"
    "Иван Иванов, Python-разработчик\n"
    "Опыт: 2020–2023 Яндекс — Backend Developer\n"
    "Навыки: Python, Django, PostgreSQL, Redis, Git\n\n"
    "✅ После адаптации под вакансию «Senior Python Developer»:\n"
    "──────────────────────────\n"
    "Иван Иванов — Senior Python Developer\n"
    "3 года опыта backend-разработки в высоконагруженных системах (Яндекс)\n"
    "Стек: Python · Django · PostgreSQL · Redis · Git\n"
    "Ключевые достижения: оптимизация запросов БД, поддержка REST API"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def send_message(user_id: int, text: str) -> bool:
    """Send a VK message, truncating at 4096 chars. Returns True on success."""
    try:
        if len(text) > 4096:
            text = text[:4093] + "..."
        vk.messages.send(user_id=user_id, message=text, random_id=0)
        return True
    except VkApiError as e:
        if e.code == 901:
            logger.warning("⚠️ Cannot message user %s: permission denied", user_id)
        else:
            logger.error("❌ VK error sending to %s: %s", user_id, e)
        return False
    except Exception as e:
        logger.exception("❌ Unexpected error sending to %s: %s", user_id, e)
        return False


def download_vk_doc(url: str, ext: str) -> str:
    """Download a VK document to a temp file. Returns path or empty string."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        suffix = f".{ext.lower()}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(resp.content)
            return f.name
    except Exception as e:
        logger.error("❌ Failed to download doc: %s", e)
        return ""


def extract_hh_url(text: str) -> str:
    """Extract the first hh.ru vacancy URL from a message text."""
    match = re.search(r"https?://[^\s]*hh\.ru/vacancy/\d+[^\s]*", text)
    if match:
        return match.group(0)
    match = re.search(r"hh\.ru/vacancy/\d+", text)
    return match.group(0) if match else ""


def get_session(user_id: int) -> dict:
    if user_id not in USER_SESSIONS:
        USER_SESSIONS[user_id] = {"resume_text": None, "state": None}
    return USER_SESSIONS[user_id]


def clear_session(user_id: int) -> None:
    USER_SESSIONS.pop(user_id, None)


# ── Core conversation handler ─────────────────────────────────────────────────


def handle_message(user_id: int, text: str, attachments: list) -> None:
    session = get_session(user_id)
    text_lower = text.lower().strip()

    # ── Commands ──────────────────────────────────────────────────────────────
    if text_lower in ("/start", "start", "начать", "привет", "hi", "hello", ""):
        clear_session(user_id)
        send_message(user_id, GREETING)
        return

    if text_lower in ("/help", "help", "помощь"):
        send_message(user_id, HELP)
        return

    if text_lower in ("/demo", "demo", "пример"):
        send_message(user_id, DEMO_RESUME)
        return

    # ── File attachment (PDF / DOCX resume) ───────────────────────────────────
    doc_attachment = next((a for a in attachments if a.get("type") == "doc"), None)

    if doc_attachment:
        doc = doc_attachment["doc"]
        ext = doc.get("ext", "").lower()

        if ext not in ("pdf", "docx", "doc"):
            send_message(
                user_id,
                "❌ Неподдерживаемый формат файла.\n"
                "Пожалуйста, отправь резюме в формате PDF или DOCX.",
            )
            return

        send_message(user_id, "⏳ Читаю резюме...")

        file_path = download_vk_doc(doc["url"], ext)
        if not file_path:
            send_message(user_id, "❌ Не удалось загрузить файл. Попробуй ещё раз.")
            return

        resume_text = extract_text_from_file(file_path, ext)

        try:
            os.unlink(file_path)
        except Exception:
            pass

        if not resume_text or len(resume_text) < 50:
            send_message(
                user_id,
                "❌ Не удалось извлечь текст из файла.\n"
                "Убедись, что PDF не отсканирован (нужен текстовый PDF), "
                "или попробуй DOCX.",
            )
            return

        session["resume_text"] = resume_text
        session["state"] = "waiting_vacancy"

        logger.info(
            "📄 Resume loaded for user %s (%d chars)", user_id, len(resume_text)
        )
        send_message(
            user_id,
            "✅ Резюме получено!\n\n"
            "Теперь отправь ссылку на вакансию с hh.ru\n"
            "Пример: https://hh.ru/vacancy/12345678",
        )
        return

    # ── HH.ru vacancy link ────────────────────────────────────────────────────
    hh_url = extract_hh_url(text)
    if hh_url:
        if not session.get("resume_text"):
            send_message(
                user_id,
                "📎 Сначала отправь файл резюме (PDF или DOCX), "
                "а потом я адаптирую его под эту вакансию.",
            )
            return

        send_message(
            user_id,
            "⏳ Анализирую вакансию и адаптирую резюме...\nЭто займёт около 30 секунд.",
        )

        vacancy_text = parse_hh_vacancy(hh_url)
        if vacancy_text.startswith("Error:") or vacancy_text == "Invalid HH.ru URL":
            send_message(
                user_id,
                f"❌ Не удалось получить вакансию.\n{vacancy_text}\n\n"
                "Проверь ссылку — она должна быть вида hh.ru/vacancy/12345678",
            )
            return

        resume_text = session["resume_text"]
        try:
            adapted, metadata = generator.generate_safe_resume(
                resume_text, vacancy_text
            )
        except Exception as e:
            logger.exception("Generation error for user %s: %s", user_id, e)
            send_message(user_id, "❌ Ошибка при генерации. Попробуй ещё раз позже.")
            return

        adapted_clean = clean_markdown(adapted)
        conf = metadata.get("validation", {}).get("confidence", 1.0) * 100

        if metadata.get("fallback_used"):
            header = (
                "⚠️ Не удалось безопасно адаптировать резюме.\n"
                "Возвращаем оригинал без изменений.\n\n"
            )
        else:
            header = f"✅ Резюме адаптировано! Match Score: {conf:.0f}%\n\n"

        response = header + adapted_clean

        # Append soft info-level notes if any
        info_issues = [i for i in metadata.get("issues", []) if i.startswith("ℹ️")]
        if info_issues:
            response += "\n\n" + "\n".join(info_issues)

        send_message(user_id, response)

        # Reset session so user can immediately start another adaptation
        clear_session(user_id)
        send_message(
            user_id,
            "Хочешь адаптировать под другую вакансию? "
            "Просто отправь новый файл резюме 📎",
        )

        logger.info(
            "✅ Done for user %s | confidence=%.0f%% | fallback=%s",
            user_id,
            conf,
            metadata.get("fallback_used"),
        )
        return

    # ── Fallthrough: unrecognised input ───────────────────────────────────────
    if session.get("state") == "waiting_vacancy":
        send_message(
            user_id,
            "Жду ссылку на вакансию с hh.ru 🔗\n"
            "Пример: https://hh.ru/vacancy/12345678\n\n"
            "Или отправь новый файл резюме, чтобы начать заново.",
        )
    else:
        send_message(user_id, GREETING)


# ── Flask routes ──────────────────────────────────────────────────────────────


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    if data.get("type") == "confirmation":
        token = getattr(Config, "VK_CONFIRMATION_TOKEN", None) or os.getenv(
            "VK_CONFIRMATION_TOKEN", "ok"
        )
        return str(token)

    if data.get("type") != "message_new":
        return jsonify({"status": "ok"})

    msg = data.get("object", {}).get("message", {})
    user_id = msg.get("from_id")
    text = (msg.get("text") or "").strip()
    attachments = msg.get("attachments") or []

    if not user_id or user_id < 0:
        return jsonify({"status": "ok"})

    logger.info("📨 User %s: '%.60s' | %d attachments", user_id, text, len(attachments))

    try:
        handle_message(user_id, text, attachments)
    except Exception as e:
        logger.exception("Unhandled error for user %s: %s", user_id, e)
        send_message(user_id, "❌ Произошла непредвиденная ошибка. Попробуй позже.")

    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "version": "5.1.0",
            "vk_group_id": Config.VK_GROUP_ID,
            "gigachat_connected": bool(Config.GIGACHAT_API_KEY),
            "active_sessions": len(USER_SESSIONS),
        }
    )


@app.route("/validate", methods=["POST"])
def validate_endpoint():
    """Debug: POST {original, adapted} → validation result JSON."""
    body = request.json or {}
    original = body.get("original", "")
    adapted = body.get("adapted", "")
    if not original or not adapted:
        return jsonify({"error": "original and adapted fields are required"}), 400

    from utils.validation import validate_resume_facts

    result = validate_resume_facts(original, adapted)
    result["summary"] = get_validation_summary(result)
    for key in ("original_entities", "adapted_entities"):
        result[key] = {
            k: sorted(v) if isinstance(v, set) else v
            for k, v in result.get(key, {}).items()
        }
    return jsonify(result)


if __name__ == "__main__":
    logger.info("🚀 Starting ResumePro AI bot v5.1...")
    logger.info("📋 Config: VK_GROUP_ID=%s, PORT=%s", Config.VK_GROUP_ID, Config.PORT)
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
