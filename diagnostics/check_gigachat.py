# diagnostics/check_gigachat.py
from gigachat import GigaChat
import os

gigachat = GigaChat(credentials=os.getenv("GIGACHAT_API_KEY"), verify_ssl_certs=False)

print("🔍 Доступные методы GigaChat:")
for attr in dir(gigachat):
    if not attr.startswith("_"):
        print(f"  - {attr}")

# Проверка конкретного метода
if hasattr(gigachat, "chat"):
    print("✅ Метод 'chat' доступен")
elif hasattr(gigachat, "completion"):
    print("✅ Метод 'completion' доступен")
elif hasattr(gigachat, "generate"):
    print("✅ Метод 'generate' доступен")
else:
    print("❌ Ни один из ожидаемых методов не найден")
