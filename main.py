#!/usr/bin/env python3
import os, time, logging, tempfile, re, requests
from flask import Flask
from threading import Thread
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils import extract_text_from_file, parse_hh_vacancy, create_resume_pdf, clean_markdown

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

@app.route('/')
def index():
    return f"<html><body><h1>Bot Works!</h1><p>{time.strftime('%Y-%m-%d %H:%M:%S')}</p></body></html>"

@app.route('/ping')
def ping():
    return 'PONG! Bot is alive'

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def send_pdf_to_user(vk, user_id, pdf_path, vk_token):
    try:
        upload = vk.docs.getMessagesUploadServer(peer_id=user_id)
        with open(pdf_path, 'rb') as f:
            resp = requests.post(upload['upload_url'], files={'file': ('resume.pdf', f)})
        saved = vk.docs.save(file=resp.json()['file'], title='Resume.pdf')
        doc = saved[0] if isinstance(saved, list) else saved.get('doc', saved)
        vk.messages.send(peer_id=user_id, message="PDF ready!", attachment=f"doc{doc['owner_id']}_{doc['id']}", random_id=0)
        return True
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return False

def adapt_resume(resume_text, vacancy_text):
    try:
        model = GigaChat(credentials=os.getenv("GIGA_CREDENTIALS"), scope=os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS"), model="GigaChat-Pro", verify_ssl_certs=False)
        prompt = ChatPromptTemplate.from_template("Adapt resume: {resume} for vacancy: {vacancy}. No markdown. Clean text with emojis.")
        result = (prompt | model | StrOutputParser()).invoke({"resume": resume_text, "vacancy": vacancy_text})
        return clean_markdown(result)
    except Exception as e:
        logger.error(f"GigaChat error: {e}")
        return "Try later"

user_states = {}
class UserState:
    def __init__(self):
        self.resume_text = ""
        self.vacancy_text = ""
        self.step = "idle"

def send_long_msg(vk, peer_id, text):
    for i in range(0, len(text), 4000):
        vk.messages.send(peer_id=peer_id, message=text[i:i+4000], random_id=0)

def handle_message(vk, user_id, raw_text, attachments, VK_TOKEN):
    text = raw_text.lower()
    logger.info(f"Msg from {user_id}: {text[:50]}")
    
    for attach in attachments:
        if attach.get('type') == 'doc':
            doc = attach.get('doc', {})
            doc_url = doc.get('url', '')
            if doc_url:
                try:
                    resp = requests.get(doc_url)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                        f.write(resp.content)
                        tmp = f.name
                    resume_txt = extract_text_from_file(tmp, 'pdf')
                    os.unlink(tmp)
                    if resume_txt:
                        if user_id not in user_states: user_states[user_id] = UserState()
                        user_states[user_id].resume_text = resume_txt
                        vk.messages.send(peer_id=user_id, message="Resume uploaded! Send HH.ru link", random_id=0)
                except Exception as e:
                    logger.error(f"File error: {e}")
    
    if text in ['/start', 'привет']:
        vk.messages.send(peer_id=user_id, message="Hi! Send resume + HH.ru link", random_id=0)
    elif 'hh.ru' in text:
        url = re.findall(r'https?://[^\s]+', raw_text)[0] if re.findall(r'https?://[^\s]+', raw_text) else None
        if url:
            vk.messages.send(peer_id=user_id, message="Loading vacancy...", random_id=0)
            vac_txt = parse_hh_vacancy(url)
            if user_id not in user_states: user_states[user_id] = UserState()
            user_states[user_id].vacancy_text = vac_txt
            if user_states[user_id].resume_text:
                vk.messages.send(peer_id=user_id, message="Adapting...", random_id=0)
                result = adapt_resume(user_states[user_id].resume_text, vac_txt)
                send_long_msg(vk, user_id, f"Done!\n\n{result}")
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                    pdf_path = f.name
                if create_resume_pdf(result, pdf_path):
                    send_pdf_to_user(vk, user_id, pdf_path, VK_TOKEN)
                try: os.unlink(pdf_path)
                except: pass
            else:
                vk.messages.send(peer_id=user_id, message="Vacancy saved! Send resume now", random_id=0)
    elif 'резюме:' in text:
        if user_id not in user_states: user_states[user_id] = UserState()
        user_states[user_id].resume_text = text.replace('резюме:', '').strip()
        vk.messages.send(peer_id=user_id, message="Resume saved! Send HH.ru link", random_id=0)
    else:
        vk.messages.send(peer_id=user_id, message="Send /start to begin", random_id=0)

def run_bot():
    VK_TOKEN = os.getenv("VK_TOKEN")
    GROUP_ID = int(os.getenv("GROUP_ID", 237022345))
    if not VK_TOKEN:
        logger.error("No VK_TOKEN!")
        return
    vk = vk_api.VkApi(token=VK_TOKEN).get_api()
    while True:
        try:
            logger.info("Connecting to VK...")
            longpoll = VkBotLongPoll(vk_api.VkApi(token=VK_TOKEN), GROUP_ID)
            logger.info(f"Bot started! Group: {GROUP_ID}")
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    try:
                        uid = event.obj.message['from_id']
                        txt = event.obj.message.get('text', '').strip()
                        att = event.obj.message.get('attachments', [])
                        handle_message(vk, uid, txt, att, VK_TOKEN)
                    except Exception as e:
                        logger.error(f"Msg error: {e}")
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    logger.info("Flask on port 5000")
    run_bot()
