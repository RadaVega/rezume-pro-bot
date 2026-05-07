# main.py (v6.13 – file detection moved before commands)
"""
ResumePro AI — VK Bot v6.13
- File attachment detection now runs before any command.
- Guaranteed return after file processing.
"""

import sys as _sys
import os
import re
import time
import random
import logging
import tempfile
import threading
from collections import OrderedDict

_PKGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pkgs")
if os.path.isdir(_PKGS) and _PKGS not in sys.path:
    sys.path.insert(0, _PKGS)

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

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

logger.info("🔄 Connecting to VK...")
vk_session = VkApi(token=os.getenv("VK_TOKEN"))

if not Config.VK_GROUP_ID:
    logger.error("❌ VK_GROUP_ID is not set!")
    raise ValueError("VK_GROUP_ID is required")
logger.info("✅ VK Group ID: %s", Config.VK_GROUP_ID)

logger.info("🔄 Connecting to GigaChat...")
gigachat = GigaChat(credentials=Config.GIGACHAT_API_KEY, verify_ssl_certs=False)
generator = AntiHallucinationGenerator(gigachat, max_retries=Config.MAX_RETRIES)
logger.info("✅ Bot ready. Group: %s", Config.VK_GROUP_ID)

_seen_msg_ids = OrderedDict()
_seen_lock = threading.Lock()
_MSG_TTL = 60
_MSG_CACHE_MAX = 2000

def _is_duplicate_message(message_id: int) -> bool:
    if not message_id:
        return False
    now = time.time()
    with _seen_lock:
        while _seen_msg_ids and next(iter(_seen_msg_ids.values())) < now - _MSG_TTL:
            _seen_msg_ids.popitem(last=False)
        if message_id in _seen_msg_ids:
            return True
        _seen_msg_ids[message_id] = now
        if len(_seen_msg_ids) > _MSG_CACHE_MAX:
            _seen_msg_ids.popitem(last=False)
    return False

_sessions = {}
_session_lock = threading.Lock()
_SESSION_TTL = 3600

def _get_session(user_id: int) -> dict:
    with _session_lock:
        now = time.time()
        s = _sessions.get(user_id)
        if s and now - s.get("updated_at", 0) < _SESSION_TTL:
            return s
        _sessions[user_id] = {
            "resume_text": None,
            "resume_filename": None,
            "state": "waiting_resume",
            "forced_lang": None,
            "updated_at": now,
        }
        return _sessions[user_id]

def _touch(user_id: int) -> None:
    with _session_lock:
        if user_id in _sessions:
            _sessions[user_id]["updated_at"] = time.time()

def _clear_session(user_id: int) -> None:
    with _session_lock:
        _sessions.pop(user_id, None)

def _session_cleanup():
    while True:
        time.sleep(600)
        now = time.time()
        with _session_lock:
            expired = [uid for uid, s in _sessions.items()
                       if now - s.get("updated_at", 0) > _SESSION_TTL]
            for uid in expired:
                _sessions.pop(uid, None)
        if expired:
            logger.debug("🧹 Cleaned %d expired sessions", len(expired))

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
    "• /сброс    — начать заново\n"
    "• /язык английский — все выходные документы на английском\n"
    "• /язык русский    — все выходные документы на русском\n"
    "• /язык авто       — автоматическое определение языка вакансии\n\n"
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
    "Управление языком:\n"
    "• /язык английский — принудительно английский\n"
    "• /язык русский    — принудительно русский\n"
    "• /язык авто       — автоматическое определение (по умолчанию)\n\n"
    "⚠️ Поддерживаются вакансии с hh.ru, SuperJob, Rabota.ru, LinkedIn, Habr, а также вставленный текст.\n\n"
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

def send(user_id: int, text: str) -> bool:
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
            logger.warning("⚠️ User %s blocked messages", user_id)
        else:
            logger.error("❌ VK API error → user %s | code=%s | %s", user_id, e.code, e)
        return False
    except Exception as e:
        logger.exception("❌ send() error → user %s: %s", user_id, e)
        return False

def send_document(user_id: int, file_path: str, title: str) -> bool:
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
            raise ValueError(f"No file key: {resp.text}")
        saved = vk.docs.save(file=file_key, title=title)
        doc = saved.get("doc") or (saved[0] if isinstance(saved, list) else None)
        if not doc:
            raise ValueError(f"Invalid save response: {saved}")
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
        logger.info("✅ Document sent: '%s'", title)
        return True
    except Exception as e:
        logger.exception("❌ send_document error: %s", e)
        return False

def _send_pdf_or_text(user_id: int, text: str, title: str, fallback_header: str) -> None:
    pdf_path = None
    try:
        pdf_path = text_to_pdf(text, title)
        if send_document(user_id, pdf_path, title):
            return
        raise RuntimeError("send_document returned False")
    except Exception as e:
        logger.warning("PDF send failed (%s), falling back to text", e)
        send(user_id, fallback_header + text)
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)

def download_file(url: str, ext: str) -> str:
    try:
        resp = http_requests.get(url, timeout=30)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext.lower()}") as f:
            f.write(resp.content)
            return f.name
    except Exception as e:
        logger.error("❌ Download error: %s", e)
        return ""

def extract_hh_url(text: str) -> str:
    m = re.search(r"https?://[^\s]*hh\.ru/vacancy/\d+[^\s]*", text)
    if m:
        return m.group(0).rstrip(".,;!?)")
    m = re.search(r"hh\.ru/vacancy/\d+", text)
    return ("https://" + m.group(0)) if m else ""

def extract_any_url(text: str) -> str:
    for m in re.finditer(r"https?://[^\s]+", text):
        url = m.group(0).rstrip(".,;!?)")
        if "hh.ru/vacancy/" not in url:
            return url
    return ""

def ats_score(confidence: float) -> int:
    return round(confidence * 100)

def build_score_report(resume_text: str, vacancy_text: str) -> str:
    resume_entities = extract_entities(resume_text)
    resume_tech = resume_entities["skills"] & TECH_SKILLS
    vacancy_tech = _scan_tech_skills(vacancy_text)
    present = sorted(resume_tech & vacancy_tech)
    missing = sorted(vacancy_tech - resume_tech)
    extra = sorted(resume_tech - vacancy_tech)
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

def detect_language(text: str, url_hint: str = "") -> str:
    if "linkedin.com" in url_hint.lower():
        return "en"
    if not text:
        return "ru"
    cyrillic = sum(1 for ch in text if 'а' <= ch.lower() <= 'я')
    latin = sum(1 for ch in text if 'a' <= ch.lower() <= 'z')
    english_words = {"the", "and", "for", "with", "you", "are", "not", "this", "that", "will", "from", "have", "your", "please", "experience", "skills", "requirements"}
    text_lower = text.lower()
    english_score = sum(1 for word in english_words if f" {word} " in text_lower or text_lower.startswith(word + " "))
    if english_score >= 2:
        return "en"
    if latin > cyrillic * 1.5:
        return "en"
    if cyrillic > latin * 1.5:
        return "ru"
    return "ru"

def _cmd_language_set(user_id: int, lang: str):
    s = _get_session(user_id)
    with _session_lock:
        s["forced_lang"] = lang
    msg = {
        "en": "🌐 Язык установлен на английский. Все выходные документы будут на английском.",
        "ru": "🌐 Язык установлен на русский. Все выходные документы будут на русском.",
    }
    send(user_id, msg.get(lang, "🌐 Автоматическое определение языка вакансии (по умолчанию)."))

def _cmd_status(user_id: int):
    s = _get_session(user_id)
    with _session_lock:
        state = s.get("state", "waiting_resume")
        resume_file = s.get("resume_filename")
        resume_len = len(s.get("resume_text") or "")
        last_url = s.get("last_vacancy_url")
        forced_lang = s.get("forced_lang")
    state_labels = {
        "waiting_resume": "⏳ Ожидание резюме",
        "waiting_vacancy": "🔗 Ожидание ссылки на вакансию",
        "waiting_score": "📊 Режим анализа соответствия",
        "waiting_both": "🚀 Режим: резюме + письмо",
        "waiting_coverletter": "✉️ Режим сопроводительного письма",
        "processing": "⚙️ Обрабатываю запрос…",
    }
    lang_label = {"en": "английский", "ru": "русский", None: "авто"}
    lines = ["📋 Состояние сессии:\n"]
    lines.append(f"📄 Резюме: {resume_file} ({resume_len} символов)" if resume_file else "📄 Резюме: не загружено")
    lines.append(f"🔄 Режим: {state_labels.get(state, state)}")
    lines.append(f"🌐 Язык (принудительно): {lang_label[forced_lang]}")
    if last_url:
        lines.append(f"🔗 Последняя вакансия: {last_url}")
    if state == "waiting_resume":
        lines.append("\nОтправь файл резюме (PDF или DOCX) чтобы начать.")
    elif state == "waiting_vacancy":
        lines.append("\nПришли ссылку с hh.ru — или выбери режим (/анализ, /письмо, /оба).")
    send(user_id, "\n".join(lines))

def _cmd_reset(user_id: int):
    _clear_session(user_id)
    send(user_id, "🔄 Сессия сброшена.\n\nОтправь новый файл резюме или напиши /старт.")

def _cmd_help(user_id: int):
    send(user_id, HELP)

def _cmd_demo(user_id: int):
    send(user_id, DEMO)

def _cmd_start(user_id: int):
    _clear_session(user_id)
    send(user_id, GREETING)

def _cmd_score_mode(user_id: int):
    s = _get_session(user_id)
    if not s.get("resume_text"):
        send(user_id, "📎 Сначала отправь файл резюме (PDF или DOCX), а затем введи /анализ.")
        return
    with _session_lock:
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
        s["state"] = "waiting_score"
    _touch(user_id)
    fname = s.get("resume_filename", "резюме")
    send(user_id, f"📊 Режим: анализ соответствия\nРезюме: {fname}\n\nПришли ссылку на вакансию с hh.ru — и я покажу:\n  ✅ какие навыки из резюме совпадают с вакансией\n  ❌ чего не хватает\n  💡 что стоит выделить или доучить\n\nПример: https://hh.ru/vacancy/12345678\n\nДля отмены отправь /сброс")

def _cmd_both_mode(user_id: int):
    s = _get_session(user_id)
    if not s.get("resume_text"):
        send(user_id, "📎 Сначала отправь файл резюме (PDF или DOCX), а затем введи /оба.")
        return
    with _session_lock:
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
        s["state"] = "waiting_both"
    _touch(user_id)
    fname = s.get("resume_filename", "резюме")
    send(user_id, f"🚀 Режим: резюме + письмо\nРезюме: {fname}\n\nПришли ссылку на вакансию с hh.ru — и я сразу подготовлю\nадаптированное резюме и сопроводительное письмо.\nПример: https://hh.ru/vacancy/12345678\n\nДля отмены отправь /сброс")

def _cmd_letter_mode(user_id: int):
    s = _get_session(user_id)
    if not s.get("resume_text"):
        send(user_id, "📎 Сначала отправь файл резюме (PDF или DOCX), а затем введи /письмо.")
        return
    with _session_lock:
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
        s["state"] = "waiting_coverletter"
    _touch(user_id)
    fname = s.get("resume_filename", "резюме")
    send(user_id, f"✉️ Режим сопроводительного письма\nРезюме: {fname}\n\nПришли ссылку на вакансию с hh.ru — и я напишу письмо под неё.\nПример: https://hh.ru/vacancy/12345678\n\nДля отмены отправь /сброс")

def _cmd_health(user_id: int):
    send(user_id, f"✅ Бот работает! Версия 6.13\nАктивных сессий: {len(_sessions)}")

def _cmd_download(user_id: int):
    s = _get_session(user_id)
    with _session_lock:
        has_resume = bool(s.get("last_resume_pdf"))
        has_letter = bool(s.get("last_letter_pdf"))
    if not has_resume and not has_letter:
        send(user_id, "📭 Нет сохранённых файлов для повторной отправки.\n\nПришли ссылку на вакансию с hh.ru — и я сгенерирую документы.\nДля резюме + письма сразу используй /оба")
        return
    with _session_lock:
        if s.get("state") == "processing":
            send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
            return
    send(user_id, "📤 Повторно отправляю файлы...")
    if has_resume:
        with _session_lock:
            r = s["last_resume_pdf"]
        _send_pdf_or_text(user_id, r["text"], title=r["title"], fallback_header="📄 Адаптированное резюме:\n\n")
    if has_letter:
        with _session_lock:
            l = s["last_letter_pdf"]
        _send_pdf_or_text(user_id, l["text"], title=l["title"], fallback_header="✉️ Сопроводительное письмо:\n\n")
    send(user_id, f"✅ Готово! Отправил: {'резюме' if has_resume else ''}{' и письмо' if has_letter else ''}".strip())

def handle(user_id: int, text: str, attachments: list) -> None:
    s = _get_session(user_id)

    # 🔥 FILE ATTACHMENT HANDLING – MUST BE FIRST 🔥
    doc = None
    for a in attachments:
        if a.get("type") == "doc":
            doc = a
            break
        if "doc" in a:
            doc = a
            logger.info(f"Found doc in attachment with type {a.get('type')}")
            break

    if doc:
        doc_info = doc.get("doc", doc)
        ext = doc_info.get("ext", "").lower()
        fname = doc_info.get("title", doc_info.get("filename", "файл"))
        if ext not in ("pdf", "docx", "doc"):
            send(user_id, "❌ Неподдерживаемый формат.\nОтправь резюме в формате PDF или DOCX.")
            return
        send(user_id, f"⏳ Читаю файл {fname}...")
        url = doc_info.get("url")
        if not url:
            send(user_id, "❌ Не удалось получить URL файла.")
            return
        path = download_file(url, ext)
        if not path:
            send(user_id, "❌ Не удалось загрузить файл. Попробуй ещё раз.")
            return
        resume_text = extract_text_from_file(path, ext)
        try:
            os.unlink(path)
        except:
            pass
        if not resume_text or len(resume_text) < 50:
            send(user_id, "❌ Не удалось извлечь текст.\nУбедись, что PDF не отсканирован, или используй DOCX.")
            return
        with _session_lock:
            s["resume_text"] = resume_text
            s["resume_filename"] = fname
            s["state"] = "waiting_vacancy"
        _touch(user_id)
        logger.info("📄 Resume loaded: %s (%d chars)", fname, len(resume_text))
        send(user_id, f"✅ Резюме получено: {fname}\n\nТеперь пришли ссылку на вакансию (hh.ru, любой другой сайт)\nили просто вставь текст вакансии прямо в чат.\n\n💡 После адаптации можно прислать другую вакансию — резюме останется в памяти!")
        return   # CRITICAL – stop further processing

    # ── Now handle commands ─────────────────────────────────────────────────
    cmd = text.lower().strip()

    # Language commands
    if cmd in ("/язык английский", "/lang en", "/lang english"):
        send(user_id, "✏️ Принято, устанавливаю английский язык...")
        threading.Thread(target=_cmd_language_set, args=(user_id, "en"), daemon=True).start()
        return
    if cmd in ("/язык русский", "/lang ru", "/lang russian"):
        send(user_id, "✏️ Принято, устанавливаю русский язык...")
        threading.Thread(target=_cmd_language_set, args=(user_id, "ru"), daemon=True).start()
        return
    if cmd in ("/язык авто", "/lang auto", "/lang default"):
        send(user_id, "✏️ Принято, включаю автоматическое определение языка...")
        threading.Thread(target=_cmd_language_set, args=(user_id, None), daemon=True).start()
        return

    # Other commands
    if cmd in ("/статус", "/status", "статус"):
        send(user_id, "✏️ Собираю информацию...")
        threading.Thread(target=_cmd_status, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/сброс", "/reset", "reset", "сброс"):
        send(user_id, "✏️ Сбрасываю сессию...")
        threading.Thread(target=_cmd_reset, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/помощь", "/help", "help", "помощь"):
        send(user_id, "✏️ Открываю справку...")
        threading.Thread(target=_cmd_help, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/пример", "/demo", "demo", "пример"):
        send(user_id, "✏️ Показываю пример...")
        threading.Thread(target=_cmd_demo, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/старт", "/start", "start", "начать", "привет", "hi", "hello", ""):
        send(user_id, "✏️ Показываю приветствие...")
        threading.Thread(target=_cmd_start, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/анализ", "/score", "score", "анализ", "скор"):
        send(user_id, "✏️ Переключаю в режим анализа...")
        threading.Thread(target=_cmd_score_mode, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/оба", "/both", "both", "оба", "всё"):
        send(user_id, "✏️ Переключаю в режим резюме+письмо...")
        threading.Thread(target=_cmd_both_mode, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/письмо", "/coverletter", "coverletter", "письмо", "сопроводительное"):
        send(user_id, "✏️ Переключаю в режим письма...")
        threading.Thread(target=_cmd_letter_mode, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/здоровье", "/health"):
        send(user_id, "✏️ Проверяю состояние...")
        threading.Thread(target=_cmd_health, args=(user_id,), daemon=True).start()
        return
    if cmd in ("/скачать", "/download", "скачать"):
        send(user_id, "✏️ Повторно отправляю файлы...")
        threading.Thread(target=_cmd_download, args=(user_id,), daemon=True).start()
        return

    # ── Vacancy input (only if no attachment and no command matched) ─────────
    hh_url = extract_hh_url(text)
    other_url = ""
    pasted_vacancy = ""
    if not hh_url:
        link_att = next((a for a in attachments if a.get("type") == "link"), None)
        if link_att:
            link_url = link_att.get("link", {}).get("url", "")
            hh_url = extract_hh_url(link_url)
            if not hh_url and link_url:
                other_url = link_url
                logger.info("🔗 Non-hh URL from link attachment: %s", other_url)
    if not hh_url and not other_url:
        other_url = extract_any_url(text)
    if (not hh_url and not other_url and len(text) > 300 and not text.startswith("/") and s.get("resume_text")):
        pasted_vacancy = text
    vacancy_input = hh_url or other_url or pasted_vacancy

    if vacancy_input:
        if not s.get("resume_text"):
            with _session_lock:
                if pasted_vacancy:
                    s["pending_vacancy_text"] = pasted_vacancy
                else:
                    s["pending_vacancy_url"] = hh_url or other_url
            _touch(user_id)
            send(user_id, "📎 Сначала отправь файл резюме (PDF или DOCX).\n\n💾 Запомнил описание/ссылку вакансии — пришли резюме и сразу начну!")
            return
        with _session_lock:
            current_state = s.get("state")
            if current_state == "processing":
                send(user_id, "⏳ Уже обрабатываю предыдущий запрос, подожди немного.")
                return
            s["state"] = "processing"
            s["last_vacancy_url"] = vacancy_input
        _touch(user_id)

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
            send(user_id, "⏳ Адаптирую резюме и пишу сопроводительное письмо последовательно...\nЭто займёт около 60 секунд.")
        else:
            send(user_id, "⏳ Адаптирую резюме и пишу сопроводительное письмо последовательно...\nЭто займёт около 60 секунд.")

        def _process():
            try:
                vacancy_text = vacancy_getter()
                if isinstance(vacancy_text, str) and vacancy_text.startswith("Error:"):
                    send(user_id, f"❌ Не удалось получить данные вакансии.\n{vacancy_text}\n\nПопробуй вставить текст вакансии прямо в чат — скопируй описание и пришли его сюда.")
                    with _session_lock:
                        if coverletter_mode:
                            s["state"] = "waiting_coverletter"
                        elif both_mode:
                            s["state"] = "waiting_both"
                        else:
                            s["state"] = "waiting_vacancy"
                    return

                forced = s.get("forced_lang")
                if forced:
                    vacancy_lang = forced
                    logger.info(f"Using forced language: {forced}")
                else:
                    vacancy_lang = detect_language(vacancy_text, vacancy_label)
                    if "linkedin.com" in vacancy_label:
                        vacancy_lang = "en"
                        logger.info("LinkedIn detected -> forcing English")
                    else:
                        logger.info(f"Auto-detected language: {vacancy_lang}")
                with _session_lock:
                    s["vacancy_lang"] = vacancy_lang

                if score_mode:
                    report = build_score_report(s["resume_text"], vacancy_text)
                    send(user_id, report)
                    with _session_lock:
                        s["state"] = "waiting_vacancy"
                    _touch(user_id)
                    send(user_id, "💡 Хочешь адаптировать резюме под эту вакансию?\n• /оба — резюме + письмо сразу\n• просто пришли ту же ссылку — получишь адаптированное резюме\n• /сброс — загрузить другое резюме")
                    logger.info("Score report done")

                elif coverletter_mode:
                    letter, metadata = generator.generate_cover_letter(s["resume_text"], vacancy_text, language=vacancy_lang)
                    letter_clean = clean_markdown(letter)
                    if metadata.get("fallback_used"):
                        send(user_id, "⚠️ Не удалось сгенерировать письмо — возвращаем заготовку.\n\n" + letter_clean)
                    else:
                        send(user_id, "✉️ Генерирую PDF сопроводительного письма...")
                        fname = s.get("resume_filename", "резюме").rsplit(".", 1)[0]
                        letter_title = f"Сопроводительное письмо — {fname}"
                        _send_pdf_or_text(user_id, letter_clean, title=letter_title, fallback_header="✉️ Сопроводительное письмо:\n\n")
                        with _session_lock:
                            s["last_letter_pdf"] = {"text": letter_clean, "title": letter_title}
                    with _session_lock:
                        s["state"] = "waiting_vacancy"
                    _touch(user_id)
                    send(user_id, "💡 Хочешь адаптировать резюме под эту же вакансию?\nПросто пришли ту же ссылку ещё раз.\nДля нового резюме отправь /сброс")
                    logger.info("Cover letter done")

                elif both_mode:
                    try:
                        adapted, r_meta = generator.generate_safe_resume(s["resume_text"], vacancy_text, language=vacancy_lang)
                        adapted_clean = clean_markdown(adapted)
                        validation_dict = r_meta.get("validation")
                        if validation_dict is None:
                            score = 60
                        else:
                            conf = validation_dict.get("confidence", 1.0)
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
                            _send_pdf_or_text(user_id, resume_pdf_text, title=resume_title, fallback_header=f"✅ Резюме адаптировано! Match Score: {score}/100\n\n")
                            with _session_lock:
                                s["last_resume_pdf"] = {"text": resume_pdf_text, "title": resume_title}
                        letter, l_meta = generator.generate_cover_letter(s["resume_text"], vacancy_text, language=vacancy_lang)
                        letter_clean = clean_markdown(letter)
                        if l_meta.get("fallback_used"):
                            send(user_id, "⚠️ Не удалось сгенерировать письмо — возвращаем заготовку.\n\n" + letter_clean)
                        else:
                            send(user_id, "✉️ Генерирую PDF сопроводительного письма...")
                            letter_title = f"Сопроводительное письмо — {fname}"
                            _send_pdf_or_text(user_id, letter_clean, title=letter_title, fallback_header="✉️ Сопроводительное письмо:\n\n")
                            with _session_lock:
                                s["last_letter_pdf"] = {"text": letter_clean, "title": letter_title}
                        with _session_lock:
                            s["state"] = "waiting_vacancy"
                        _touch(user_id)
                        send(user_id, "💡 Резюме и письмо готовы! Пришли новую ссылку для другой вакансии.\nДля нового резюме отправь /сброс")
                        logger.info("Both done")
                    except Exception as e:
                        logger.exception("Error in both_mode: %s", e)
                        send(user_id, "❌ Ошибка при генерации. Попробуй ещё раз.")
                        with _session_lock:
                            s["state"] = "waiting_vacancy"

                else:
                    # DEFAULT MODE (auto both)
                    try:
                        adapted, r_meta = generator.generate_safe_resume(s["resume_text"], vacancy_text, language=vacancy_lang)
                        adapted_clean = clean_markdown(adapted)
                        validation_dict = r_meta.get("validation")
                        score = 60 if validation_dict is None else ats_score(validation_dict.get("confidence", 1.0))
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
                            _send_pdf_or_text(user_id, resume_pdf_text, title=resume_title, fallback_header=f"✅ Резюме адаптировано! Match Score: {score}/100\n\n")
                            with _session_lock:
                                s["last_resume_pdf"] = {"text": resume_pdf_text, "title": resume_title}
                        letter, l_meta = generator.generate_cover_letter(s["resume_text"], vacancy_text, language=vacancy_lang)
                        letter_clean = clean_markdown(letter)
                        if l_meta.get("fallback_used"):
                            send(user_id, "⚠️ Не удалось сгенерировать письмо — возвращаем заготовку.\n\n" + letter_clean)
                        else:
                            send(user_id, "✉️ Генерирую PDF сопроводительного письма...")
                            letter_title = f"Сопроводительное письмо — {fname}"
                            _send_pdf_or_text(user_id, letter_clean, title=letter_title, fallback_header="✉️ Сопроводительное письмо:\n\n")
                            with _session_lock:
                                s["last_letter_pdf"] = {"text": letter_clean, "title": letter_title}
                        with _session_lock:
                            s["state"] = "waiting_vacancy"
                        _touch(user_id)
                        send(user_id, "💡 Резюме и письмо готовы! Пришли новую ссылку для другой вакансии.\nДля нового резюме отправь /сброс")
                        logger.info("Auto both done")
                    except Exception as e:
                        logger.exception("Error in auto mode: %s", e)
                        send(user_id, "❌ Ошибка при генерации. Попробуй ещё раз.")
                        with _session_lock:
                            s["state"] = "waiting_vacancy"

            except Exception as e:
                logger.exception("_process outer error: %s", e)
                send(user_id, "❌ Ошибка при генерации. Попробуй ещё раз.")
                with _session_lock:
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

    # ── Fallthrough (unrecognized text, no file, no vacancy) ─────────────────
    state = s.get("state", "waiting_resume")
    if state == "waiting_score":
        send(user_id, "📊 Жду ссылку на вакансию для анализа соответствия\nПример: https://hh.ru/vacancy/12345678\n\nИли /сброс чтобы выйти из режима анализа.")
    elif state == "waiting_both":
        send(user_id, "🚀 Жду ссылку на вакансию — пришлю резюме и письмо\nПример: https://hh.ru/vacancy/12345678\n\nИли /сброс чтобы выйти из этого режима.")
    elif state == "waiting_coverletter":
        send(user_id, "✉️ Жду ссылку на вакансию для сопроводительного письма\nПример: https://hh.ru/vacancy/12345678\n\nИли /сброс чтобы выйти из режима письма.")
    elif state == "waiting_vacancy":
        send(user_id, "🔗 Жду ссылку на вакансию с hh.ru\nПример: https://hh.ru/vacancy/12345678\n\nИли /сброс чтобы загрузить другое резюме.")
    elif state == "processing":
        send(user_id, "⏳ Ещё обрабатываю запрос, подожди немного...")
    else:
        send(user_id, GREETING)

def _safe_handle(user_id: int, text: str, attachments: list) -> None:
    try:
        handle(user_id, text, attachments)
    except Exception as e:
        logger.exception("Unhandled error for user %s: %s", user_id, e)
        send(user_id, "❌ Непредвиденная ошибка. Попробуй позже.")

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    if data.get("type") == "confirmation":
        token = (getattr(Config, "VK_CONFIRMATION_TOKEN", None) or os.getenv("VK_CONFIRMATION_TOKEN", "ok"))
        return str(token)
    if data.get("type") != "message_new":
        return jsonify({"status": "ok"})
    msg = data.get("object", {}).get("message", {})
    message_id = msg.get("id")
    user_id = msg.get("from_id")
    text = (msg.get("text") or "").strip()
    attachments = msg.get("attachments") or []
    if not user_id or user_id < 0:
        return jsonify({"status": "ok"})
    if _is_duplicate_message(message_id):
        logger.debug("Duplicate msg_id=%s from user %s — skipped", message_id, user_id)
        return jsonify({"status": "ok"})
    logger.info("📨 user=%s msg_id=%s text='%.60s' attachments=%d", user_id, message_id, text, len(attachments))
    threading.Thread(target=_safe_handle, args=(user_id, text, attachments), daemon=True).start()
    return jsonify({"status": "ok"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "version": "6.13",
        "vk_group_id": Config.VK_GROUP_ID,
        "gigachat_connected": bool(Config.GIGACHAT_API_KEY),
        "active_sessions": len(_sessions),
    })

@app.route("/validate", methods=["POST"])
def validate_endpoint():
    body = request.json or {}
    original = body.get("original", "")
    adapted = body.get("adapted", "")
    if not original or not adapted:
        return jsonify({"error": "original and adapted fields are required"}), 400
    from utils.validation import validate_resume_facts
    result = validate_resume_facts(original, adapted)
    result["summary"] = get_validation_summary(result)
    for key in ("original_entities", "adapted_entities"):
        result[key] = {k: sorted(v) if isinstance(v, set) else v for k, v in result.get(key, {}).items()}
    return jsonify(result)

if __name__ == "__main__":
    logger.info("🚀 Starting ResumePro AI bot v6.13...")
    logger.info("📋 Config: VK_GROUP_ID=%s, PORT=%s", Config.VK_GROUP_ID, Config.PORT)
    threading.Thread(target=_session_cleanup, daemon=True).start()
    app.run(host="0.0.0.0", port=Config.PORT, debug=False, threaded=True)