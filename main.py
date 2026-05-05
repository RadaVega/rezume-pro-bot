# main.py
"""
ResumePro AI — VK Bot v5.5
Conversation flow:
  /старт | привет | empty   → приветствие (всегда, без дедупликации)
  PDF/DOCX attachment       → разобрать резюме, сохранить в сессию, попросить ссылку HH
  hh.ru/vacancy/... link    → адаптировать резюме, показать результат
                              (резюме остаётся в сессии — можно отправить другую ссылку)
  /письмо                   → сопроводительное письмо под следующую ссылку HH
  /анализ                   → детальный разбор соответствия вакансии
  /оба                      → резюме + письмо одновременно
  /сброс                    → очистить сессию, начать заново
  /пример                   → пример вывода
  /помощь                   → инструкции
"""

# ── Package path: .pkgs/ is pre-installed during the Build stage ──────────────
# The [deployment] build command in .replit runs:
#   pip install --target .pkgs/ ...
# We add it to sys.path here so imports work regardless of PYTHONPATH env var.
import sys as _sys, os as _os
_PKGS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".pkgs")
if _os.path.isdir(_PKGS) and _PKGS not in _sys.path:
    _sys.path.insert(0, _PKGS)
# ─────────────────────────────────────────────────────────────────────────────

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
from utils.utils import (extract_text_from_file, parse_hh_vacancy,
                         scrape_any_vacancy, parse_linkedin_vacancy,
                         parse_superjob_vacancy, parse_rabota_vacancy,
                         is_linkedin_url, is_superjob_url, is_rabota_url,
                         clean_markdown)
from utils.validation import get_validation_summary, extract_entities, _scan_tech_skills, TECH_SKILLS
from utils.pdf_generator import text_to_pdf
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
_MSG_TTL = 60          # seconds — VK retries arrive within a few seconds
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
        expired = [uid for uid, s in list(_sessions.items())
                   if now - s.get("updated_at", 0) > _SESSION_TTL]
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
    "• /помощь   — справка\n"
    "• /пример   — показать пример\n"
    "• /анализ   — детальный анализ соответствия вакансии\n"
    "• /письмо   — написать сопроводительное письмо\n"
    "• /оба      — резюме + письмо одновременно\n"
    "• /статус   — показать текущее состояние сессии\n"
    "• /скачать  — повторно получить последние PDF-файлы\n"
    "• /сброс    — начать заново\n\n"
    "Проект Школы 21 • Готов помочь! 🚀"
)

HELP = (
    "📖 Справка ResumePro AI\n\n"
    "Что умею:\n"
    "• Адаптирую резюме под конкретную вакансию\n"
    "• Пишу сопроводительное письмо под вакансию (/письмо)\n"
    "• Выделяю ключевые слова из вакансии\n"
    "• Защита от ИИ-галлюцинаций — не добавляю несуществующий опыт\n"
    "• Сохраняю резюме в сессии — одно резюме для нескольких вакансий\n\n"
    "Как пользоваться:\n"
    "1. Отправь файл резюме (PDF или DOCX)\n"
    "2. После подтверждения пришли ссылку hh.ru/vacancy/...\n"
    "3. Получи результат. Резюме останется — пришли новую ссылку!\n\n"
    "Сопроводительное письмо:\n"
    "1. Загрузи резюме (если ещё не загружено)\n"
    "2. Отправь /письмо\n"
    "3. Пришли ссылку на вакансию с hh.ru\n\n"
    "Анализ соответствия (/анализ):\n"
    "1. Загрузи резюме\n"
    "2. Отправь /анализ\n"
    "3. Пришли ссылку — получишь разбор по навыкам:\n"
    "   ✅ что уже есть, ❌ чего не хватает, 💡 рекомендации\n\n"
    "Резюме + письмо сразу:\n"
    "1. Загрузи резюме\n"
    "2. Отправь /оба\n"
    "3. Пришли ссылку — получишь оба документа\n\n"
    "⚠️ Поддерживаются только вакансии с hh.ru\n\n"
    "Команды:\n"
    "• /статус   — показать текущее состояние сессии\n"
    "• /сброс    — начать заново\n"
    "• /старт    — вернуться в начало"
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


def send_document(user_id: int, file_path: str, title: str) -> bool:
    """
    Upload a file as a VK document and send it to the user as an attachment.
    Uses the low-level VK docs API so no extra wrapper is needed.
    """
    try:
        vk = vk_session.get_api()

        upload_info = vk.docs.getMessagesUploadServer(peer_id=user_id, type="doc")
        upload_url = upload_info["upload_url"]

        with open(file_path, "rb") as f:
            resp = http_requests.post(
                upload_url,
                files={"file": (title + ".pdf", f, "application/pdf")},
                timeout=60,
            )
        resp.raise_for_status()
        file_key = resp.json().get("file", "")
        if not file_key:
            raise ValueError(f"VK upload returned no file key: {resp.text}")

        saved = vk.docs.save(file=file_key, title=title)
        doc = saved.get("doc") or (saved[0] if isinstance(saved, list) else None)
        if not doc:
            raise ValueError(f"VK docs.save returned unexpected format: {saved}")

        attachment = f"doc{doc['owner_id']}_{doc['id']}"
        vk_session.method(
            "messages.send",
            {
                "user_id": user_id,
                "attachment": attachment,
                "message": "",
                "random_id": random.randint(1, 2_147_483_647),
            },
        )
        logger.info("✅ Document sent to user %s: '%s'", user_id, title)
        return True

    except VkApiError as e:
        logger.error("❌ VK API error in send_document → user %s | code=%s | %s", user_id, e.code, e)
        return False
    except Exception as e:
        logger.exception("❌ send_document() error → user %s: %s", user_id, e)
        return False


def _send_pdf_or_text(user_id: int, text: str, title: str, fallback_header: str) -> None:
    """
    Try to send text as a PDF attachment.
    Falls back to sending plain text if PDF generation or upload fails.
    """
    pdf_path = None
    try:
        pdf_path = text_to_pdf(text, title)
        ok = send_document(user_id, pdf_path, title)
        if not ok:
            raise RuntimeError("send_document returned False")
    except Exception as e:
        logger.warning("⚠️ PDF send failed (%s), falling back to text", e)
        send(user_id, fallback_header + text)
    finally:
        if pdf_path:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass


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
        return m.group(0).rstrip(".,;!?)")
    m = re.search(r"hh\.ru/vacancy/\d+", text)
    return ("https://" + m.group(0)) if m else ""


def extract_any_url(text: str) -> str:
    """Return the first http URL in text that is NOT an hh.ru vacancy URL, or ''."""
    for m in re.finditer(r"https?://[^\s]+", text):
        url = m.group(0).rstrip(".,;!?)")
        if "hh.ru/vacancy/" not in url:
            return url
    return ""


def ats_score(confidence: float) -> int:
    """Convert validator confidence (0.0–1.0) to a 0–100 ATS score."""
    return round(confidence * 100)


def build_score_report(resume_text: str, vacancy_text: str) -> str:
    """
    Сравнивает навыки из резюме с требованиями вакансии.
    Возвращает детальный отчёт на русском языке.
    """
    resume_entities = extract_entities(resume_text)
    resume_tech: set = resume_entities["skills"] & TECH_SKILLS

    vacancy_tech: set = _scan_tech_skills(vacancy_text)

    present = sorted(resume_tech & vacancy_tech)
    missing = sorted(vacancy_tech - resume_tech)
    extra   = sorted(resume_tech - vacancy_tech)

    total = len(vacancy_tech)
    if total == 0:
        score = 100 if resume_tech else 0
    else:
        score = round(len(present) / total * 100)

    lines = [
        f"📊 Анализ соответствия вакансии",
        f"─────────────────────────────",
        f"🎯 Match Score: {score}/100",
        "",
    ]

    if present:
        lines.append(f"✅ Есть в резюме и нужны вакансии ({len(present)}):")
        lines.append("   " + ",  ".join(present))
        lines.append("")

    if missing:
        lines.append(f"❌ Требуются вакансией, но отсутствуют ({len(missing)}):")
        lines.append("   " + ",  ".join(missing))
        lines.append("")

    if extra:
        lines.append(f"📌 Есть в резюме, но не упомянуты в вакансии ({len(extra)}):")
        lines.append("   " + ",  ".join(extra))
        lines.append("")

    lines.append("💡 Рекомендации:")
    if present:
        highlight = ", ".join(present[:5])
        lines.append(f"  → Выдели в резюме: {highlight}")
    if missing:
        if len(missing) <= 3:
            lines.append(f"  → Навыки для изучения: {', '.join(missing)}")
        else:
            top = ", ".join(missing[:3])
            lines.append(f"  → Приоритетные навыки для изучения: {top} и ещё {len(missing)-3}")
    if score >= 80:
        lines.append("  → Отличное соответствие! Смело отправляй резюме.")
    elif score >= 50:
        lines.append("  → Хорошая база. Адаптируй резюме командой /оба.")
    else:
        lines.append("  → Навыков пока немного. Попробуй адаптировать резюме через /оба.")

    if total == 0:
        lines.append("")
        lines.append("ℹ️ В вакансии не найдено технических навыков из базы.")
        lines.append("   Оценка основана на общем анализе текста.")

    return "\n".join(lines)


# ── Core conversation handler ─────────────────────────────────────────────────

def handle(user_id: int, text: str, attachments: list) -> None:
    """Dispatch incoming message to the right handler.
    Order: attachments → HH link → commands → fallthrough.
    Attachments MUST be first: user sends a file with empty text,
    which would otherwise match the '' greeting trigger.
    """
    s = _session(user_id)
    cmd = text.lower().strip()

    # ── 1. File attachment (PDF / DOCX) ───────────────────────────────────────
    doc = next((a for a in attachments if a.get("type") == "doc"), None)
    if doc:
        info = doc["doc"]
        ext = info.get("ext", "").lower()
        fname = info.get("title", info.get("filename", "файл"))

        if ext not in ("pdf", "docx", "doc"):
            send(user_id,
                 "❌ Неподдерживаемый формат.\n"
                 "Отправь резюме в формате PDF или DOCX.")
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
            send(user_id,
                 "❌ Не удалось извлечь текст.\n"
                 "Убедись, что PDF не отсканирован, или используй DOCX.")
            return

        s["resume_text"] = resume_text
        s["resume_filename"] = fname
        s["state"] = "waiting_vacancy"
        _touch(user_id)
        logger.info("📄 Resume loaded for user %s: %s (%d chars)", user_id, fname, len(resume_text))

        pending_url = s.pop("pending_vacancy_url", None)
        pending_text = s.pop("pending_vacancy_text", None)
        if pending_url:
            send(user_id,
                 f"✅ Резюме получено: {fname}\n\n"
                 f"🔗 Вижу ссылку на вакансию, которую ты прислал раньше:\n{pending_url}\n\n"
                 "Начинаю обработку...")
            handle(user_id, pending_url, [])
        elif pending_text:
            preview = pending_text[:120].replace("\n", " ")
            send(user_id,
                 f"✅ Резюме получено: {fname}\n\n"
                 f"📋 Вижу описание вакансии, которое ты прислал раньше:\n«{preview}…»\n\n"
                 "Начинаю обработку...")
            handle(user_id, pending_text, [])
        else:
            send(user_id,
                 f"✅ Резюме получено: {fname}\n\n"
                 "Теперь пришли ссылку на вакансию (hh.ru, любой другой сайт)\n"
                 "или просто вставь текст вакансии прямо в чат.\n\n"
                 "💡 После адаптации можно прислать другую вакансию — резюме останется в памяти!")
        return

    # ── 2. Vacancy source detection (hh.ru / any URL / pasted text) ───────────
    hh_url = extract_hh_url(text)
    other_url = ""
    pasted_vacancy = ""

    if not hh_url:
        link_att = next((a for a in attachments if a.get("type") == "link"), None)
        if link_att:
            link_url = link_att.get("link", {}).get("url", "")
            hh_url = extract_hh_url(link_url)
            if hh_url:
                logger.info("🔗 hh.ru URL from link attachment: %s", hh_url)
            elif link_url:
                other_url = link_url
                logger.info("🔗 Non-hh URL from link attachment: %s", other_url)

    if not hh_url and not other_url:
        other_url = extract_any_url(text)

    if (not hh_url and not other_url
            and len(text) > 300
            and not text.startswith("/")
            and s.get("resume_text")):
        pasted_vacancy = text

    vacancy_input = hh_url or other_url or pasted_vacancy

    if vacancy_input:
        if not s.get("resume_text"):
            if pasted_vacancy:
                s["pending_vacancy_text"] = pasted_vacancy
            else:
                s["pending_vacancy_url"] = hh_url or other_url
            _touch(user_id)
            send(user_id,
                 "📎 Сначала отправь файл резюме (PDF или DOCX).\n\n"
                 "💾 Запомнил описание/ссылку вакансии — пришли резюме и сразу начну!")
            return
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return

        current_state = s.get("state")
        coverletter_mode = current_state == "waiting_coverletter"
        both_mode = current_state == "waiting_both"
        score_mode = current_state == "waiting_score"

        if hh_url:
            vacancy_getter = lambda: parse_hh_vacancy(hh_url)
            vacancy_label = hh_url
            source_name = "hh.ru"
        elif other_url and is_linkedin_url(other_url):
            vacancy_getter = lambda: parse_linkedin_vacancy(other_url)
            vacancy_label = other_url
            source_name = "LinkedIn"
        elif other_url and is_superjob_url(other_url):
            vacancy_getter = lambda: parse_superjob_vacancy(other_url)
            vacancy_label = other_url
            source_name = "SuperJob"
        elif other_url and is_rabota_url(other_url):
            vacancy_getter = lambda: parse_rabota_vacancy(other_url)
            vacancy_label = other_url
            source_name = "Работа.ру"
        elif other_url:
            vacancy_getter = lambda: scrape_any_vacancy(other_url)
            vacancy_label = other_url
            source_name = "сайта вакансий"
        else:
            vacancy_getter = lambda: pasted_vacancy
            vacancy_label = "(текст вакансии)"
            source_name = "вставленного текста"

        if score_mode:
            send(user_id, "⏳ Анализирую соответствие резюме вакансии...\nОбычно это занимает несколько секунд.")
        elif coverletter_mode:
            send(user_id, "⏳ Составляю сопроводительное письмо...\nЭто займёт около 30 секунд.")
        elif both_mode:
            send(user_id, "⏳ Адаптирую резюме и пишу сопроводительное письмо одновременно...\nЭто займёт около 60 секунд.")
        else:
            send(user_id, f"⏳ Читаю вакансию ({source_name}) и адаптирую резюме...\nЭто займёт около 30 секунд.")

        s["state"] = "processing"
        s["last_vacancy_url"] = vacancy_label
        _touch(user_id)

        def _process():
            try:
                vacancy_text = vacancy_getter()
                if isinstance(vacancy_text, str) and vacancy_text.startswith("Error:"):
                    send(user_id,
                         f"❌ Не удалось получить данные вакансии.\n{vacancy_text}\n\n"
                         "Попробуй вставить текст вакансии прямо в чат — скопируй описание и пришли его сюда.")
                    if coverletter_mode:
                        s["state"] = "waiting_coverletter"
                    elif both_mode:
                        s["state"] = "waiting_both"
                    else:
                        s["state"] = "waiting_vacancy"
                    return

                if score_mode:
                    # ── Score / keyword breakdown ─────────────────────────────
                    report = build_score_report(s["resume_text"], vacancy_text)
                    send(user_id, report)
                    s["state"] = "waiting_vacancy"
                    _touch(user_id)
                    send(user_id,
                         "💡 Хочешь адаптировать резюме под эту вакансию?\n"
                         "• /оба — резюме + письмо сразу\n"
                         "• просто пришли ту же ссылку — получишь адаптированное резюме\n"
                         "• /сброс — загрузить другое резюме")
                    logger.info("✅ Score report done for user %s", user_id)

                elif coverletter_mode:
                    # ── Cover letter only ─────────────────────────────────────
                    letter, metadata = generator.generate_cover_letter(s["resume_text"], vacancy_text)
                    letter_clean = clean_markdown(letter)
                    if metadata.get("fallback_used"):
                        send(user_id, "⚠️ Не удалось сгенерировать письмо — возвращаем заготовку.\n\n" + letter_clean)
                    else:
                        send(user_id, "✉️ Генерирую PDF сопроводительного письма...")
                        fname = s.get("resume_filename", "резюме").rsplit(".", 1)[0]
                        letter_title = f"Сопроводительное письмо — {fname}"
                        _send_pdf_or_text(
                            user_id,
                            letter_clean,
                            title=letter_title,
                            fallback_header="✉️ Сопроводительное письмо:\n\n",
                        )
                        s["last_letter_pdf"] = {"text": letter_clean, "title": letter_title}
                    s["state"] = "waiting_vacancy"
                    _touch(user_id)
                    send(user_id,
                         "💡 Хочешь адаптировать резюме под эту же вакансию?\n"
                         "Просто пришли ту же ссылку ещё раз.\n"
                         "Для нового резюме отправь /сброс")
                    logger.info("✅ Cover letter done for user %s | fallback=%s",
                                user_id, metadata.get("fallback_used"))

                elif both_mode:
                    # ── Resume + cover letter in parallel ─────────────────────
                    resume_result: dict = {}
                    letter_result: dict = {}

                    def _gen_resume():
                        adapted, meta = generator.generate_safe_resume(s["resume_text"], vacancy_text)
                        resume_result["text"] = adapted
                        resume_result["meta"] = meta

                    def _gen_letter():
                        letter, meta = generator.generate_cover_letter(s["resume_text"], vacancy_text)
                        letter_result["text"] = letter
                        letter_result["meta"] = meta

                    t1 = threading.Thread(target=_gen_resume, daemon=True)
                    t2 = threading.Thread(target=_gen_letter, daemon=True)
                    t1.start()
                    t2.start()
                    t1.join()
                    t2.join()

                    # Send resume first
                    adapted_clean = clean_markdown(resume_result.get("text", ""))
                    r_meta = resume_result.get("meta", {})
                    conf = r_meta.get("validation", {}).get("confidence", 1.0)
                    score = ats_score(conf)
                    fname = s.get("resume_filename", "резюме").rsplit(".", 1)[0]
                    if r_meta.get("fallback_used"):
                        r_body = "⚠️ Не удалось адаптировать резюме. Возвращаем оригинал.\n\n" + adapted_clean
                        info_notes = [i for i in r_meta.get("issues", []) if i.startswith("ℹ️")]
                        if info_notes:
                            r_body += "\n\n" + "\n".join(info_notes)
                        send(user_id, r_body)
                    else:
                        send(user_id, f"✅ Генерирую PDF резюме (Match Score: {score}/100)...")
                        resume_pdf_text = adapted_clean
                        info_notes = [i for i in r_meta.get("issues", []) if i.startswith("ℹ️")]
                        if info_notes:
                            resume_pdf_text += "\n\n" + "\n".join(info_notes)
                        resume_title = f"Адаптированное резюме — {fname}"
                        _send_pdf_or_text(
                            user_id,
                            resume_pdf_text,
                            title=resume_title,
                            fallback_header=f"✅ Резюме адаптировано! Match Score: {score}/100\n\n",
                        )
                        s["last_resume_pdf"] = {"text": resume_pdf_text, "title": resume_title}

                    # Send cover letter second
                    letter_clean = clean_markdown(letter_result.get("text", ""))
                    l_meta = letter_result.get("meta", {})
                    if l_meta.get("fallback_used"):
                        send(user_id, "⚠️ Не удалось сгенерировать письмо — возвращаем заготовку.\n\n" + letter_clean)
                    else:
                        send(user_id, "✉️ Генерирую PDF сопроводительного письма...")
                        letter_title = f"Сопроводительное письмо — {fname}"
                        _send_pdf_or_text(
                            user_id,
                            letter_clean,
                            title=letter_title,
                            fallback_header="✉️ Сопроводительное письмо:\n\n",
                        )
                        s["last_letter_pdf"] = {"text": letter_clean, "title": letter_title}

                    s["state"] = "waiting_vacancy"
                    _touch(user_id)
                    send(user_id,
                         "💡 Резюме и письмо готовы! Пришли новую ссылку для другой вакансии.\n"
                         "Для нового резюме отправь /сброс")
                    logger.info("✅ Both done for user %s | resume_score=%d | letter_fallback=%s",
                                user_id, score, l_meta.get("fallback_used"))

                else:
                    # ── Resume only ───────────────────────────────────────────
                    adapted, metadata = generator.generate_safe_resume(s["resume_text"], vacancy_text)
                    adapted_clean = clean_markdown(adapted)
                    conf = metadata.get("validation", {}).get("confidence", 1.0)
                    score = ats_score(conf)
                    fname = s.get("resume_filename", "резюме").rsplit(".", 1)[0]

                    info_notes = [i for i in metadata.get("issues", []) if i.startswith("ℹ️")]

                    if metadata.get("fallback_used"):
                        body = "⚠️ Не удалось безопасно адаптировать резюме.\nВозвращаем оригинал без изменений.\n\n" + adapted_clean
                        if info_notes:
                            body += "\n\n" + "\n".join(info_notes)
                        send(user_id, body)
                    else:
                        send(user_id, f"✅ Генерирую PDF резюме (Match Score: {score}/100)...")
                        pdf_text = adapted_clean
                        if info_notes:
                            pdf_text += "\n\n" + "\n".join(info_notes)
                        resume_title = f"Адаптированное резюме — {fname}"
                        _send_pdf_or_text(
                            user_id,
                            pdf_text,
                            title=resume_title,
                            fallback_header=f"✅ Резюме адаптировано! Match Score: {score}/100\n\n",
                        )
                        s["last_resume_pdf"] = {"text": pdf_text, "title": resume_title}
                        s["last_letter_pdf"] = None

                    s["state"] = "waiting_vacancy"
                    _touch(user_id)
                    send(user_id,
                         "💡 Хочешь проверить другую вакансию? "
                         "Просто пришли новую ссылку — резюме сохранено 📎\n"
                         "Нужно сопроводительное письмо? Отправь /письмо\n"
                         "Нужно и то и другое? Отправь /оба\n"
                         "Для нового резюме отправь /сброс")
                    logger.info("✅ Done for user %s | score=%d | fallback=%s",
                                user_id, score, metadata.get("fallback_used"))

            except Exception as e:
                logger.exception("❌ _process() error for user %s: %s", user_id, e)
                send(user_id, "❌ Ошибка при генерации. Попробуй ещё раз.")
                if score_mode:
                    s["state"] = "waiting_score"
                elif coverletter_mode:
                    s["state"] = "waiting_coverletter"
                elif both_mode:
                    s["state"] = "waiting_both"
                else:
                    s["state"] = "waiting_vacancy"

        threading.Thread(target=_process, daemon=True).start()
        return

    # ── 3. Commands ───────────────────────────────────────────────────────────
    if cmd in ("/старт", "/start", "start", "начать", "привет", "hi", "hello", ""):
        _clear_session(user_id)
        send(user_id, GREETING)
        return

    if cmd in ("/помощь", "/help", "help", "помощь"):
        send(user_id, HELP)
        return

    if cmd in ("/пример", "/demo", "demo", "пример"):
        send(user_id, DEMO)
        return

    if cmd in ("/сброс", "/reset", "reset", "сброс"):
        _clear_session(user_id)
        send(user_id, "🔄 Сессия сброшена.\n\nОтправь новый файл резюме или напиши /старт.")
        return

    if cmd in ("/анализ", "/score", "score", "анализ", "скор"):
        if not s.get("resume_text"):
            send(user_id,
                 "📎 Сначала отправь файл резюме (PDF или DOCX), "
                 "а затем введи /анализ.")
            return
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
        s["state"] = "waiting_score"
        _touch(user_id)
        fname = s.get("resume_filename", "резюме")
        send(user_id,
             f"📊 Режим: анализ соответствия\n"
             f"Резюме: {fname}\n\n"
             "Пришли ссылку на вакансию с hh.ru — и я покажу:\n"
             "  ✅ какие навыки из резюме совпадают с вакансией\n"
             "  ❌ чего не хватает\n"
             "  💡 что стоит выделить или доучить\n\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Для отмены отправь /сброс")
        return

    if cmd in ("/оба", "/both", "both", "оба", "всё"):
        if not s.get("resume_text"):
            send(user_id,
                 "📎 Сначала отправь файл резюме (PDF или DOCX), "
                 "а затем введи /оба.")
            return
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
        s["state"] = "waiting_both"
        _touch(user_id)
        fname = s.get("resume_filename", "резюме")
        send(user_id,
             f"🚀 Режим: резюме + письмо\n"
             f"Резюме: {fname}\n\n"
             "Пришли ссылку на вакансию с hh.ru — и я сразу подготовлю\n"
             "адаптированное резюме и сопроводительное письмо.\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Для отмены отправь /сброс")
        return

    if cmd in ("/письмо", "/coverletter", "coverletter", "письмо", "сопроводительное"):
        if not s.get("resume_text"):
            send(user_id,
                 "📎 Сначала отправь файл резюме (PDF или DOCX), "
                 "а затем введи /письмо.")
            return
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
        s["state"] = "waiting_coverletter"
        _touch(user_id)
        fname = s.get("resume_filename", "резюме")
        send(user_id,
             f"✉️ Режим сопроводительного письма\n"
             f"Резюме: {fname}\n\n"
             "Пришли ссылку на вакансию с hh.ru — и я напишу письмо под неё.\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Для отмены отправь /сброс")
        return

    if cmd in ("/здоровье", "/health"):
        send(user_id, f"✅ Бот работает! Версия 5.5\nАктивных сессий: {len(_sessions)}")
        return

    if cmd in ("/статус", "/status", "статус"):
        state = s.get("state", "waiting_resume")
        resume_file = s.get("resume_filename")
        resume_len = len(s.get("resume_text") or "")
        last_url = s.get("last_vacancy_url")

        state_labels = {
            "waiting_resume":     "⏳ Ожидание резюме",
            "waiting_vacancy":    "🔗 Ожидание ссылки на вакансию",
            "waiting_score":      "📊 Режим анализа соответствия",
            "waiting_both":       "🚀 Режим: резюме + письмо",
            "waiting_coverletter": "✉️ Режим сопроводительного письма",
            "processing":         "⚙️ Обрабатываю запрос…",
        }
        state_label = state_labels.get(state, state)

        lines = ["📋 Состояние сессии:\n"]
        if resume_file:
            lines.append(f"📄 Резюме: {resume_file} ({resume_len} символов)")
        else:
            lines.append("📄 Резюме: не загружено")
        lines.append(f"🔄 Режим: {state_label}")
        if last_url:
            lines.append(f"🔗 Последняя вакансия: {last_url}")
        if state == "waiting_resume":
            lines.append("\nОтправь файл резюме (PDF или DOCX) чтобы начать.")
        elif state == "waiting_vacancy":
            lines.append("\nПришли ссылку с hh.ru — или выбери режим (/анализ, /письмо, /оба).")

        send(user_id, "\n".join(lines))
        return

    if cmd in ("/скачать", "/download", "скачать"):
        has_resume = bool(s.get("last_resume_pdf"))
        has_letter = bool(s.get("last_letter_pdf"))

        if not has_resume and not has_letter:
            send(user_id,
                 "📭 Нет сохранённых файлов для повторной отправки.\n\n"
                 "Пришли ссылку на вакансию с hh.ru — и я сгенерирую документы.\n"
                 "Для резюме + письма сразу используй /оба")
            return

        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю запрос, подожди немного.")
            return

        send(user_id, "📤 Повторно отправляю файлы...")

        if has_resume:
            r = s["last_resume_pdf"]
            _send_pdf_or_text(
                user_id,
                r["text"],
                title=r["title"],
                fallback_header="📄 Адаптированное резюме:\n\n",
            )

        if has_letter:
            l = s["last_letter_pdf"]
            _send_pdf_or_text(
                user_id,
                l["text"],
                title=l["title"],
                fallback_header="✉️ Сопроводительное письмо:\n\n",
            )

        parts = []
        if has_resume:
            parts.append("резюме")
        if has_letter:
            parts.append("письмо")
        send(user_id, f"✅ Готово! Отправил: {' и '.join(parts)}.")
        return

    # ── 4. Fallthrough ────────────────────────────────────────────────────────
    state = s.get("state", "waiting_resume")
    if state == "waiting_score":
        send(user_id,
             "📊 Жду ссылку на вакансию для анализа соответствия\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Или /сброс чтобы выйти из режима анализа.")
    elif state == "waiting_both":
        send(user_id,
             "🚀 Жду ссылку на вакансию — пришлю резюме и письмо\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Или /сброс чтобы выйти из этого режима.")
    elif state == "waiting_coverletter":
        send(user_id,
             "✉️ Жду ссылку на вакансию для сопроводительного письма\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Или /сброс чтобы выйти из режима письма.")
    elif state == "waiting_vacancy":
        send(user_id,
             "🔗 Жду ссылку на вакансию с hh.ru\n"
             "Пример: https://hh.ru/vacancy/12345678\n\n"
             "Или /сброс чтобы загрузить другое резюме.")
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
        token = (getattr(Config, "VK_CONFIRMATION_TOKEN", None)
                 or os.getenv("VK_CONFIRMATION_TOKEN", "ok"))
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
        logger.debug("⏭️ Duplicate msg_id=%s from user %s — skipped", message_id, user_id)
        return jsonify({"status": "ok"})

    logger.info("📨 user=%s msg_id=%s text='%.60s' attachments=%d",
                user_id, message_id, text, len(attachments))

    try:
        handle(user_id, text, attachments)
    except Exception as e:
        logger.exception("Unhandled error for user %s: %s", user_id, e)
        send(user_id, "❌ Непредвиденная ошибка. Попробуй позже.")

    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "version": "5.3.0",
        "vk_group_id": Config.VK_GROUP_ID,
        "gigachat_connected": bool(Config.GIGACHAT_API_KEY),
        "active_sessions": len(_sessions),
    })


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