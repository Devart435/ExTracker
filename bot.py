import asyncio
import os
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_ID = "@extracker_ru"
SUPPORT_LINK = "https://t.me/ExTrackerSupport"
PHOTO_URL = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_000000009af88210a3d41715da171b4a.png"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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

    name = message.from_user.first_name or "друг"
    
    caption = (
        f"<b>Добро пожаловать в ExTracker, {name}.</b>\n\n"
        "ExTracker — мониторинг крупных ончейн-сделок и смарт-мани в сетях TON и Solana в реальном времени.\n\n"
        "Мы анализируем транзакции крупнейших игроков рынка, чтобы вы могли видеть движение капитала раньше остальных.\n"
        "В приложении доступны: живая лента сделок, детальные графики активности китов, статистика по токенам и удобный поиск.\n"
        "Все данные берутся напрямую из блокчейна и обновляются каждую секунду.\n"
        "Никаких задержек, никакого шума — только важные сигналы для принятия решений."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить ExTracker", web_app=WebAppInfo(url="https://extracker-eight.vercel.app"), style="success")],
        [InlineKeyboardButton(text="Поддержка", url=SUPPORT_LINK)]
    ])
    
    await message.answer_photo(
        photo=PHOTO_URL,
        caption=caption,
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await cmd_start(callback.message)
    else:
        await callback.answer("Вы еще не подписались!", show_alert=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
