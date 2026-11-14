import asyncio
import os
import aiohttp
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.filters import CommandStart, CommandObject

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://extracker-eight.vercel.app")
RENDER_URL = os.getenv("RENDER_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_ID = "@extracker_ru"
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

IMG_START = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_000000009af88210a3d41715da171b4a.png"
IMG_SUBSCRIBE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000fb8482108889f22a32b53712.png"
URL_TERMS = "https://extracker-policy.vercel.app/terms.html"
URL_PRIVACY = "https://extracker-policy.vercel.app/privacy.html"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
_http_session: aiohttp.ClientSession | None = None

async def get_http() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# --- БАЗА ДАННЫХ ---
async def save_user_to_db(user_id: int, username: str):
    url = f"{SUPABASE_URL}/rest/v1/users"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    data = {"chat_id": user_id, "username": username}
    session = await get_http()
    await session.post(url, headers=headers, json=data)

async def get_user_data(user_id: int) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}&select=plan,plan_expires_at"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    session = await get_http()
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200: return {"plan": "free", "plan_expires_at": None}
        data = await resp.json()
        if data and len(data) > 0: return data[0]
    return {"plan": "free", "plan_expires_at": None}

async def update_user_plan(user_id: int, plan: str, expires_at: str = None):
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    data = {"plan": plan}
    if expires_at: data["plan_expires_at"] = expires_at
    session = await get_http()
    await session.patch(url, headers=headers, json=data)

async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception: return True

# --- ВЕБХУК ОПЛАТЫ ---
async def crypto_webhook(request):
    try:
        body = await request.text()
        signature = request.headers.get("crypto-pay-api-signature", "")
        secret = hashlib.sha256(CRYPTO_PAY_TOKEN.encode()).digest()
        if not hmac.compare_digest(hmac.new(secret, body.encode(), hashlib.sha256).hexdigest(), signature):
            return web.Response(status=403)
        data = json.loads(body)
        if data.get("update_type") != "invoice_paid": return web.Response(status=200)
        
        invoice_obj = data.get("payload", {})
        payload_str = invoice_obj.get("payload", "")
        invoice_id = str(invoice_obj.get("invoice_id", ""))
        
        session = await get_http()
        async with session.get(f"{SUPABASE_URL}/rest/v1/payments?invoice_id=eq.{invoice_id}&select=invoice_id", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}) as chk:
            if await chk.json(): return web.Response(status=200)

        user_id = int(payload_str.split("_")[-1])
        plan = "pro"
        base = datetime.now(timezone.utc)
        current = await get_user_data(user_id)
        if current.get("plan") == "pro" and current.get("plan_expires_at"):
            cur_exp = datetime.fromisoformat(current["plan_expires_at"].replace("Z", "+00:00"))
            if cur_exp > base: base = cur_exp
        new_exp = (base + timedelta(days=30)).isoformat()
        await update_user_plan(user_id, plan, new_exp)
        await session.post(f"{SUPABASE_URL}/rest/v1/payments", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}, json={"invoice_id": invoice_id, "user_id": user_id, "amount": invoice_obj.get("amount"), "plan": plan})
        await bot.send_message(user_id, f"✅ <b>Оплата прошла!</b> PRO активен до {new_exp[:10]}.", parse_mode="HTML")
        return web.Response(status=200)
    except Exception as e:
        print(f"Webhook err: {e}"); return web.Response(status=200)

async def send_crypto_invoice(message: types.Message, amount_usd: float, title: str, payload: str):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {"asset": "USDT", "amount": str(amount_usd), "description": title, "payload": f"{payload}_{message.chat.id}", "expires_in": 3600}
    try:
        session = await get_http()
        async with session.post(url, json=data, headers=headers) as resp:
            res = await resp.json()
            if res.get("ok"):
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=res["result"]["bot_invoice_url"])]])
                await message.answer(f"Счет на {title} создан:", reply_markup=kb)
    except Exception: pass

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart(deep_link=True))
async def start_deep_link(message: types.Message, command: CommandObject):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if command.args == "pay_pro":
        # Если перешел по ссылке оплаты — сразу требуем согласие
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я принимаю Оферту", callback_data="agree_terms")],
            [InlineKeyboardButton(text="📄 Оферта", url=URL_TERMS), InlineKeyboardButton(text="📄 Политика", url=URL_PRIVACY)]
        ])
        await message.answer("Перед оплатой подписки PRO ($9/мес) вы должны ознакомиться и согласиться с условиями:", reply_markup=kb)
    else:
        await start(message)

@dp.message(CommandStart())
async def start(message: types.Message):
    await save_user_to_db(message.from_user.id, message.from_user.username or "unknown")
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перейти в канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
            [InlineKeyboardButton(text="Проверить подписку", callback_data="check_sub")]
        ])
        await message.answer_photo(photo=IMG_SUBSCRIBE, caption="Для доступа к терминалу ExTracker, пожалуйста, подпишитесь на наш новостной канал.", reply_markup=kb, parse_mode="HTML")
        return

    # ВОЗВРАЩАЕМ БОЛЬШОЙ ТЕКСТ
    caption = (
        f"<b>Добро пожаловать в ExTracker, {message.from_user.first_name}.</b>\n\n"
        "ExTracker – мониторинг крупных ончейн-сделок и смарт-мани в сетях TON и Solana в реальном времени.\n\n"
        "Мы анализируем транзакции крупнейших игроков рынка, чтобы вы могли видеть движение капитала раньше остальных.\n"
        "В приложении доступны: живая лента сделок, детальные графики активности китов, статистика по токенам и удобный поиск.\n"
        "Все данные берутся напрямую из блокчейна и обновляются каждую секунду.\n"
        "Никаких задержек, никакого шума — только важные сигналы для принятия решений."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить ExTracker", web_app=WebAppInfo(url=WEBAPP_URL), style="success")],
        [InlineKeyboardButton(text="Поддержка", url="https://t.me/ExTrackerSupport")],
        [InlineKeyboardButton(text="Политика конфиденциальности", url=URL_PRIVACY)]
    ])
    await message.answer_photo(photo=IMG_START, caption=caption, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "agree_terms")
async def agree_terms_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await send_crypto_invoice(callback.message, 9.0, "ExTracker PRO", "pro_30d")
    await callback.answer("Согласие принято.")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await start(callback.message)
    else:
        await callback.answer("Вы не подписаны!", show_alert=True)

# --- STARTUP ---
async def on_startup(bot: Bot):
    if WEBHOOK_SECRET:
        await bot.set_webhook(f"{RENDER_URL}/webhook", secret_token=WEBHOOK_SECRET, drop_pending_updates=False)
    else:
        await bot.set_webhook(f"{RENDER_URL}/webhook", drop_pending_updates=False)
    await get_http()

def main():
    app = web.Application()
    handler_kwargs = {"dispatcher": dp, "bot": bot}
    if WEBHOOK_SECRET: handler_kwargs["secret_token"] = WEBHOOK_SECRET
    SimpleRequestHandler(**handler_kwargs).register(app, path="/webhook")
    app.router.add_post("/crypto_webhook", crypto_webhook)
    setup_application(app, dp, bot=bot, on_startup=on_startup)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()
