# main.py
"""
ResumePro AI — VK Bot v5.3
Conversation flow:
  /start | привет | empty  → greeting (ALWAYS, no dedup)
  PDF/DOCX attachment       → parse resume, save to session, ask for HH link
  hh.ru/vacancy/... link    → adapt stored resume, show result
                              (resume stays in session — user can send another link)
  /reset                    → clear session, start over
  /demo                     → example output
  /help                     → instructions
"""


import os
import re
import time
import random
import logging
import tempfile
import threading
from collections import OrderedDict

import requests as http_requests
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

if not Config.VK_GROUP_ID:
    logger.error("❌ VK_GROUP_ID is not set!")
    raise ValueError("VK_GROUP_ID is required")
logger.info("✅ VK Group ID: %s", Config.VK_GROUP_ID)

# ── GigaChat ──────────────────────────────────────────────────────────────────
logger.info("🔄 Connecting to GigaChat...")
gigachat = GigaChat(credentials=Config.GIGACHAT_API_KEY, verify_ssl_certs=False)
generator = AntiHallucinationGenerator(gigachat, max_retries=Config.MAX_RETRIES)
logger.info("✅ Bot ready. Group: %s", Config.VK_GROUP_ID)

# ── Message deduplication (by VK message_id only) ─────────────────────────────
# Prevents double-delivery when VK retries a webhook call.
# Does NOT deduplicate commands — /start always works.
_seen_msg_ids: OrderedDict = OrderedDict()
_MSG_TTL = 60  # seconds — VK retries arrive within a few seconds
_MSG_CACHE_MAX = 2000


def _is_duplicate_message(message_id: int) -> bool:
    """Return True if this VK message_id was already processed."""
    if not message_id:
        return False
    now = time.time()
    # Evict expired entries
    while _seen_msg_ids and next(iter(_seen_msg_ids.values())) < now - _MSG_TTL:
        _seen_msg_ids.popitem(last=False)
    if message_id in _seen_msg_ids:
        return True
    _seen_msg_ids[message_id] = now
    if len(_seen_msg_ids) > _MSG_CACHE_MAX:
        _seen_msg_ids.popitem(last=False)
    return False


# ── User session store ────────────────────────────────────────────────────────
# { user_id: { resume_text, resume_filename, state, updated_at } }
# state: "waiting_resume" | "waiting_vacancy" | "processing"
_sessions: dict = {}
_SESSION_TTL = 3600  # 1 hour


def _session(user_id: int) -> dict:
    now = time.time()
    s = _sessions.get(user_id)
    if s and now - s.get("updated_at", 0) < _SESSION_TTL:
        return s
    # New or expired session
    _sessions[user_id] = {
        "resume_text": None,
        "resume_filename": None,
        "state": "waiting_resume",
        "updated_at": now,
    }
    return _sessions[user_id]


def _touch(user_id: int) -> None:
    if user_id in _sessions:
        _sessions[user_id]["updated_at"] = time.time()


def _clear_session(user_id: int) -> None:
    _sessions.pop(user_id, None)


def _session_cleanup() -> None:
    while True:
        time.sleep(600)
        now = time.time()
        expired = [
            uid
            for uid, s in list(_sessions.items())
            if now - s.get("updated_at", 0) > _SESSION_TTL
        ]
        for uid in expired:
            _sessions.pop(uid, None)
        if expired:
            logger.debug("🧹 Cleaned %d expired sessions", len(expired))


# ── Static messages ───────────────────────────────────────────────────────────
GREETING = (
    "👋 Привет! Я бот Резюме.Про 🎯\n"
    "Я помогу адаптировать твоё резюме под вакансию за 30 секунд с помощью ИИ.\n\n"
    "📋 Как работать:\n"
    "1. Отправь мне файл резюме (PDF или DOCX)\n"
    "2. Пришли ссылку на вакансию с hh.ru\n"
    "3. Получи адаптированную версию + Match Score\n\n"
    "💡 Команды:\n"
    "• /help  — справка\n"
    "• /demo  — показать пример\n"
    "• /reset — начать заново\n\n"
    "Проект Школы 21 • Готов помочь! 🚀"
)

HELP = (
    "📖 Справка ResumePro AI\n\n"
    "Что умею:\n"
    "• Адаптирую резюме под конкретную вакансию\n"
    "• Выделяю ключевые слова из вакансии\n"
    "• Защита от ИИ-галлюцинаций — не добавляю несуществующий опыт\n"
    "• Сохраняю резюме в сессии — одно резюме для нескольких вакансий\n\n"
    "Как пользоваться:\n"
    "1. Отправь файл резюме (PDF или DOCX)\n"
    "2. После подтверждения пришли ссылку hh.ru/vacancy/...\n"
    "3. Получи результат. Резюме останется — пришли новую ссылку!\n\n"
    "⚠️ Поддерживаются только вакансии с hh.ru"
)

DEMO = (
    "📄 Пример — исходное резюме:\n"
    "────────────────────────\n"
    "Иван Иванов, Python-разработчик\n"
    "Опыт: 2020–2023 Яндекс — Backend Developer\n"
    "Навыки: Python, Django, PostgreSQL, Redis, Git\n\n"
    "✅ После адаптации под «Senior Python Developer»:\n"
    "────────────────────────\n"
    "Иван Иванов — Senior Python Developer\n"
    "3 года backend-разработки в высоконагруженных системах (Яндекс, 2020–2023)\n"
    "Стек: Python · Django · PostgreSQL · Redis · Git\n"
    "Достижения: оптимизация запросов БД, REST API, CI/CD на Docker\n\n"
    "📊 Match Score: 91%"
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def send(user_id: int, text: str) -> bool:
    """
    Send a VK message using vk_session.method() — the form proven to work.
    Uses a unique random_id per call (required by VK to avoid silent drops).
    Truncates at 4096 chars. Returns True on success.
    """
    try:
        if len(text) > 4096:
            text = text[:4093] + "..."
        vk_session.method(
            "messages.send",
            {
                "user_id": user_id,
                "message": text,
                "random_id": random.randint(1, 2_147_483_647),
            },
        )
        logger.info("✅ Sent to user %s (%d chars)", user_id, len(text))
        return True
    except VkApiError as e:
        if e.code == 901:
            logger.warning("⚠️ User %s blocked messages (VK 901)", user_id)
        else:
            logger.error("❌ VK API error → user %s | code=%s | %s", user_id, e.code, e)
        return False
    except Exception as e:
        logger.exception("❌ send() unexpected error → user %s: %s", user_id, e)
        return False


def download_file(url: str, ext: str) -> str:
    """Download a VK document URL to a temp file. Returns path or ''."""
    try:
        resp = http_requests.get(url, timeout=30)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext.lower()}") as f:
            f.write(resp.content)
            return f.name
    except Exception as e:
        logger.error("❌ File download error: %s", e)
        return ""


def extract_hh_url(text: str) -> str:
    """Return the first hh.ru vacancy URL found in text, or ''."""
    m = re.search(r"https?://[^\s]*hh\.ru/vacancy/\d+[^\s]*", text)
    if m:
        return m.group(0)
    m = re.search(r"hh\.ru/vacancy/\d+", text)
    return m.group(0) if m else ""


def ats_score(confidence: float) -> int:
    """Convert validator confidence (0.0–1.0) to a 0–100 ATS score."""
    return round(confidence * 100)


# ── Core conversation handler ─────────────────────────────────────────────────


def handle(user_id: int, text: str, attachments: list) -> None:
    """Dispatch incoming message to the right handler."""
    s = _session(user_id)
    cmd = text.lower().strip()

    # ── Always-respond commands ───────────────────────────────────────────────
    if cmd in ("/start", "start", "начать", "привет", "hi", "hello", ""):
        _clear_session(user_id)
        send(user_id, GREETING)
        return

    if cmd in ("/help", "help", "помощь"):
        send(user_id, HELP)
        return

    if cmd in ("/demo", "demo", "пример"):
        send(user_id, DEMO)
        return

    if cmd in ("/reset", "reset", "сброс"):
        _clear_session(user_id)
        send(user_id, "🔄 Сессия сброшена.\n\nОтправь новый файл резюме или /start.")
        return

    if cmd == "/health":
        send(user_id, f"✅ Бот работает! Версия 5.3\nАктивных сессий: {len(_sessions)}")
        return

    # ── File attachment: PDF / DOCX ───────────────────────────────────────────
    doc = next((a for a in attachments if a.get("type") == "doc"), None)
    if doc:
        info = doc["doc"]
        ext = info.get("ext", "").lower()
        fname = info.get("title", info.get("filename", "файл"))

        if ext not in ("pdf", "docx", "doc"):
            send(
                user_id,
                "❌ Неподдерживаемый формат.\nОтправь резюме в формате PDF или DOCX.",
            )
            return

        send(user_id, f"⏳ Читаю файл {fname}...")

        path = download_file(info["url"], ext)
        if not path:
            send(user_id, "❌ Не удалось загрузить файл. Попробуй ещё раз.")
            return

        resume_text = extract_text_from_file(path, ext)
        try:
            os.unlink(path)
        except Exception:
            pass

        if not resume_text or len(resume_text) < 50:
            send(
                user_id,
                "❌ Не удалось извлечь текст.\n"
                "Убедись, что PDF не отсканирован, или используй DOCX.",
            )
            return

        s["resume_text"] = resume_text
        s["resume_filename"] = fname
        s["state"] = "waiting_vacancy"
        _touch(user_id)

        logger.info(
            "📄 Resume loaded for user %s: %s (%d chars)",
            user_id,
            fname,
            len(resume_text),
        )
        send(
            user_id,
            f"✅ Резюме получено: {fname}\n\n"
            "Теперь пришли ссылку на вакансию с hh.ru\n"
            "Пример: https://hh.ru/vacancy/12345678\n\n"
            "💡 После адаптации можно прислать другую ссылку — "
            "резюме останется в памяти!",
        )
        return

    # ── HH.ru vacancy link ────────────────────────────────────────────────────
    hh_url = extract_hh_url(text)
    if hh_url:
        if not s.get("resume_text"):
            send(user_id, "📎 Сначала отправь файл резюме (PDF или DOCX).")
            return

        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return

        send(
            user_id,
            "⏳ Анализирую вакансию и адаптирую резюме...\nЭто займёт около 30 секунд.",
        )

        s["state"] = "processing"
        _touch(user_id)

        # Run in background so webhook returns 200 immediately
        def _process():
            try:
                vacancy_text = parse_hh_vacancy(hh_url)
                if (
                    vacancy_text.startswith("Error:")
                    or vacancy_text == "Invalid HH.ru URL"
                ):
                    send(
                        user_id,
                        f"❌ Не удалось получить вакансию.\n{vacancy_text}\n\n"
                        "Проверь ссылку — она должна быть вида hh.ru/vacancy/12345678",
                    )
                    s["state"] = "waiting_vacancy"
                    return

                adapted, metadata = generator.generate_safe_resume(
                    s["resume_text"], vacancy_text
                )
                adapted_clean = clean_markdown(adapted)
                conf = metadata.get("validation", {}).get("confidence", 1.0)
                score = ats_score(conf)

                if metadata.get("fallback_used"):
                    header = (
                        "⚠️ Не удалось безопасно адаптировать резюме.\n"
                        "Возвращаем оригинал без изменений.\n\n"
                    )
                else:
                    header = f"✅ Резюме адаптировано!\n📊 Match Score: {score}/100\n\n"

                body = header + adapted_clean

                # Append soft info notes if any
                info_notes = [
                    i for i in metadata.get("issues", []) if i.startswith("ℹ️")
                ]
                if info_notes:
                    body += "\n\n" + "\n".join(info_notes)

                send(user_id, body)

                # Keep resume, reset state — ready for the next vacancy link
                s["state"] = "waiting_vacancy"
                _touch(user_id)

                send(
                    user_id,
                    "💡 Хочешь проверить другую вакансию? "
                    "Просто пришли новую ссылку — резюме сохранено 📎\n"
                    "Для нового резюме отправь /reset",
                )

                logger.info(
                    "✅ Done for user %s | score=%d | fallback=%s",
                    user_id,
                    score,
                    metadata.get("fallback_used"),
                )

            except Exception as e:
                logger.exception("❌ _process() error for user %s: %s", user_id, e)
                send(user_id, "❌ Ошибка при генерации. Попробуй ещё раз.")
                s["state"] = "waiting_vacancy"

        threading.Thread(target=_process, daemon=True).start()
        return

    # ── Fallthrough: unrecognised input ───────────────────────────────────────
    state = s.get("state", "waiting_resume")
    if state == "waiting_vacancy":
        send(
            user_id,
            "🔗 Жду ссылку на вакансию с hh.ru\n"
            "Пример: https://hh.ru/vacancy/12345678\n\n"
            "Или /reset чтобы загрузить другое резюме.",
        )
    elif state == "processing":
        send(user_id, "⏳ Ещё обрабатываю запрос, подожди немного...")
    else:
        send(user_id, GREETING)


# ── Flask routes ──────────────────────────────────────────────────────────────


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    # VK confirmation handshake
    if data.get("type") == "confirmation":
        token = getattr(Config, "VK_CONFIRMATION_TOKEN", None) or os.getenv(
            "VK_CONFIRMATION_TOKEN", "ok"
        )
        return str(token)

    if data.get("type") != "message_new":
        return jsonify({"status": "ok"})

    msg = data.get("object", {}).get("message", {})
    message_id = msg.get("id")
    user_id = msg.get("from_id")
    text = (msg.get("text") or "").strip()
    attachments = msg.get("attachments") or []

    # Ignore bot's own messages and invalid senders
    if not user_id or user_id < 0:
        return jsonify({"status": "ok"})

    # Deduplicate only by VK message_id (handles VK retry storms)
    if _is_duplicate_message(message_id):
        logger.debug(
            "⏭️ Duplicate msg_id=%s from user %s — skipped", message_id, user_id
        )
        return jsonify({"status": "ok"})

    logger.info(
        "📨 user=%s msg_id=%s text='%.60s' attachments=%d",
        user_id,
        message_id,
        text,
        len(attachments),
    )

    try:
        handle(user_id, text, attachments)
    except Exception as e:
        logger.exception("Unhandled error for user %s: %s", user_id, e)
        send(user_id, "❌ Непредвиденная ошибка. Попробуй позже.")

    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "version": "5.3.0",
            "vk_group_id": Config.VK_GROUP_ID,
            "gigachat_connected": bool(Config.GIGACHAT_API_KEY),
            "active_sessions": len(_sessions),
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
    logger.info("🚀 Starting ResumePro AI bot v5.3...")
    logger.info("📋 Config: VK_GROUP_ID=%s, PORT=%s", Config.VK_GROUP_ID, Config.PORT)
    threading.Thread(target=_session_cleanup, daemon=True).start()
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
