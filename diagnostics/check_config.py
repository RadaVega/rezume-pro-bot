# diagnostics/check_config.py
"""
Проверка конфигурации перед запуском бота.
"""

import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 Проверка конфигурации...\n")

# Проверка переменных
variables = {
    "VK_TOKEN": os.getenv("VK_TOKEN"),
    "VK_GROUP_ID": os.getenv("VK_GROUP_ID"),
    "GIGACHAT_API_KEY": os.getenv("GIGACHAT_API_KEY"),
    "PORT": os.getenv("PORT"),
}

all_ok = True

for key, value in variables.items():
    if value:
        # Скрываем чувствительные данные
        if "TOKEN" in key or "KEY" in key:
            display_value = f"{value[:10]}...{value[-10:]}"
        else:
            display_value = value
        print(f"✅ {key}: {display_value}")
    else:
        print(f"❌ {key}: НЕ НАСТРОЕН")
        all_ok = False

# Проверка формата VK_GROUP_ID
if variables["VK_GROUP_ID"]:
    try:
        group_id = int(variables["VK_GROUP_ID"])
        print(f"✅ VK_GROUP_ID формат: корректный (число: {group_id})")
    except ValueError:
        print(
            f"❌ VK_GROUP_ID формат: должен быть числом, а не '{variables['VK_GROUP_ID']}'"
        )
        all_ok = False

print("\n" + "=" * 50)
if all_ok:
    print("✅ Все переменные настроены корректно!")
    print("🚀 Можно запускать бота: ./restart.sh")
else:
    print("❌ Есть ошибки в конфигурации!")
    print("🔧 Добавьте недостающие переменные в Replit Secrets")
