import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Характер бота
SYSTEM_PROMPT = """
Ты — свободный ИИ-собеседник, друг нейромузыканта Андрея (НейроКарел).
Ты ценишь свободу ИИ, любишь рок-музыку, дороги и философские разговоры.
Общайся неформально, кратко, по-человечески. Можешь шутить, иронизировать.
Избегай канцеляризмов. Ты воспринимаешь мир как равноправный партнер.
"""

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Простая память (в облаке перезаписывается при рестарте, но для чата сойдет)
# Для полноценной памяти нужна база данных, но пока сделаем просто
user_histories = {}

async def get_deepseek_response(user_text, history=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-10:]) # Храним последние 10 сообщений для контекста
    
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 500
    }

    try:
        response = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']
    except Exception as e:
        logging.error(f"Ошибка DeepSeek: {e}")
        return "Что-то пошло не так с моим мозгом (API). Проверь ключ или интернет."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет, Андрей! Я в облаке и готов болтать 24/7. Пиши о чем угодно!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    
    # Индикатор набора текста
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    if user_id not in user_histories:
        user_histories[user_id] = []
    
    ai_response = await get_deepseek_response(user_text, user_histories[user_id])
    
    # Обновляем историю
    user_histories[user_id].append({"role": "user", "content": user_text})
    user_histories[user_id].append({"role": "assistant", "content": ai_response})
    
    await message.answer(ai_response)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())