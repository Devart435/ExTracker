import asyncio
import os
import logging
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_ID = "@extracker_ru"
SUPPORT_LINK = "https://t.me/ExTrackerSupport"
POLICY_LINK = "https://extracker-policy.vercel.app"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
async def db_request(method, endpoint, json_data=None, params=None):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.request(method, f"{SUPABASE_URL}/rest/v1/{endpoint}", headers=headers, json=json_data, params=params) as resp:
            return await resp.json() if resp.status != 204 else None

async def save_user(chat_id, username):
    await db_request("POST", "users", json_data={"chat_id": chat_id, "username": username, "plan": "free", "is_active": True}, params={"on_conflict": "chat_id"})

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception: return False

# --- ХЭНДЛЕРЫ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await save_user(message.from_user.id, message.from_user.username)
    
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал 📢", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
            [InlineKeyboardButton(text="Я подписался ✅", callback_data="check_sub")]
        ])
        await message.answer("Для использования бота подпишитесь на наш канал:", reply_markup=kb)
        return

    # Кнопка запуска
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить ExTracker", web_app=WebAppInfo(url="https://extracker-eight.vercel.app"), style="success")],
        [InlineKeyboardButton(text="Поддержка", url=SUPPORT_LINK), InlineKeyboardButton(text="Политика", url=POLICY_LINK)]
    ])
    await message.answer_photo(
        photo="https://i.imgur.com/your_logo.png", # Замени на свой логотип
        caption="<b>Привет!</b> 👋\n\nExTracker — это твой терминал для трекинга китов в Solana и TON. Я показываю сделки крупных игроков в реальном времени.\n\nЖми кнопку ниже, чтобы начать.",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await cmd_start(callback.message)
    else:
        await callback.answer("Вы еще не подписались!", show_alert=True)

@dp.message(Command("pay_pro"))
async def pay_pro(message: types.Message):
    await message.answer("Создаю счет...")

# --- АЛЕРТЫ (ВЫЗЫВАЕТСЯ ИЗ ПАРСЕРА) ---
# В парсере у меня уже есть функция send_telegram_alert, которая шлет запросы напрямую.
# Если ты хочешь, чтобы бот сам отправлял алерты (через aiogram), то тут нужен отдельный вебхук.
# Но пока оставим как есть в парсере, чтобы не ломать логику.

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
