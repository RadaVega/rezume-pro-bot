# config/settings.py
"""
Конфигурация приложения.
Версия: 5.0
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # VK
    VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", 0))
    VK_TOKEN = os.getenv("VK_TOKEN", "")

    # ✅ ADD THIS LINE (fixes the AttributeError):
    VK_CONFIRMATION_TOKEN = os.getenv("VK_CONFIRMATION_TOKEN", "ok")

    # GigaChat
    GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-prod")
    PORT = int(os.getenv("PORT", 5000))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Anti-hallucination
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 2))
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", 0.7))
