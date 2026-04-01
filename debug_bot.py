#!/usr/bin/env python3
"""Диагностика VK бота."""

import os
import sys

print("=" * 60)
print("🔍 ДИАГНОСТИКА RESUMEPRO AI BOT")
print("=" * 60)

# 1. Проверка переменных окружения
print("\n1️⃣  Переменные окружения:")
vars_to_check = [
    "VK_TOKEN",
    "VK_GROUP_ID",
    "GIGACHAT_API_KEY",
    "VK_CONFIRMATION_TOKEN",
    "PORT",
]
for var in vars_to_check:
    value = os.getenv(var)
    status = "✅" if value else "❌"
    display_value = value[:20] + "..." if value and len(value) > 20 else value
    print(f"   {status} {var}: {display_value or 'NOT SET'}")

# 2. Проверка импортов
print("\n2️⃣  Проверка импортов:")
try:
    from flask import Flask

    print("   ✅ Flask")
except ImportError as e:
    print(f"   ❌ Flask: {e}")

try:
    from vk_api import VkApi

    print("   ✅ vk_api")
except ImportError as e:
    print(f"   ❌ vk_api: {e}")

try:
    from gigachat import GigaChat

    print("   ✅ gigachat")
except ImportError as e:
    print(f"   ❌ gigachat: {e}")

# 3. Проверка подключения к VK
print("\n3️⃣  Подключение к VK:")
try:
    vk_token = os.getenv("VK_TOKEN")
    if vk_token:
        vk_session = VkApi(token=vk_token)
        vk_session.get_api()
        print("   ✅ VK API подключён")
    else:
        print("   ❌ VK_TOKEN не установлен")
except Exception as e:
    print(f"   ❌ VK API ошибка: {e}")

# 4. Проверка подключения к GigaChat
print("\n4️⃣  Подключение к GigaChat:")
try:
    gc_key = os.getenv("GIGACHAT_API_KEY")
    if gc_key:
        gigachat = GigaChat(credentials=gc_key, verify_ssl_certs=False)
        print("   ✅ GigaChat подключён")
    else:
        print("   ❌ GIGACHAT_API_KEY не установлен")
except Exception as e:
    print(f"   ❌ GigaChat ошибка: {e}")

# 5. Проверка конфигурации
print("\n5️⃣  Конфигурация:")
try:
    from config.settings import Config

    print(f"   ✅ VK_GROUP_ID: {Config.VK_GROUP_ID}")
    print(f"   ✅ PORT: {Config.PORT}")
    print(f"   ✅ MAX_RETRIES: {Config.MAX_RETRIES}")
except Exception as e:
    print(f"   ❌ Config ошибка: {e}")

print("\n" + "=" * 60)
print("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 60)
