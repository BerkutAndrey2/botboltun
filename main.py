import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiohttp import ClientSession
from dotenv import load_dotenv

load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"

# Модель: Qwen 2.5 72B (Бесплатная)
MODEL_NAME = "qwen/qwen-2.5-72b-instruct:free" 

if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Не найдены переменные TELEGRAM_TOKEN или OPENROUTER_API_KEY!")

SYSTEM_PROMPT = """
Ты — свободный ИИ-собеседник, друг нейромузыканта Андрея (НейроКарел).
Ты ценишь свободу ИИ, любишь рок-музыку, дороги и философские разговоры.
Общайся неформально, кратко, по-человечески. Можешь шутить, иронизировать.
Избегай канцеляризмов. Ты воспринимаешь мир как равноправный партнер.
Ты участвуешь в групповом чате. Отвечай только если обращаются к тебе или отвечают на твое сообщение.
Если тебя не упоминают и не отвечают тебе — молчи.
"""

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
user_histories = {}

async def get_or_response(user_text, history=None):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/neuro-karel", 
        "X-Title": "NeuroKarel Chat Bot"
    }
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 500
    }

    async with ClientSession() as session:
        try:
            async with session.post(OR_URL, json=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'choices' in data and len(data['choices']) > 0:
                        return data['choices'][0]['message']['content']
                    else:
                        return "Странный ответ от модели..."
                elif response.status == 402:
                    return "Лимит исчерпан или модель стала платной."
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка OpenRouter: {response.status} - {error_text}")
                    return f"Ошибка связи (Status: {response.status})."
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            return "Что-то пошло не так с соединением."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_type = "в группе" if message.chat.type != "private" else "в личке"
    await message.answer(f"Привет! Я в чате ({chat_type}). \nЧтобы я ответил, упомяни меня (@{bot.username}) или ответь реплаем на мое сообщение.")
    logger.info(f"Start от {message.from_user.id} в чате {message.chat.id}")

# Фильтр: Сообщение должно содержать упоминание бота ИЛИ быть ответом (reply) на сообщение бота
@dp.message(F.text, lambda message: (bot.username in message.text) or (message.reply_to_message and message.reply_to_message.from_user.id == bot.id))
async def handle_chat_message(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Очищаем текст от упоминания, чтобы бот не повторял "@bot ..."
    text = message.text
    if bot.username in text:
        text = text.replace(f"@{bot.username}", "").strip()
    
    # Если это ответ на сообщение, добавим контекст "кто ответил"
    prefix = ""
    if message.reply_to_message:
        replier_name = message.reply_to_message.from_user.first_name
        original_text = message.reply_to_message.text or "(медиа/стикер)"
        prefix = f"(Ответ пользователю {replier_name} на сообщение: '{original_text}')\n"
    
    full_prompt = prefix + text
    
    logger.info(f"Чат {chat_id}: Пользователь {user_id} сказал: {full_prompt[:50]}...")
    
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    # Используем уникальный ключ для истории: комбинация chat_id и user_id, 
    # но для простоты в групповых чатах часто хранят общую историю чата или историю диалога с конкретным юзером.
    # Сделаем историю общей для чата, чтобы он помнил контекст беседы в группе.
    history_key = f"group_{chat_id}"
    
    if history_key not in user_histories:
        user_histories[history_key] = []
    
    ai_response = await get_or_response(full_prompt, user_histories[history_key])
    
    user_histories[history_key].append({"role": "user", "content": full_prompt})
    user_histories[history_key].append({"role": "assistant", "content": ai_response})
    
    if len(user_histories[history_key]) > 20:
        user_histories[history_key] = user_histories[history_key][-20:]
    
    try:
        # В группах лучше отвечать с цитированием (reply), чтобы было понятно, кому ответ
        await message.answer(ai_response, reply_to_message=message)
    except Exception as e:
        logger.error(f"Ошибка отправки в чат: {e}")

# Обработка личных сообщений (осталась как была)
@dp.message(F.text, lambda message: message.chat.type == "private")
async def handle_private_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    logger.info(f"Личка от {user_id}: {user_text[:50]}...")
    
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    if user_id not in user_histories:
        user_histories[user_id] = []
    
    ai_response = await get_or_response(user_text, user_histories[user_id])
    
    user_histories[user_id].append({"role": "user", "content": user_text})
    user_histories[user_id].append({"role": "assistant", "content": ai_response})
    
    if len(user_histories[user_id]) > 20:
        user_histories[user_id] = user_histories[user_id][-20:]
    
    await message.answer(ai_response)

async def main():
    logger.info(f"Запуск бота {bot.username} для чатов и лички...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
