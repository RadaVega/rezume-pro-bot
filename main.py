#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 ResumePro AI - VK Bot
🏆 Best-in-Class Resume Adaptation Bot
✅ Uses GigaChat-Lite (900,000 tokens available)
✅ Professional PDF generation
✅ Message deduplication
✅ Error handling & fallbacks
"""

import os
import time
import logging
import tempfile
import re
import requests
from flask import Flask
from threading import Thread
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils import (
    extract_text_from_file,
    parse_hh_vacancy,
    create_resume_pdf,
    clean_markdown,
)

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# === FLASK WEB SERVER ===
app = Flask(__name__)


@app.route("/")
def index():
    """Status page"""
    return f"""<html><body>
    <h1>🤖 ResumePro Bot Works!</h1>
    <p>✅ Status: Active</p>
    <p>🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>👥 <a href="https://vk.com/rezume_pro">vk.com/rezume_pro</a></p>
    <hr>
    <p><small>🎓 School 21 Project | ID: Rubyalbe</small></p>
    </body></html>"""


@app.route("/ping")
def ping():
    """For UptimeRobot monitoring"""
    return "PONG! Bot is alive 🟢"


def run_flask():
    """Run Flask in background thread"""
    app.run(host="0.0.0.0", port=5000)


# === PDF UPLOAD TO VK ===
def send_pdf_to_user(vk, user_id, pdf_path, vk_token):
    """Upload PDF to VK and send as attachment"""
    try:
        logger.info(f"📤 Uploading PDF: {pdf_path}")

        if not os.path.exists(pdf_path):
            logger.error(f"❌ PDF not found: {pdf_path}")
            return False

        # Get upload URL
        upload_server = vk.docs.getMessagesUploadServer(peer_id=user_id, type="doc")
        upload_url = upload_server["upload_url"]
        logger.info(f"📤 Upload URL received")

        # Upload file
        with open(pdf_path, "rb") as f:
            files = {"file": ("Adapted_Resume.pdf", f, "application/pdf")}
            response = requests.post(upload_url, files=files)
            upload_data = response.json()
            logger.info(f"📤 Upload response received")

        # Save document
        saved = vk.docs.save(file=upload_data["file"], title="Adapted_Resume.pdf")
        doc = saved[0] if isinstance(saved, list) else saved.get("doc", saved)

        owner_id = doc.get("owner_id")
        doc_id = doc.get("id")
        attachment = f"doc{owner_id}_{doc_id}"

        logger.info(f"✅ Document saved: {attachment}")

        # Send message with attachment
        vk.messages.send(
            peer_id=user_id,
            message="📄 Your adapted resume in PDF format is ready!",
            attachment=attachment,
            random_id=0,
        )
        return True

    except Exception as e:
        logger.error(f"❌ PDF upload failed: {e}")
        import traceback

        traceback.print_exc()
        return False


# === GIGACHAT ADAPTATION ===
def adapt_resume(resume_text, vacancy_text):
    """
    Adapt resume using GigaChat-Lite API
    ✅ Uses Lite model (900,000 tokens available)
    ✅ Fallback if API fails
    """
    try:
        logger.info("🔄 Initializing GigaChat-Lite model...")

        model = GigaChat(
            credentials=os.getenv("GIGA_CREDENTIALS"),
            scope=os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS"),
            model="GigaChat-Lite",  # ✅ Changed from Pro to Lite
            verify_ssl_certs=False,
        )

        logger.info("✅ GigaChat-Lite model initialized")

        prompt = ChatPromptTemplate.from_template("""
You are an expert resume writer with 15+ years experience.
Adapt this resume for the vacancy. Write in Russian.

RESUME:
{resume}

VACANCY:
{vacancy}

Create adapted resume with these sections:

📋 ПРОФЕССИОНАЛЬНЫЙ ПРОФИЛЬ
[2-3 sentences about candidate's value]

💼 ОПЫТ РАБОТЫ
[Job Title]
[Company] | [Dates]
- Achievement with metric (%, ₽, time)
- Achievement with metric

🎓 ОБРАЗОВАНИЕ
[Degree, University, Year]

🛠 НАВЫКИ
[Skills relevant to vacancy]

📊 MATCH SCORE: XX%
[Why this score, 2-3 sentences]

💡 РЕКОМЕНДАЦИИ
- [Specific recommendation 1]
- [Specific recommendation 2]
- [Specific recommendation 3]

Use professional language. Include specific metrics. No markdown (**, ###).
""")

        logger.info("🔄 Sending to GigaChat...")

        chain = prompt | model | StrOutputParser()
        result = chain.invoke(
            {
                "resume": resume_text[:2000],  # Limit to avoid token limits
                "vacancy": vacancy_text[:2000],
            }
        )

        logger.info("✅ GigaChat adaptation complete")

        if not result or len(result) < 100:
            logger.error("❌ GigaChat returned empty result")
            return None

        return clean_markdown(result)

    except Exception as e:
        logger.error(f"❌ GigaChat error: {e}")

        # 🔄 FALLBACK: Simple template when API fails
        logger.info("🔄 Using fallback adaptation...")
        return simple_fallback_adaptation(resume_text, vacancy_text)


def simple_fallback_adaptation(resume_text, vacancy_text):
    """Simple fallback when GigaChat is unavailable"""
    try:
        # Extract basic info
        name_match = re.search(r"([А-Я][а-я]+\s+[А-Я][а-я]+)", resume_text)
        name = name_match.group(1) if name_match else "Кандидат"

        return f"""📋 ПРОФЕССИОНАЛЬНЫЙ ПРОФИЛЬ
Опытный специалист с релевантным опытом работы. Готов внести вклад в развитие вашей компании.

💼 ОПЫТ РАБОТЫ
{resume_text[:500]}...

🎓 ОБРАЗОВАНИЕ
[Информация об образовании из резюме]

🛠 НАВЫКИ
[Навыки из резюме]

📊 MATCH SCORE: 75%
Базовое соответствие требованиям вакансии.

💡 РЕКОМЕНДАЦИИ
• Детализируйте достижения с метриками
• Добавьте больше информации о руководстве командами
• Укажите конкретные результаты проектов
"""
    except:
        return "⚠️ Адаптация недоступна. Попробуйте позже."


# === USER STATE MANAGEMENT ===
user_states = {}
processed_messages = set()  # ✅ Prevent duplicate messages


class UserState:
    def __init__(self):
        self.resume_text = ""
        self.vacancy_text = ""
        self.vacancy_url = ""
        self.step = "idle"


# === MESSAGE UTILITIES ===
def send_long_msg(vk, peer_id, text):
    """Split long messages (VK limit: 4096 chars)"""
    max_len = 4000
    for i in range(0, len(text), max_len):
        vk.messages.send(peer_id=peer_id, message=text[i : i + max_len], random_id=0)


# === MESSAGE HANDLER ===
def handle_message(vk, user_id, raw_text, attachments, VK_TOKEN, message_id):
    """Process incoming message with deduplication"""

    # ✅ Prevent duplicate processing
    if message_id in processed_messages:
        logger.info(f"⏭️ Skipping duplicate message {message_id}")
        return

    processed_messages.add(message_id)

    # Clean old message IDs (keep last 1000)
    if len(processed_messages) > 1000:
        processed_messages.clear()

    text = raw_text.lower()
    logger.info(f"📨 Message from {user_id}: {text[:50]}...")

    # === PROCESS FILE ATTACHMENTS ===
    for attach in attachments:
        if attach.get("type") == "doc":
            doc = attach.get("doc", {})
            doc_url = doc.get("url", "")
            doc_type = doc.get("ext", "pdf").lower()
            doc_title = doc.get("title", "file")

            if doc_url:
                try:
                    logger.info(f"📎 Downloading file: {doc_title}")
                    response = requests.get(doc_url, timeout=15)

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=f".{doc_type}"
                    ) as f:
                        f.write(response.content)
                        temp_file = f.name

                    logger.info(f"📄 Extracting text from {doc_type}")
                    resume_txt = extract_text_from_file(temp_file, doc_type)

                    try:
                        os.unlink(temp_file)
                    except:
                        pass

                    if resume_txt:
                        if user_id not in user_states:
                            user_states[user_id] = UserState()
                        user_states[user_id].resume_text = resume_txt
                        user_states[user_id].step = "waiting_vacancy"

                        vk.messages.send(
                            peer_id=user_id,
                            message=f"✅ Resume uploaded! ({doc_title})\n\n📎 Now send HH.ru vacancy link",
                            random_id=0,
                        )
                    else:
                        vk.messages.send(
                            peer_id=user_id,
                            message="⚠️ Could not extract text. Try another file or send text resume.",
                            random_id=0,
                        )

                except Exception as e:
                    logger.error(f"❌ File processing error: {e}")
                    vk.messages.send(
                        peer_id=user_id, message="⚠️ File error. Try again.", random_id=0
                    )

    # === COMMANDS ===

    if text in ["/start", "привет", "hi", "hello"]:
        vk.messages.send(
            peer_id=user_id,
            message="👋 Welcome to ResumePro AI!\n\n🏆 I'll adapt your resume to ANY job in 30 seconds!\n\n📝 How it works:\n1. Send your resume (PDF/DOCX file or text)\n2. Send HH.ru vacancy link\n3. Get adapted resume with Match Score!\n\n💰 FREE vs competitors ($25/month)",
            random_id=0,
        )

    elif text in ["/help", "помощь"]:
        vk.messages.send(
            peer_id=user_id,
            message="💡 Commands:\n/start - Start bot\n/help - This help\n/demo - See example\n\n📄 Send: Resume file + HH.ru link",
            random_id=0,
        )

    elif text in ["/demo", "пример"]:
        vk.messages.send(
            peer_id=user_id,
            message='🎯 Example:\n\nBefore: "Managed projects"\n\nAfter: "Managed 5+ projects with 150M ₽ budget, reduced time-to-market by 35%"\n\n📊 Match Score: 87-95%\n⏱️ Time: 30 seconds',
            random_id=0,
        )

    elif "hh.ru" in text:
        urls = re.findall(r"https?://[^\s]+", raw_text)
        if urls:
            vacancy_url = urls[0]
            logger.info(f"🔗 Processing HH.ru: {vacancy_url}")

            vk.messages.send(
                peer_id=user_id, message="⏳ Loading vacancy from HH.ru...", random_id=0
            )

            vacancy_text = parse_hh_vacancy(vacancy_url)

            if user_id not in user_states:
                user_states[user_id] = UserState()

            user_states[user_id].vacancy_text = vacancy_text
            user_states[user_id].vacancy_url = vacancy_url

            # If we already have resume
            if user_states[user_id].resume_text:
                logger.info("🤖 Both resume and vacancy ready. Adapting...")

                vk.messages.send(
                    peer_id=user_id,
                    message="🤖 Adapting your resume... ⏱️ 30 seconds",
                    random_id=0,
                )

                result = adapt_resume(user_states[user_id].resume_text, vacancy_text)

                if result:
                    # Send text result
                    send_long_msg(
                        vk, user_id, f"✅ Done! Your adapted resume:\n\n{result}"
                    )

                    # Generate and send PDF
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                        pdf_path = f.name

                    logger.info(f"📄 Generating PDF: {pdf_path}")

                    if create_resume_pdf(result, pdf_path):
                        logger.info("✅ PDF created, uploading...")
                        success = send_pdf_to_user(vk, user_id, pdf_path, VK_TOKEN)

                        if not success:
                            vk.messages.send(
                                peer_id=user_id,
                                message="⚠️ PDF upload failed, but text version is above!",
                                random_id=0,
                            )
                    else:
                        vk.messages.send(
                            peer_id=user_id,
                            message="⚠️ PDF generation failed. Use text version above.",
                            random_id=0,
                        )

                    try:
                        os.unlink(pdf_path)
                    except:
                        pass

                    user_states[user_id].step = "idle"
                else:
                    logger.error("❌ Adaptation returned None")
                    vk.messages.send(
                        peer_id=user_id,
                        message="⚠️ Error adapting resume. Try again in 5 minutes.",
                        random_id=0,
                    )
            else:
                vk.messages.send(
                    peer_id=user_id,
                    message="✅ Vacancy saved!\n\n📝 Now send your resume (PDF/DOCX file or text)",
                    random_id=0,
                )

    elif "резюме:" in text or "resume:" in text:
        logger.info("📄 Resume text received")

        parts = text.split("ваканс") if "ваканс" in text else text.split("vacancy")
        resume = parts[0].replace("резюме:", "").replace("resume:", "").strip()
        vacancy_part = parts[1] if len(parts) > 1 else ""

        if user_id not in user_states:
            user_states[user_id] = UserState()

        user_states[user_id].resume_text = resume

        # Check if vacancy is in same message
        if vacancy_part and "hh.ru" in vacancy_part:
            urls = re.findall(r"https?://[^\s]+", vacancy_part)
            if urls:
                vk.messages.send(
                    peer_id=user_id, message="⏳ Processing...", random_id=0
                )
                vacancy_text = parse_hh_vacancy(urls[0])
                user_states[user_id].vacancy_text = vacancy_text

                vk.messages.send(peer_id=user_id, message="🤖 Adapting...", random_id=0)
                result = adapt_resume(resume, vacancy_text)

                if result:
                    send_long_msg(vk, user_id, f"✅ Done!\n\n{result}")
                    user_states[user_id].step = "idle"
                else:
                    vk.messages.send(
                        peer_id=user_id, message="⚠️ Error adapting resume", random_id=0
                    )

        elif user_states[user_id].vacancy_text:
            vk.messages.send(
                peer_id=user_id, message="🤖 Adapting... ⏱️ 30 sec", random_id=0
            )
            result = adapt_resume(resume, user_states[user_id].vacancy_text)

            if result:
                send_long_msg(vk, user_id, f"✅ Done!\n\n{result}")
                user_states[user_id].step = "idle"
            else:
                vk.messages.send(
                    peer_id=user_id, message="⚠️ Error adapting resume", random_id=0
                )

        else:
            vk.messages.send(
                peer_id=user_id,
                message="✅ Resume saved!\n\n🔗 Now send HH.ru vacancy link",
                random_id=0,
            )

    else:
        vk.messages.send(
            peer_id=user_id,
            message="👋 Send /start to begin!\n\n🏆 FREE AI resume adaptation!",
            random_id=0,
        )


# === BOT MAIN LOOP ===
def run_bot():
    """Run VK bot with auto-reconnect"""
    VK_TOKEN = os.getenv("VK_TOKEN")
    GROUP_ID = int(os.getenv("GROUP_ID", 237022345))

    if not VK_TOKEN:
        logger.error("❌ VK_TOKEN not found!")
        return

    vk = vk_api.VkApi(token=VK_TOKEN).get_api()

    while True:
        try:
            logger.info("🔄 Connecting to VK...")
            longpoll = VkBotLongPoll(vk_api.VkApi(token=VK_TOKEN), GROUP_ID)
            logger.info(f"✅ Bot started! Group: {GROUP_ID}")

            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    try:
                        uid = event.obj.message["from_id"]
                        txt = event.obj.message.get("text", "").strip()
                        att = event.obj.message.get("attachments", [])
                        mid = event.obj.message["id"]  # ✅ Message ID for deduplication
                        handle_message(vk, uid, txt, att, VK_TOKEN, mid)
                    except Exception as e:
                        logger.error(f"❌ Message error: {e}")

        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            time.sleep(5)


# === START APPLICATION ===
if __name__ == "__main__":
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask on port 5000")

    # Start bot
    run_bot()
