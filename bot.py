import asyncio
import os
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.filters import CommandStart, CommandObject, Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://extracker-eight.vercel.app")
RENDER_URL = os.getenv("RENDER_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_ID = "@extracker_ru"
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def save_user_to_db(user_id: int, username: str):
    url = f"{SUPABASE_URL}/rest/v1/users"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, headers=headers, json={"chat_id": user_id, "username": username})

async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

async def crypto_webhook(request):
    try:
        data = await request.json()
        if data.get("update_type") == "invoice_paid":
            payload = data.get("payload", {}).get("payload", "")
            if "_" in payload:
                user_id = int(payload.split("_")[-1])
                plan = "pro" if "pro" in payload else "plus"
                url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}"
                headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
                async with aiohttp.ClientSession() as session:
                    await session.patch(url, headers=headers, json={"plan": plan})
                    await bot.send_message(user_id, f"✅ Оплата прошла! Статус: {plan.upper()}", parse_mode="HTML")
        return web.Response(status=200)
    except Exception:
        return web.Response(status=500)

async def show_main_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть ExTracker", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="Профиль", callback_data="profile"), InlineKeyboardButton(text="Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="Добавить кошелек", callback_data="add_wallet_help")]
    ])
    try:
        await message.answer_photo(photo="https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000002e882108efdb662d3c35408.png", caption="<b>Добро пожаловать в ExTracker!</b>\n\nНажмите кнопку ниже, чтобы открыть терминал.", reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer("Добро пожаловать в ExTracker! Нажмите кнопку ниже.", reply_markup=kb)

@dp.message(CommandStart(deep_link=True))
async def start_with_payload(message: types.Message, command: CommandObject):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if command.args == "pay_pro":
        await send_crypto_invoice(message, 9.0, "ExTracker PRO", "pro_30d")
    else:
        await start(message)

@dp.message(CommandStart())
async def start(message: types.Message):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти в канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")], [InlineKeyboardButton(text="Проверить", callback_data="check_sub")]])
        await message.answer("Для доступа подпишитесь на канал.", reply_markup=kb)
        return
    await show_main_menu(message)

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await show_main_menu(callback.message)
    else:
        await callback.answer("Вы не подписаны!", show_alert=True)

# --- ДОБАВЛЕНИЕ КОШЕЛЬКОВ ---
@dp.message(Command("add_wallet"))
async def add_wallet(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /add_wallet <адрес>\n\nПример:\n/add_wallet EQBfbbSCrAnX2XWOjSq2qnAx...")
        return
    
    wallet = args[1].strip()
    # Определяем сеть по длине адреса
    network = "Solana" if len(wallet) > 40 and not wallet.startswith("E") else "TON"
    
    url = f"{SUPABASE_URL}/rest/v1/custom_wallets"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    data = {"chat_id": message.from_user.id, "wallet": wallet, "network": network}
    
    async with aiohttp.ClientSession() as session:
        # Проверка лимита (на FREE - 2 кошелька)
        user_url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{message.from_user.id}&select=plan"
        async with session.get(user_url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}) as resp:
            user_data = await resp.json()
            plan = user_data[0].get("plan", "free") if user_data else "free"
            
        if plan == "free":
            count_url = f"{SUPABASE_URL}/rest/v1/custom_wallets?chat_id=eq.{message.from_user.id}&select=wallet"
            async with session.get(count_url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}) as resp:
                existing = await resp.json()
                if len(existing) >= 2:
                    await message.answer("❌ На тарифе FREE можно добавить не более 2 кошельков.\n\nОформите PRO для снятия лимита.")
                    return
        
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status in [200, 201]:
                await message.answer(f"✅ Кошелек добавлен!\nСеть: {network}\nАдрес: <code>{wallet}</code>", parse_mode="HTML")
            else:
                await message.answer("Ошибка при добавлении.")

@dp.callback_query(F.data == "add_wallet_help")
async def add_wallet_help(callback: types.CallbackQuery):
    await callback.message.answer("Чтобы добавить кошелек, отправьте команду:\n\n<code>/add_wallet ВАШ_АДРЕС</code>\n\nНа FREE можно добавить до 2 кошельков, на PRO — до 50.", parse_mode="HTML")
    await callback.answer()

# --- ОСТАЛЬНЫЕ ХЕНДЛЕРЫ ---
@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    await callback.message.answer(f"<b>Профиль</b>\nID: <code>{callback.from_user.id}</code>", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    await callback.message.answer("Поддержка: @ExTrackerSupport")
    await callback.answer()

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
