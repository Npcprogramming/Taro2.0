import os
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем переменные из .env
load_dotenv()

# Подключаемся к Langdock API
client = OpenAI(
    base_url="https://api.langdock.com/openai/eu/v1",
    api_key=os.getenv("LANGDOCK_API_KEY")  # ✅ Имя переменной такое же как в .env
)

# Основная функция получения AI-совета
async def get_ai_description(card, card_info, zodiac_sign, is_reversed):
    base_description = card_info.get('reversed_description') if is_reversed else card_info.get('description')

    messages = [
        {
            "role": "system",
            "content": "Ты профессиональный таролог. Дай подробный и понятный совет по значению карты, в контексте повседневной жизни. Прогнозирование по знак зодиака и позициям планет. Можно в тоне Подружки и Стиля ТароМаро. Больше смайлов."
        },
        {
            "role": "user",
            "content": f"Карта: {card}\nЗначение: {base_description}\nЗнак зодиака: {zodiac_sign or 'неизвестен'}"
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o",  # ✅ Поддерживаемая модель от Langdock
        messages=messages
    )

    return response.choices[0].message.content.strip()
