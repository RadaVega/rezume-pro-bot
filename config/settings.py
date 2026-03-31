# config/settings.py
"""
Конфигурация приложения.
"""

import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()


class Config:
    # VK - Обязательно должно быть числом (int), не строкой!
    VK_GROUP_ID = os.getenv("VK_GROUP_ID")

    # Проверка на наличие обязательных переменных
    if not VK_GROUP_ID:
        raise ValueError(
            "❌ КРИТИЧЕСКАЯ ОШИБКА: VK_GROUP_ID не настроен!\n"
            "Добавьте переменную в Replit Secrets или .env файл.\n"
            "Формат: VK_GROUP_ID=123456789 (без @club, без пробелов)"
        )

    # Преобразуем в int (VK API требует число, не строку!)
    try:
        VK_GROUP_ID = int(VK_GROUP_ID)
    except ValueError:
        raise ValueError(
            f"❌ VK_GROUP_ID должен быть числом, а не '{VK_GROUP_ID}'\n"
            "Пример правильного формата: VK_GROUP_ID=123456789"
        )

    # GigaChat
    GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY")
    if not GIGACHAT_API_KEY:
        raise ValueError("❌ GIGACHAT_API_KEY не настроен!")

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-prod")
    PORT = int(os.getenv("PORT", 5000))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Anti-hallucination
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 2))
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", 0.7))
