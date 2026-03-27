#!/usr/bin/env python3
import os
from langchain_gigachat.chat_models import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

print("🔍 Проверка переменных...")
print(f"GIGA_CREDENTIALS: {'✅' if os.getenv('GIGA_CREDENTIALS') else '❌'}")
print(f"GIGA_SCOPE: {os.getenv('GIGA_SCOPE', '❌')}")

try:
    print("\n🔄 Инициализация GigaChat...")

    model = GigaChat(
        credentials=os.getenv("GIGA_CREDENTIALS"),
        scope=os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS"),
        model="GigaChat-Pro",
        verify_ssl_certs=False,
    )

    print("✅ Модель инициализирована!")

    print("\n🤖 Тестовый запрос...")
    prompt = ChatPromptTemplate.from_template(
        "Что такое адаптация резюме? Ответь в 1 предложении."
    )
    chain = prompt | model | StrOutputParser()
    result = chain.invoke({})

    print(f"\n✅ Ответ GigaChat: {result}")
    print("\n🎉 ВСЁ РАБОТАЕТ!")

except Exception as e:
    print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
