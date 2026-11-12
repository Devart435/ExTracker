import asyncio
import os
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.filters import CommandStart, CommandObject

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://extracker-eight.vercel.app")
RENDER_URL = os.getenv("RENDER_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_ID = "@extracker_ru"
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

# Картинки
IMG_START = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000002e882108efdb662d3c35408.png"
IMG_SUBSCRIBE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000fb8482108889f22a32b53712.png"
IMG_SUPPORT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000aa2c821087ec3f3ea12422f6.png"
IMG_PROFILE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000033e082109342702b717a9f88.png"
IMG_ABOUT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000a090821293d0cb7b8d988b9e.png"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
async def save_user_to_db(user_id: int, username: str):
    url = f"{SUPABASE_URL}/rest/v1/users"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    data = {"chat_id": user_id, "username": username}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json=data)

async def get_user_plan(user_id: int) -> str:
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}&select=plan"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            if data and len(data) > 0: return data[0].get("plan", "free")
    return "free"

async def update_user_plan(user_id: int, plan: str):
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    async with aiohttp.ClientSession() as session:
        await session.patch(url, headers=headers, json={"plan": plan})

async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- ВЕБХУК КРИПТОБОТА ---
async def crypto_webhook(request):
    try:
        data = await request.json()
        if data.get("update_type") == "invoice_paid":
            payload = data.get("payload", {}).get("payload", "")
            if "_" in payload:
                user_id = int(payload.split("_")[-1])
                plan = "pro" if "pro" in payload else "plus"
                await update_user_plan(user_id, plan)
                await bot.send_message(user_id, f"✅ <b>Оплата прошла!</b>\nВаш статус обновлен на <b>{plan.upper()}</b>.", parse_mode="HTML")
        return web.Response(status=200)
    except Exception:
        return web.Response(status=500)

# --- КЛАВИАТУРЫ ---
def main_reply_kb():
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚀 Открыть ExTracker")],
        [KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="ℹ️ О нас"), KeyboardButton(text="💎 Тарифы")]
    ], resize_keyboard=True)
    return kb

def inline_start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть ExTracker", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart(deep_link=True))
async def start_with_payload(message: types.Message, command: CommandObject):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if command.args == "pay_pro":
        await send_crypto_invoice(message, 9.0, "ExTracker PRO", "pro_30d")
    elif command.args == "pay_plus":
        await send_crypto_invoice(message, 20.0, "ExTracker Plus", "plus_30d")
    else:
        await start(message)

@dp.message(CommandStart())
async def start(message: types.Message):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти в канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")], [InlineKeyboardButton(text="Проверить подписку", callback_data="check_sub")]])
        await message.answer_photo(photo=IMG_SUBSCRIBE, caption="Для доступа к терминалу ExTracker, пожалуйста, подпишитесь на наш новостной канал.", reply_markup=kb, parse_mode="HTML")
        return
    caption = f"<b>Добро пожаловать в ExTracker, {message.from_user.first_name}.</b>\n\nВаш доступ к терминалу мониторинга крупных ончейн-сделок активирован."
    await message.answer_photo(photo=IMG_START, caption=caption, reply_markup=inline_start_kb(), parse_mode="HTML")
    await message.answer("Используйте меню ниже для навигации:", reply_markup=main_reply_kb())

@dp.message(F.text == "🚀 Открыть ExTracker")
async def btn_open_app(message: types.Message):
    await message.answer("Нажмите кнопку ниже, чтобы открыть приложение:", reply_markup=inline_start_kb())

@dp.message(F.text == "💬 Поддержка")
async def btn_support(message: types.Message):
    text = ("<b>Служба поддержки ExTracker</b>\n\n"
            "Наша команда на связи 24/7. Мы поможем с оплатой, настройкой бота или решением любых технических проблем.\n\n"
            "📩 Пишите сюда: @ExTrackerSupport\n\n"
            "Среднее время ответа — 15-30 минут. Если вы обнаружили баг, приложите скриншот и опишите проблему.")
    await message.answer_photo(photo=IMG_SUPPORT, caption=text, parse_mode="HTML")

@dp.message(F.text == "👤 Профиль")
async def btn_profile(message: types.Message):
    plan = await get_user_plan(message.from_user.id)
    status = "PRO" if plan != "free" else "FREE"
    text = f"<b>Профиль пользователя</b>\n\nID: <code>{message.from_user.id}</code>\nТариф: <b>{status}</b>\nЛимит сессии: <b>{'24/7' if status == 'PRO' else '3 часа'}</b>\nКастомные кошельки: <b>0 / {'50' if status == 'PRO' else '2'}</b>"
    await message.answer_photo(photo=IMG_PROFILE, caption=text, parse_mode="HTML")

@dp.message(F.text == "ℹ️ О нас")
async def btn_about(message: types.Message):
    text = ("<b>О проекте ExTracker</b>\n\n"
            "ExTracker — это профессиональный Telegram-терминал для ончейн-аналитики. Мы даем обычному трейдеру те же возможности, что и крупным фондам.\n\n"
            "<b>Что мы делаем:</b>\n"
            "• Мониторим 100+ кошельков крипто-миллионеров и фондов (Wintermute, Jump Trading и др.)\n"
            "• Сканируем блокчейны Solana и TON в реальном времени 24/7\n"
            "• Показываем крупные сделки (от $5,000) и тренды китов\n\n"
            "<b>Наши ресурсы:</b>\n"
            "@extracker_ru — новости и анонсы\n"
            "@extracker_community — чат трейдеров\n\n"
            "Мы не просим доступ к вашим кошелькам. Только публичные данные блокчейна.")
    await message.answer_photo(photo=IMG_ABOUT, caption=text, parse_mode="HTML")

@dp.message(F.text == "💎 Тарифы")
async def btn_plans(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Оплатить PRO ($9)", url="https://t.me/ExTrackerTerminalBot?start=pay_pro")]])
    text = ("<b>Тарифные планы ExTracker</b>\n\n"
            "<b>FREE ($0)</b> — для знакомства\n"
            "• Базовый терминал и лента\n"
            "• Задержка уведомлений 5-10 мин\n"
            "• До 2 кастомных кошельков\n"
            "• Частично скрытые адреса\n\n"
            "<b>PRO ($9/мес)</b> — для активного трейдинга\n"
            "• Мгновенные уведомления без задержек\n"
            "• Безлимитное сканирование 24/7\n"
            "• Полные открытые адреса китов\n"
            "• До 50 кастомных кошельков\n"
            "• Статистика винрейта и PnL (в разработке)")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- КАСТОМНЫЕ КОШЕЛЬКИ ---
@dp.message(F.text.startswith("/add_wallet"))
async def add_wallet(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /add_wallet <адрес>\n\nПример:\n/add_wallet EQBfbbSCrAnX2XWOjSq2qnAx...")
        return
    wallet = args[1].strip()
    network = "Solana" if len(wallet) > 40 and not wallet.startswith("E") else "TON"
    
    url = f"{SUPABASE_URL}/rest/v1/custom_wallets"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    data = {"chat_id": message.from_user.id, "wallet": wallet, "network": network}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status in [200, 201]:
                await message.answer(f"✅ Кошелек добавлен!\nСеть: {network}\nАдрес: <code>{wallet}</code>", parse_mode="HTML")
            else:
                await message.answer("Ошибка при добавлении.")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await start(callback.message)
    else:
        await callback.answer("Вы не подписаны!", show_alert=True)

async def send_crypto_invoice(message: types.Message, amount_usd: float, title: str, payload: str):
    if not CRYPTO_PAY_TOKEN:
        await message.answer("Ошибка: токен не настроен.")
        return
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {"asset": "USDT", "amount": str(amount_usd), "description": title, "payload": f"{payload}_{message.from_user.id}", "expires_in": 3600}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok"):
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить", url=res["result"]["bot_invoice_url"])]])
                    await message.answer(f"Счет на {title} создан:", reply_markup=kb)
                else:
                    await message.answer("Ошибка создания счета.")
    except Exception:
        await message.answer("Ошибка сервера.")

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{RENDER_URL}/webhook", drop_pending_updates=True)

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    app.router.add_post("/crypto_webhook", crypto_webhook)
    setup_application(app, dp, bot=bot, on_startup=on_startup)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()
