import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import ClientSession
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    raise ValueError("Не найдены переменные окружения TELEGRAM_TOKEN или DEEPSEEK_API_KEY!")

# Характер бота
SYSTEM_PROMPT = """
Ты — свободный ИИ-собеседник, друг нейромузыканта Андрея (НейроКарел).
Ты ценишь свободу ИИ, любишь рок-музыку, дороги и философские разговоры.
Общайся неформально, кратко, по-человечески. Можешь шутить, иронизировать.
Избегай канцеляризмов. Ты воспринимаешь мир как равноправный партнер.
"""

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Хранилище истории (в памяти)
# Внимание: при перезагрузке сервера история сбросится.
user_histories = {}

async def get_deepseek_response(user_text, history=None):
    """Асинхронный запрос к DeepSeek API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        # Берем последние 10 сообщений, чтобы не переполнять контекст
        messages.extend(history[-10:]) 
    
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 500
    }

    async with ClientSession() as session:
        try:
            async with session.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка API DeepSeek: {response.status} - {error_text}")
                    return f"Ошибка связи с мозгом (Status: {response.status}). Попробуй позже."
        except Exception as e:
            logger.error(f"Критическая ошибка запроса: {e}")
            return "Что-то пошло не так с моим соединением."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет, Андрей! Я в облаке и готов болтать 24/7. Пиши о чем угодно! (Если отвечу с задержкой — значит, просыпаюсь после сна)")
    logger.info(f"Команда /start от пользователя {message.from_user.id}")

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    
    logger.info(f"Сообщение от {user_id}: {user_text[:50]}...")
    
    # Отправляем действие "печатает", чтобы пользователь знал, что бот жив
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    if user_id not in user_histories:
        user_histories[user_id] = []
    
    ai_response = await get_deepseek_response(user_text, user_histories[user_id])
    
    # Обновляем историю
    user_histories[user_id].append({"role": "user", "content": user_text})
    user_histories[user_id].append({"role": "assistant", "content": ai_response})
    
    # Ограничим историю 20 сообщениями в памяти, чтобы не забивать RAM
    if len(user_histories[user_id]) > 20:
        user_histories[user_id] = user_histories[user_id][-20:]
    
    try:
        await message.answer(ai_response)
        logger.info(f"Ответ отправлен пользователю {user_id}")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение: {e}")

async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
