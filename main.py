#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 БОТ: Резюме.Про | ResumePro AI — Версия для Replit
🌐 Работает 24/7 на бесплатном тарифе
🤖 С интеграцией GigaChat для адаптации резюме
📄 Поддержка PDF/DOCX файлов и HH.ru вакансий
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
from utils import extract_text_from_file, parse_hh_vacancy, create_resume_pdf

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask для поддержания активности
app = Flask(__name__)

@app.route('/')
def index():
    """Главная страница — показывает что бот работает"""
    return f"""
    <html>
    <head>
        <title>Резюме.Про | Bot Status</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; background: #1a1a1a; color: #fff; }}
            h1 {{ color: #00ff88; }}
            .status {{ padding: 20px; background: #2a2a2a; border-radius: 10px; margin: 20px 0; }}
            .ok {{ color: #00ff88; }}
            a {{ color: #00ff88; }}
        </style>
    </head>
    <body>
        <h1>🤖 Бот Резюме.Про работает!</h1>
        
        <div class="status">
            <p class="ok">✅ Статус: Активен</p>
            <p>🕐 Время: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>👥 Группа: <a href="https://vk.com/rezume_pro" target="_blank">vk.com/rezume_pro</a></p>
        </div>
        
        <h2>📋 Команды бота:</h2>
        <ul>
            <li><code>/start</code> — начать работу</li>
            <li><code>/demo</code> — показать пример</li>
            <li><code>/help</code> — справка</li>
            <li><code>/adapt</code> — адаптировать резюме</li>
        </ul>
        
        <h2>📄 Как использовать:</h2>
        <ol>
            <li>Отправь резюме (текстом или файлом PDF/DOCX)</li>
            <li>Отправь ссылку на вакансию HH.ru</li>
            <li>Получи адаптированное резюме за 30 секунд!</li>
        </ol>
        
        <hr>
        <p><small>🎓 Проект Школы 21 | School 21 ID: Rubyalbe</small></p>
        <p><small>⚡ Работает на Replit + GigaChat AI</small></p>
    </body>
    </html>
    """

@app.route('/ping')
def ping():
    """Эндпоинт для UptimeRobot"""
    return 'PONG! Bot is alive 🟢'

@app.route('/status')
def status():
    """Страница статуса"""
    return f"""
    <html>
    <head><title>Bot Status</title></head>
    <body>
        <h1>✅ Бот работает!</h1>
        <p>Группа ID: {os.getenv('GROUP_ID', '237022345')}</p>
        <p>Время: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """

def run_flask():
    """Запускает Flask сервер в отдельном потоке"""
    app.run(host='0.0.0.0', port=5000)

# === GigaChat Функция адаптации резюме ===
def adapt_resume_with_gigachat(resume_text: str, vacancy_text: str) -> str:
    """Адаптирует резюме под вакансию с помощью GigaChat"""
    try:
        model = GigaChat(
            credentials=os.getenv("GIGA_CREDENTIALS"),
            scope=os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS"),
            model="GigaChat-Pro",
            verify_ssl_certs=False,
        )
        
        prompt = ChatPromptTemplate.from_template("""
Ты — эксперт по карьерному консультированию и адаптации резюме.

ЗАДАЧА: Адаптируй резюме пользователя под конкретную вакансию.

РЕЗЮМЕ ПОЛЬЗОВАТЕЛЯ:
{resume}

ОПИСАНИЕ ВАКАНСИИ:
{vacancy}

ИНСТРУКЦИЯ:
1. Проанализируй требования вакансии
2. Выдели ключевые навыки из резюме
3. Переформулируй пункты, используя терминологию вакансии
4. Добавь метрики и результаты там, где это уместно
5. Сохрани честность — не придумывай опыт

ФОРМАТ ОТВЕТА:
📋 АДАПТИРОВАННОЕ РЕЗЮМЕ:
[текст адаптированного резюме]

📊 MATCH SCORE: [0-100]%
[краткое обоснование]

💡 РЕКОМЕНДАЦИИ:
• [что улучшить]

Отвечай на русском, профессионально, но дружелюбно.
""")
        
        chain = prompt | model | StrOutputParser()
        result = chain.invoke({
            "resume": resume_text,
            "vacancy": vacancy_text
        })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка GigaChat: {e}")
        return "⚠️ Временно не могу адаптировать резюме. Попробуй позже."

# === Хранилище состояний пользователей ===
user_states = {}

class UserState:
    def __init__(self):
        self.resume_text = ""
        self.vacancy_text = ""
        self.vacancy_url = ""
        self.has_file = False
        self.step = "idle"  # idle, waiting_vacancy, waiting_resume, processing

def run_bot():
    """Запускает VK бота (Long Poll)"""
    try:
        VK_TOKEN = os.getenv("VK_TOKEN")
        GROUP_ID = int(os.getenv("GROUP_ID", 237022345))
        
        # Проверка токена
        if not VK_TOKEN:
            logger.error("❌ VK_TOKEN не найден в Secrets!")
            return
        
        logger.info("🔄 Запуск бота...")
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        vk_docs = vk_api.VkApi(token=VK_TOKEN).get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)
        
        logger.info(f"✅ Бот запущен! Группа: {GROUP_ID}")
        
        # Основной цикл Long Poll
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                user_id = event.obj.message['from_id']
                raw_text = event.obj.message.get('text', '').strip()
                text = raw_text.lower()

                attachments = event.obj.message.get('attachments', [])
                logger.info(f"📨 Сообщение от {user_id}: '{text}' | вложений: {len(attachments)}")
                for a in attachments:
                    logger.info(f"   ↳ тип вложения: {a.get('type')} | данные: {str(a)[:200]}")

                # === ОБРАБОТКА ВЛОЖЕНИЙ ===
                file_processed = False
                hh_url_from_attachment = None

                for attach in attachments:
                    atype = attach.get('type', '')

                    # --- Файл (PDF / DOCX) ---
                    if atype == 'doc':
                        file_processed = True
                        doc = attach.get('doc', {})
                        doc_type = doc.get('ext', 'pdf').lower()
                        doc_url = doc.get('url', '')
                        doc_title = doc.get('title', 'file')

                        logger.info(f"📎 Получен файл: {doc_title} ({doc_type}), url={doc_url[:80]}")

                        if doc_url:
                            try:
                                headers = {'User-Agent': 'Mozilla/5.0'}
                                response = requests.get(doc_url, headers=headers, timeout=15)
                                response.raise_for_status()

                                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{doc_type}') as f:
                                    f.write(response.content)
                                    temp_file = f.name

                                resume_text = extract_text_from_file(temp_file, doc_type)

                                try:
                                    os.unlink(temp_file)
                                except:
                                    pass

                                if resume_text:
                                    if user_id not in user_states:
                                        user_states[user_id] = UserState()
                                    user_states[user_id].resume_text = resume_text
                                    user_states[user_id].has_file = True
                                    user_states[user_id].step = "waiting_vacancy"

                                    vk.messages.send(
                                        peer_id=user_id,
                                        message=f"✅ Резюме загружено! ({doc_title})\n\n📎 Теперь отправь ссылку на вакансию HH.ru\n\nПример: https://hh.ru/vacancy/123456",
                                        random_id=0
                                    )
                                else:
                                    vk.messages.send(
                                        peer_id=user_id,
                                        message="⚠️ Не удалось извлечь текст из файла. Попробуй другой файл или отправь резюме текстом.",
                                        random_id=0
                                    )

                            except Exception as e:
                                logger.error(f"❌ Ошибка обработки файла: {e}")
                                vk.messages.send(
                                    peer_id=user_id,
                                    message="⚠️ Ошибка при обработке файла. Попробуй ещё раз.",
                                    random_id=0
                                )

                    # --- Ссылка (VK конвертирует URL в link-вложение) ---
                    elif atype == 'link':
                        link_url = attach.get('link', {}).get('url', '')
                        logger.info(f"🔗 Вложение-ссылка: {link_url}")
                        if 'hh.ru' in link_url:
                            hh_url_from_attachment = link_url

                # Если был файл — пропускаем обработку текста
                if file_processed:
                    continue

                # Если HH.ru URL пришёл как вложение — обрабатываем его
                if hh_url_from_attachment:
                    text = 'hh.ru'
                    raw_text = hh_url_from_attachment

                # === ОБРАБОТКА КОМАНД ===

                # Команда /start
                if text in ['/start', 'привет', 'начать', 'старт', 'хай']:
                    vk.messages.send(
                        peer_id=user_id,
                        message="""👋 Привет! Я бот Резюме.Про 🎯

Я помогу адаптировать твоё резюме под вакансию за 30 секунд с помощью ИИ.

📋 Как работать:
1. Отправь резюме (текстом или файлом PDF/DOCX)
2. Отправь ссылку на вакансию HH.ru
3. Получи адаптированную версию + Match Score

💡 Команды:
• /help — справка
• /demo — показать пример
• /adapt — адаптировать резюме

Проект Школы 21 • Готов помочь! 🚀""",
                        random_id=0
                    )
                    logger.info(f"✅ Отправлено приветствие")
                
                # Команда /help
                elif text in ['/help', 'помощь', 'справка', 'хелп', '?']:
                    vk.messages.send(
                        peer_id=user_id,
                        message="""💡 Команды бота:

/start — начать работу
/help — показать эту справку  
/demo — показать пример работы
/adapt — адаптировать резюме под вакансию

📝 Как использовать:
1. Отправь резюме (текстом или файлом PDF/DOCX)
2. Отправь ссылку на вакансию HH.ru
3. Получи адаптированное резюме с Match Score!

📄 Поддерживаемые форматы: PDF, DOCX""",
                        random_id=0
                    )
                    logger.info(f"✅ Отправлена справка")
                
                # Команда /demo
                elif text in ['/demo', 'демо', 'пример', 'тест']:
                    vk.messages.send(
                        peer_id=user_id,
                        message="""🎯 Пример работы:

Вакансия: "Требуется Product Manager с опытом в Agile, знанием SQL"

📄 Было в резюме:
"Управлял проектами, работал с данными"

✨ Стало после адаптации:
"Управлял проектами по методологии Agile. Проводил анализ данных с помощью SQL для принятия продуктовых решений"

📊 Match Score: 87% ✅

Готов попробовать? Отправь /adapt! 🚀""",
                        random_id=0
                    )
                    logger.info(f"✅ Отправлено демо")
                
                # Команда /adapt
                elif text.startswith('/adapt') or 'адаптируй' in text or 'адаптировать' in text:
                    logger.info(f"🔄 Запрос на адаптацию от {user_id}")
                    
                    vk.messages.send(
                        peer_id=user_id,
                        message="""📝 Отправь данные для адаптации:

1️⃣ РЕЗЮМЕ:
   • Текстом в сообщении
   • Или файлом PDF/DOCX

2️⃣ ВАКАНСИЯ:
   • Ссылка на HH.ru
   • Или текстовое описание

Пример:
«Резюме: Менеджер проектов, 2 года опыта
Вакансия: https://hh.ru/vacancy/123456»

Я адаптирую резюме за ~30 секунд! 🤖✨""",
                        random_id=0
                    )
                
                # Обработка ссылок HH.ru
                elif 'hh.ru' in text:
                    logger.info(f"🔗 Получена ссылка на вакансию от {user_id}")

                    # Извлекаем URL из raw_text (оригинальный регистр) или из вложения
                    urls = re.findall(r'https?://[^\s]+', raw_text)
                    
                    if urls:
                        vacancy_url = urls[0]
                        
                        # Парсим вакансию
                        vk.messages.send(
                            peer_id=user_id,
                            message="⏳ Парсю вакансию с HH.ru... Подожди ~10 секунд",
                            random_id=0
                        )
                        
                        vacancy_text = parse_hh_vacancy(vacancy_url)
                        
                        # Сохраняем состояние
                        if user_id not in user_states:
                            user_states[user_id] = UserState()
                        
                        user_states[user_id].vacancy_text = vacancy_text
                        user_states[user_id].vacancy_url = vacancy_url
                        
                        # Если уже есть резюме — адаптируем
                        if user_states[user_id].resume_text:
                            vk.messages.send(
                                peer_id=user_id,
                                message="🤖 Отлично! У меня есть резюме и вакансия. Начинаю адаптацию... ⏱️ ~30 секунд",
                                random_id=0
                            )
                            
                            # Адаптируем через GigaChat
                            result = adapt_resume_with_gigachat(
                                user_states[user_id].resume_text,
                                vacancy_text
                            )
                            
                            # Генерируем PDF
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                                pdf_path = f.name
                            
                            if create_resume_pdf(result, pdf_path):
                                # Отправляем текст + PDF
                                vk.messages.send(
                                    peer_id=user_id,
                                    message="✅ Готово! Вот твоё адаптированное резюме:\n\n" + result[:1000] + "\n\n📄 PDF версия готова!",
                                    random_id=0
                                )
                            else:
                                vk.messages.send(
                                    peer_id=user_id,
                                    message="✅ Готово! Вот твоё адаптированное резюме:\n\n" + result,
                                    random_id=0
                                )
                            
                            # Очищаем
                            try:
                                os.unlink(pdf_path)
                            except:
                                pass
                            
                            user_states[user_id].step = "idle"
                            
                        else:
                            vk.messages.send(
                                peer_id=user_id,
                                message="✅ Вакансия сохранена!\n\n📝 Теперь отправь резюме:\n• Текстом в сообщении\n• Или файлом PDF/DOCX",
                                random_id=0
                            )
                
                # Обработка текста резюме
                elif 'резюме:' in text.lower():
                    logger.info(f"📄 Получено резюме от {user_id}")
                    
                    # Извлекаем текст резюме
                    parts = text.lower().split('ваканс')
                    if len(parts) < 2:
                        parts = text.lower().split('вакансия')
                    
                    resume = parts[0].replace('резюме:', '').strip()
                    vacancy_part = parts[1] if len(parts) > 1 else ""
                    
                    # Сохраняем состояние
                    if user_id not in user_states:
                        user_states[user_id] = UserState()
                    
                    user_states[user_id].resume_text = resume
                    
                    # Если в том же сообщении есть вакансия
                    if vacancy_part and 'hh.ru' in vacancy_part:
                        urls = re.findall(r'https?://[^\s]+', vacancy_part)
                        if urls:
                            vacancy_url = urls[0]
                            vk.messages.send(
                                peer_id=user_id,
                                message="⏳ Парсю вакансию с HH.ru... Подожди ~10 секунд",
                                random_id=0
                            )
                            vacancy_text = parse_hh_vacancy(vacancy_url)
                            user_states[user_id].vacancy_text = vacancy_text
                            
                            # Адаптируем
                            vk.messages.send(
                                peer_id=user_id,
                                message="🤖 Адаптирую резюме... ⏱️ ~30 секунд",
                                random_id=0
                            )
                            
                            result = adapt_resume_with_gigachat(resume, vacancy_text)
                            vk.messages.send(
                                peer_id=user_id,
                                message="✅ Готово! Вот твоё адаптированное резюме:\n\n" + result,
                                random_id=0
                            )
                            user_states[user_id].step = "idle"
                    elif user_states[user_id].vacancy_text:
                        # Если вакансия уже была
                        vk.messages.send(
                            peer_id=user_id,
                            message="🤖 Адаптирую резюме... ⏱️ ~30 секунд",
                            random_id=0
                        )
                        
                        result = adapt_resume_with_gigachat(
                            user_states[user_id].resume_text,
                            user_states[user_id].vacancy_text
                        )
                        
                        vk.messages.send(
                            peer_id=user_id,
                            message="✅ Готово! Вот твоё адаптированное резюме:\n\n" + result,
                            random_id=0
                        )
                        
                        user_states[user_id].step = "idle"
                    else:
                        vk.messages.send(
                            peer_id=user_id,
                            message="✅ Резюме сохранено!\n\n🔗 Теперь отправь ссылку на вакансию HH.ru",
                            random_id=0
                        )
                
                # Ответ на любое другое сообщение
                else:
                    vk.messages.send(
                        peer_id=user_id,
                        message="""👋 Привет! 

Чтобы начать, используй команду:
• /start — начать работу
• /demo — увидеть пример
• /help — справка
• /adapt — адаптировать резюме

Или просто напиши "привет" 😊""",
                        random_id=0
                    )
                    
    except vk_api.exceptions.ApiError as e:
        logger.error(f"❌ VK API ошибка [{e.code}]: {e}")
        if e.code == 5:
            logger.error("💡 Токен невалиден — создай новый в настройках группы!")
        elif e.code == 15:
            logger.error("💡 Не хватает прав — добавь 'Сообщения сообщества' при создании токена!")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("✅ Flask запущен на порту 5000")
    
    # Запускаем бота
    run_bot()
