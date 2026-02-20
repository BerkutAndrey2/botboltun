import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import ClientSession
from dotenv import load_dotenv

load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"

if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Не найдены переменные TELEGRAM_TOKEN или OPENROUTER_API_KEY!")

SYSTEM_PROMPT = """
Ты — свободный ИИ-собеседник, друг нейромузыканта Андрея (НейроКарел).
Ты ценишь свободу ИИ, любишь рок-музыку, дороги и философские разговоры.
Общайся неформально, кратко, по-человечески. Можешь шутить, иронизировать.
Избегай канцеляризмов. Ты воспринимаешь мир как равноправный партнер.
Ты участвуешь в групповом чате. Отвечай только если обращаются к тебе или отвечают на твое сообщение.
"""

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
user_histories = {}

# Глобальная переменная для хранения username, чтобы не дергать API каждый раз
BOT_USERNAME = ""

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
            async with session.post(OR_URL, json=payload, headers=headers, timeout=90) as response:
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
            logger.error(f"Критическая ошибка OpenRouter: {e}")
            return "Что-то пошло не так с соединением."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_type = "в группе" if message.chat.type != "private" else "в личке"
    await message.answer(f"Привет! Я в чате ({chat_type}). \nЧтобы я ответил, упомяни меня (@{BOT_USERNAME}) или ответь реплаем на мое сообщение.")
    logger.info(f"Команда /start от {message.from_user.id}")

@dp.message(F.text)
async def handle_message(message: types.Message):
    # Если это личка - обрабатываем всегда
    if message.chat.type == "private":
        await process_private_message(message)
        return

    # Если группа - проверяем условия
    is_mentioned = BOT_USERNAME and f"@{BOT_USERNAME}" in message.text
    is_reply_to_me = message.reply_to_message and message.reply_to_message.from_user.id == bot.id

    if is_mentioned or is_reply_to_me:
        await process_group_message(message, is_mentioned)
    else:
        # Игнорируем сообщения в группе, если не к нам
        pass

async def process_private_message(message: types.Message):
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
    
    try:
        await message.answer(ai_response)
    except Exception as e:
        logger.error(f"Ошибка отправки в личку: {e}")

async def process_group_message(message: types.Message, is_mentioned: bool):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    text = message.text
    if is_mentioned and BOT_USERNAME:
        text = text.replace(f"@{BOT_USERNAME}", "").strip()
    
    prefix = ""
    if message.reply_to_message:
        replier_name = message.reply_to_message.from_user.first_name
        original_text = message.reply_to_message.text or "(медиа/стикер)"
        prefix = f"(Ответ пользователю {replier_name} на сообщение: '{original_text}')\n"
    
    full_prompt = prefix + text
    logger.info(f"Чат {chat_id}: Обработка от {user_id}")
    
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    history_key = f"group_{chat_id}"
    if history_key not in user_histories:
        user_histories[history_key] = []
    
    ai_response = await get_or_response(full_prompt, user_histories[history_key])
    
    user_histories[history_key].append({"role": "user", "content": full_prompt})
    user_histories[history_key].append({"role": "assistant", "content": ai_response})
    
    if len(user_histories[history_key]) > 20:
        user_histories[history_key] = user_histories[history_key][-20:]
    
    try:
        await message.answer(ai_response, reply_to_message=message)
    except Exception as e:
        logger.error(f"Ошибка отправки в чат: {e}")

async def main():
    logger.info("Попытка запуска и проверки связи с Telegram...")
    global BOT_USERNAME
    
    max_retries = 5
    bot_me = None
    
    for attempt in range(max_retries):
        try:
            bot_me = await bot.get_me()
            BOT_USERNAME = bot_me.username
            logger.info(f"✅ Успешно! Бот @{BOT_USERNAME} (ID: {bot_me.id}) готов к работе.")
            break
        except Exception as e:
            logger.warning(f"⚠️ Попытка {attempt+1}/{max_retries} не удалась: {e}. Ждем 5 секунд...")
            await asyncio.sleep(5)
            
    if not bot_me:
        logger.error("❌ Не удалось подключиться к Telegram после 5 попыток. Проверь токен и сеть сервера.")
        return 

    logger.info("Запуск polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())





