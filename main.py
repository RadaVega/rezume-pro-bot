#!/usr/bin/env python3
import os, time, logging, tempfile, re, requests
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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    return f"<html><body><h1>ResumePro Bot Works!</h1><p>{time.strftime('%Y-%m-%d %H:%M:%S')}</p></body></html>"


@app.route("/ping")
def ping():
    return "PONG!"


def run_flask():
    app.run(host="0.0.0.0", port=5000)


def send_pdf_to_user(vk, user_id, pdf_path, vk_token):
    try:
        logger.info(f"📤 Uploading PDF: {pdf_path}")

        # Check file exists
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
            logger.info(f"📤 Upload response: {upload_data}")

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


def adapt_resume(resume_text, vacancy_text):
    try:
        model = GigaChat(
            credentials=os.getenv("GIGA_CREDENTIALS"),
            scope=os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS"),
            model="GigaChat-Pro",
            verify_ssl_certs=False,
        )

        prompt = ChatPromptTemplate.from_template("""
Adapt this resume for the vacancy. NO markdown (**, ###, ---). Clean text with emojis.

RESUME:
{resume}

VACANCY:
{vacancy}

Format:
📋 PROFESSIONAL PROFILE
[text]

💼 WORK EXPERIENCE
[details]

🎓 EDUCATION
[details]

🛠 SKILLS
[details]

📊 MATCH SCORE: XX%
[explanation]

💡 RECOMMENDATIONS
• [point 1]
• [point 2]
""")

        chain = prompt | model | StrOutputParser()
        result = chain.invoke({"resume": resume_text, "vacancy": vacancy_text})
        return clean_markdown(result)

    except Exception as e:
        logger.error(f"❌ GigaChat error: {e}")
        return "Error adapting resume"


user_states = {}


class UserState:
    def __init__(self):
        self.resume_text = ""
        self.vacancy_text = ""
        self.step = "idle"


def send_long_msg(vk, peer_id, text):
    """Split long messages"""
    max_len = 4000
    for i in range(0, len(text), max_len):
        vk.messages.send(peer_id=peer_id, message=text[i : i + max_len], random_id=0)


def handle_message(vk, user_id, raw_text, attachments, VK_TOKEN):
    text = raw_text.lower()
    logger.info(f"📨 Message from {user_id}: {text[:50]}...")

    # Process file attachments
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

    # Commands
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

                # Send text result
                send_long_msg(vk, user_id, f"✅ Done! Your adapted resume:\n\n{result}")

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
                send_long_msg(vk, user_id, f"✅ Done!\n\n{result}")
                user_states[user_id].step = "idle"

        elif user_states[user_id].vacancy_text:
            vk.messages.send(
                peer_id=user_id, message="🤖 Adapting... ⏱️ 30 sec", random_id=0
            )
            result = adapt_resume(resume, user_states[user_id].vacancy_text)
            send_long_msg(vk, user_id, f"✅ Done!\n\n{result}")
            user_states[user_id].step = "idle"

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


def run_bot():
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
                        handle_message(vk, uid, txt, att, VK_TOKEN)
                    except Exception as e:
                        logger.error(f"❌ Message error: {e}")
                        import traceback

                        traceback.print_exc()

        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    logger.info("✅ Flask on port 5000")
    run_bot()
