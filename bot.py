import asyncio
import os
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.filters import CommandStart

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

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
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

# --- ПРОФИЛЬ И ПОДДЕРЖКА ---
@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    # Получаем текущий план из базы (упрощенно, для примера)
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

# --- ОПЛАТА STAR ---
@dp.callback_query(F.data == "pay_stars_pro")
async def pay_stars_pro(callback: types.CallbackQuery):
    prices = [LabeledPrice(label="XTR", amount=250)] # 250 Stars (примерно $5)
    await callback.message.answer_invoice(
        title="ExTracker PRO",
        description="Доступ к PRO-тарифу на 30 дней",
        prices=prices,
        provider_token="",
        currency="XTR",
        payload="pro_30d"
    )
    await callback.answer()

@dp.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    if payload == "pro_30d":
        await update_user_plan(message.from_user.id, "pro")
        await message.answer("✅ Оплата Stars прошла! Ваш статус обновлен на <b>PRO</b>.", parse_mode="HTML")
    elif payload == "plus_30d":
        await update_user_plan(message.from_user.id, "plus")
        await message.answer("✅ Оплата Stars прошла! Ваш статус обновлен на <b>PLUS</b>.", parse_mode="HTML")

# --- ОПЛАТА КРИПТА (CryptoBot) ---
async def create_crypto_invoice(amount_usd: float, description: str, payload: str):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {"asset": "USDT", "amount": str(amount_usd), "description": description, "payload": payload, "expires_in": 3600}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok"):
                    return res["result"]["bot_invoice_url"]
    except Exception as e:
        print(f"CryptoBot Error: {e}")
    return None

@dp.callback_query(F.data == "pay_crypto_pro")
async def pay_crypto_pro(callback: types.CallbackQuery):
    link = await create_crypto_invoice(5.0, "ExTracker PRO (30 дней)", "pro_30d")
    if link:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти к оплате", url=link)]])
        await callback.message.answer("Счет создан. Нажмите для оплаты:", reply_markup=kb)
    else:
        await callback.message.answer("Ошибка создания счета.")
    await callback.answer()

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
