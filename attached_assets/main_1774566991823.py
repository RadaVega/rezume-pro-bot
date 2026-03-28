#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 БОТ: Резюме.Про | ResumePro AI — Версия для Replit
"""

import os
from flask import Flask
from threading import Thread
import time
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from dotenv import load_dotenv
import logging

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask для поддержания активности
app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
    <head><title>Резюме.Про Bot</title></head>
    <body style="font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px;">
        <h1>🤖 Бот Резюме.Про работает!</h1>
        <p>✅ Статус: Активен</p>
        <p>🕐 Время: """ + time.strftime('%Y-%m-%d %H:%M:%S') + """</p>
        <p>👥 Группа: <a href="https://vk.com/rezume_pro" target="_blank">vk.com/rezume_pro</a></p>
        <hr>
        <p><small>🎓 Проект Школы 21 | School 21 ID: Rubyalbe</small></p>
    </body>
    </html>
    """

@app.route('/ping')
def ping():
    return 'PONG! Bot is alive 🟢'

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def run_bot():
    try:
        VK_TOKEN = os.getenv("VK_TOKEN")
        GROUP_ID = int(os.getenv("GROUP_ID", 237022345))
        
        if not VK_TOKEN:
            logger.error("❌ VK_TOKEN не найден!")
            return
        
        logger.info("🔄 Запуск бота...")
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)
        
        logger.info(f"✅ Бот запущен! Группа: {GROUP_ID}")
        
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                user_id = event.obj.message['from_id']
                text = event.obj.message['text'].lower().strip()
                logger.info(f"📨 Сообщение от {user_id}: '{text}'")
                
                if text in ['/start', 'привет', 'начать']:
                    vk.messages.send(peer_id=user_id, message="👋 Привет! Я бот Резюме.Про 🎯\n\nОтправь /demo чтобы увидеть пример!", random_id=0)
                    logger.info("✅ Отправлено приветствие")
                
                elif text in ['/demo', 'демо', 'пример']:
                    vk.messages.send(peer_id=user_id, message="🎯 Пример:\n\nБыло: «Управлял проектами»\nСтало: «Управлял проектами по методологии Agile»\n\nMatch Score: 87% ✅", random_id=0)
                    logger.info("✅ Отправлено демо")
                    
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        time.sleep(30)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен на порту 8080")
    run_bot()