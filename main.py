#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 БОТ: Резюме.Про | ResumePro AI — Версия для Replit
🌐 Работает 24/7 на бесплатном тарифе
🤖 С интеграцией GigaChat для адаптации резюме
"""

import os
import time
import logging
from flask import Flask
from threading import Thread
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Flask для поддержания активности
app = Flask(__name__)


@app.route("/")
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
            <p>🕐 Время: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>👥 Группа: <a href="https://vk.com/rezume_pro" target="_blank">vk.com/rezume_pro</a></p>
        </div>

        <h2>📋 Команды бота:</h2>
        <ul>
            <li><code>/start</code> — начать работу</li>
            <li><code>/demo</code> — показать пример</li>
            <li><code>/help</code> — справка</li>
            <li><code>/adapt</code> — адаптировать резюме</li>
        </ul>

        <hr>
        <p><small>🎓 Проект Школы 21 | School 21 ID: Rubyalbe</small></p>
        <p><small>⚡ Работает на Replit + GigaChat AI</small></p>
    </body>
    </html>
    """


@app.route("/ping")
def ping():
    """Эндпоинт для UptimeRobot"""
    return "PONG! Bot is alive 🟢"


@app.route("/status")
def status():
    """Страница статуса"""
    return f"""
    <html>
    <head><title>Bot Status</title></head>
    <body>
        <h1>✅ Бот работает!</h1>
        <p>Группа ID: {os.getenv("GROUP_ID", "237022345")}</p>
        <p>Время: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
    </body>
    </html>
    """


def run_flask():
    """Запускает Flask сервер в отдельном потоке"""
    app.run(host="0.0.0.0", port=5000)


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
        result = chain.invoke({"resume": resume_text, "vacancy": vacancy_text})

        return result

    except Exception as e:
        logger.error(f"❌ Ошибка GigaChat: {e}")
        return "⚠️ Временно не могу адаптировать резюме. Попробуй позже."


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
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)

        logger.info(f"✅ Бот запущен! Группа: {GROUP_ID}")

        # Основной цикл Long Poll
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                user_id = event.obj.message["from_id"]
                text = event.obj.message["text"].lower().strip()

                logger.info(f"📨 Сообщение от {user_id}: '{text}'")

                # === ОБРАБОТКА КОМАНД ===

                # Команда /start
                if text in ["/start", "привет", "начать", "старт", "хай"]:
                    vk.messages.send(
                        peer_id=user_id,
                        message="""👋 Привет! Я бот Резюме.Про 🎯

Я помогу адаптировать твоё резюме под вакансию за 30 секунд с помощью ИИ.

📋 Как работать:
1. Отправь мне текст своего резюме
2. Добавь ссылку на вакансию (hh.ru)
3. Получи адаптированную версию + Match Score

💡 Команды:
• /help — справка
• /demo — показать пример
• /adapt — адаптировать резюме

Проект Школы 21 • Готов помочь! 🚀""",
                        random_id=0,
                    )
                    logger.info(f"✅ Отправлено приветствие")

                # Команда /help
                elif text in ["/help", "помощь", "справка", "хелп", "?"]:
                    vk.messages.send(
                        peer_id=user_id,
                        message="""💡 Команды бота:

/start — начать работу
/help — показать эту справку  
/demo — показать пример работы
/adapt — адаптировать резюме под вакансию

📝 Как использовать адаптацию:
1. Отправь /adapt
2. Пришли текст резюме и описание вакансии
3. Получи адаптированное резюме с Match Score!""",
                        random_id=0,
                    )
                    logger.info(f"✅ Отправлена справка")

                # Команда /demo
                elif text in ["/demo", "демо", "пример", "тест"]:
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
                        random_id=0,
                    )
                    logger.info(f"✅ Отправлено демо")

                # Команда /adapt
                elif (
                    text.startswith("/adapt")
                    or "адаптируй" in text
                    or "адаптировать" in text
                ):
                    logger.info(f"🔄 Запрос на адаптацию от {user_id}")

                    vk.messages.send(
                        peer_id=user_id,
                        message="""📝 Отправь мне данные для адаптации:

1️⃣ Текст твоего резюме (основные пункты)
2️⃣ Описание вакансии или ссылку на hh.ru

Пример формата:
«Резюме: Менеджер проектов, 2 года опыта, управление командой 5 человек
Вакансия: Требуется PM с опытом в Agile, знанием SQL»

Я адаптирую резюме за ~30 секунд! 🤖✨""",
                        random_id=0,
                    )

                # Обработка резюме + вакансия
                elif "резюме:" in text and ("ваканс" in text or "вакансия" in text):
                    try:
                        # Парсим текст
                        parts = text.lower().split("ваканс")
                        if len(parts) < 2:
                            parts = text.lower().split("вакансия")

                        resume = parts[0].replace("резюме:", "").strip()
                        vacancy = "вакансия" + parts[1] if len(parts) > 1 else ""

                        logger.info(f"🔄 Адаптирую резюме для {user_id}...")

                        # Отправляем "печатает..."
                        vk.messages.send(
                            peer_id=user_id,
                            message="🤖 Адаптирую резюме... Это займёт ~30 секунд ⏱️",
                            random_id=0,
                        )

                        # Вызываем GigaChat
                        result = adapt_resume_with_gigachat(resume, vacancy)

                        # Отправляем результат
                        vk.messages.send(peer_id=user_id, message=result, random_id=0)

                        logger.info(f"✅ Адаптация отправлена пользователю {user_id}")

                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки: {e}")
                        vk.messages.send(
                            peer_id=user_id,
                            message="⚠️ Произошла ошибка. Попробуй отправить данные ещё раз или напиши /help",
                            random_id=0,
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
                        random_id=0,
                    )

    except vk_api.exceptions.ApiError as e:
        logger.error(f"❌ VK API ошибка [{e.code}]: {e}")
        if e.code == 5:
            logger.error("💡 Токен невалиден — создай новый в настройках группы!")
        elif e.code == 15:
            logger.error(
                "💡 Не хватает прав — добавь 'Сообщения сообщества' при создании токена!"
            )
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
