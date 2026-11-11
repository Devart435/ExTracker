import asyncio
import os
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.filters import CommandStart, CommandObject

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
RENDER_URL = os.getenv("RENDER_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_ID = "@extracker_ru"
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

# Твои картинки
IMG_SUBSCRIBE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000fb8482108889f22a32b53712.png"
IMG_SUPPORT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000aa2c821087ec3f3ea12422f6.png"
IMG_PROFILE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000033e082109342702b717a9f88.png"
IMG_ABOUT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000a090821293d0cb7b8d988b9e.png"
IMG_START = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000002e882108efdb662d3c35408.png"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
async def save_user_to_db(user_id: int, username: str):
    url = f"{SUPABASE_URL}/rest/v1/users"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    data = {"chat_id": user_id, "username": username}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=data)

async def update_user_plan(user_id: int, plan: str):
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    data = {"plan": plan}
    async with aiohttp.ClientSession() as session:
        await session.patch(url, headers=headers, json=data)

async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- ГЛАВНОЕ МЕНЮ ---
async def show_main_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть ExTracker", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="Профиль", callback_data="profile"), InlineKeyboardButton(text="Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="О нас", callback_data="about")]
    ])
    caption = f"<b>Добро пожаловать в ExTracker, {message.from_user.first_name}.</b>\n\nВаш доступ к терминалу мониторинга крупных ончейн-сделок и смарт-мани в сетях TON и Solana активирован.\n\nНажмите кнопку ниже, чтобы открыть терминал и начать поиск транзакций китов."
    try:
        await message.answer_photo(photo=IMG_START, caption=caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer(caption, reply_markup=kb, parse_mode="HTML")

# --- СТАРТ С ПАРАМЕТРОМ (DEEP LINK) ---
@dp.message(CommandStart(deep_link=True))
async def start_with_payload(message: types.Message, command: CommandObject):
    payload = command.args
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    
    if payload == "pay_pro":
        await send_crypto_invoice(message, 5.0, "ExTracker PRO", "pro_30d")
    elif payload == "pay_plus":
        await send_crypto_invoice(message, 20.0, "ExTracker Plus", "plus_30d")
    else:
        await start(message)

@dp.message(CommandStart())
async def start(message: types.Message):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти в канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")], [InlineKeyboardButton(text="Проверить подписку", callback_data="check_sub")]])
        try:
            await message.answer_photo(photo=IMG_SUBSCRIBE, caption="Для доступа к терминалу ExTracker, пожалуйста, подпишитесь на наш новостной канал.", reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message.answer("Для доступа к терминалу ExTracker, пожалуйста, подпишитесь на наш новостной канал.", reply_markup=kb)
        return
    await show_main_menu(message)

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await show_main_menu(callback.message)
    else:
        await callback.answer("Вы все еще не подписаны на канал!", show_alert=True)

# --- ПРОФИЛЬ / ПОДДЕРЖКА / О НАС ---
@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]])
    text = f"<b>Профиль пользователя</b>\n\nID: <code>{callback.from_user.id}</code>\nСтатус: <b>FREE</b>\nЛимит сессии: <b>3 часа</b>"
    try:
        await callback.message.answer_photo(photo=IMG_PROFILE, caption=text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]])
    text = "<b>Служба поддержки ExTracker</b>\n\nПо вопросам обращайтесь:\n@ExTrackerSupport"
    try:
        await callback.message.answer_photo(photo=IMG_SUPPORT, caption=text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]])
    text = "<b>О проекте ExTracker</b>\n\nExTracker — профессиональная инфраструктура для ончейн-аналитики. Мониторим 100+ кошельков.\n\n<b>Наши ресурсы:</b>\n@extracker_ru\n@extracker_community\n\n<b>ExTracker Team</b>"
    try:
        await callback.message.answer_photo(photo=IMG_ABOUT, caption=text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back_to_start(callback: types.CallbackQuery):
    await callback.message.delete()
    await show_main_menu(callback.message)
    await callback.answer()

# --- ОПЛАТА (CRYPTO + STARS) ---
async def send_crypto_invoice(message: types.Message, amount_usd: float, title: str, payload: str):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {"asset": "USDT", "amount": str(amount_usd), "description": title, "payload": payload, "expires_in": 3600}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok"):
                    link = res["result"]["bot_invoice_url"]
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти к оплате", url=link)]])
                    await message.answer(f"Счет на {title} создан. Нажмите для оплаты:", reply_markup=kb)
                else:
                    await message.answer("Ошибка создания счета.")
    except Exception as e:
        print(f"CryptoBot Error: {e}")
        await message.answer("Ошибка сервера.")

@dp.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    if payload == "pro_30d":
        await update_user_plan(message.from_user.id, "pro")
        await message.answer("✅ Оплата Stars прошла! Ваш статус обновлен на <b>PRO</b>.", parse_mode="HTML")
    elif payload == "plus_30d":
        await update_user_plan(message.from_user.id, "plus")
        await message.answer("✅ Оплата Stars прошла! Ваш статус обновлен на <b>PLUS</b>.", parse_mode="HTML")

# --- ЗАПУСК ---
async def on_startup(bot: Bot):
    await bot.set_webhook(f"{RENDER_URL}/webhook")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
