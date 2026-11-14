import asyncio
import os
import aiohttp
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
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

if not WEBHOOK_SECRET:
    print("⚠️ ВНИМАНИЕ: WEBHOOK_SECRET не задан. Вебхук не защищён!")

IMG_START = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000002e882108efdb662d3c35408.png"
IMG_SUBSCRIBE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000fb8482108889f22a32b53712.png"
IMG_SUPPORT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000aa2c821087ec3f3ea12422f6.png"
IMG_PROFILE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000033e082109342702b717a9f88.png"
IMG_ABOUT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000a090821293d0cb7b8d988b9e.png"

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
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    data = {"chat_id": user_id, "username": username}
    session = await get_http()
    async with session.post(url, headers=headers, json=data) as resp:
        if resp.status not in (200, 201, 204):
            print(f"⚠️ save_user_to_db HTTP {resp.status}: {await resp.text()}")

async def get_user_data(user_id: int) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}&select=plan,plan_expires_at"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    session = await get_http()
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            return {"plan": "free", "plan_expires_at": None}
        data = await resp.json()
        if data and len(data) > 0:
            return data[0]
    return {"plan": "free", "plan_expires_at": None}

async def update_user_plan(user_id: int, plan: str, expires_at: str = None):
    url = f"{SUPABASE_URL}/rest/v1/users?chat_id=eq.{user_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    data = {"plan": plan}
    if expires_at:
        data["plan_expires_at"] = expires_at
    session = await get_http()
    async with session.patch(url, headers=headers, json=data) as resp:
        if resp.status not in (200, 204):
            print(f"⚠️ update_user_plan HTTP {resp.status}: {await resp.text()}")

async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"⚠️ check_sub ошибка: {e}")
        return True  # не блокируем при ошибке сети

async def verify_plan(user_id: int):
    user_data = await get_user_data(user_id)
    plan = user_data.get("plan", "free")
    expires_at = user_data.get("plan_expires_at")
    if plan == "pro" and expires_at:
        try:
            exp_date = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_date.tzinfo is None:
                exp_date = exp_date.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_date:
                await update_user_plan(user_id, "free", None)
                return "expired"
        except Exception as e:
            print(f"Ошибка парсинга даты: {e}")
            return "free"
    return plan

# --- ВЕБХУК КРИПТОБОТА ---
async def crypto_webhook(request):
    try:
        body = await request.text()
        signature = request.headers.get("crypto-pay-api-signature", "")
        secret = hashlib.sha256(CRYPTO_PAY_TOKEN.encode()).digest()
        check_hash = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(check_hash, signature):
            print("❌ Ошибка подписи вебхука!")
            return web.Response(status=403)

        data = json.loads(body)
        if data.get("update_type") != "invoice_paid":
            return web.Response(status=200)

        invoice_obj = data.get("payload", {})
        payload_str = invoice_obj.get("payload", "")
        invoice_id = str(invoice_obj.get("invoice_id", ""))
        if not invoice_id:
            print("⚠️ invoice_paid без invoice_id, пропуск")
            return web.Response(status=200)

        session = await get_http()
        # Идемпотентность
        async with session.get(
            f"{SUPABASE_URL}/rest/v1/payments?invoice_id=eq.{invoice_id}&select=invoice_id",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        ) as chk:
            existing = await chk.json()
            if existing:
                print(f"ℹ️ invoice {invoice_id} уже обработан")
                return web.Response(status=200)

        if "_" not in payload_str:
            return web.Response(status=200)
        try:
            user_id = int(payload_str.split("_")[-1])
        except (ValueError, IndexError):
            print(f"⚠️ битый payload: {payload_str}")
            return web.Response(status=200)

        plan = "pro" if "pro" in payload_str else "plus"

        # Продление от текущей даты, не от now()
        base = datetime.now(timezone.utc)
        current = await get_user_data(user_id)
        if current.get("plan") == "pro" and current.get("plan_expires_at"):
            try:
                cur_exp = datetime.fromisoformat(current["plan_expires_at"].replace("Z", "+00:00"))
                if cur_exp.tzinfo is None:
                    cur_exp = cur_exp.replace(tzinfo=timezone.utc)
                if cur_exp > base:
                    base = cur_exp
            except Exception as e:
                print(f"⚠️ ошибка парсинга текущей даты: {e}")

        new_exp = (base + timedelta(days=30)).isoformat()
        await update_user_plan(user_id, plan, new_exp)

        # Запись в payments
        async with session.post(
            f"{SUPABASE_URL}/rest/v1/payments",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"invoice_id": invoice_id, "user_id": user_id, "amount": invoice_obj.get("amount"), "plan": plan},
        ) as pay_resp:
            if pay_resp.status not in (200, 201, 204):
                print(f"⚠️ payments insert HTTP {pay_resp.status}: {await pay_resp.text()}")

        await bot.send_message(
            user_id,
            f"✅ <b>Оплата прошла!</b>\nВаш статус обновлен на <b>{plan.upper()}</b> (до {new_exp[:10]}).",
            parse_mode="HTML",
        )
        return web.Response(status=200)
    except Exception as e:
        print(f"Ошибка вебхука: {e}")
        return web.Response(status=200)  # всегда 200, чтобы CryptoBot не ретраил бесконечно

# --- КЛАВИАТУРЫ ---
def main_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Открыть ExTracker")],
            [KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="ℹ️ О нас"), KeyboardButton(text="💎 Тарифы")],
        ],
        resize_keyboard=True,
    )

def inline_start_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚀 Открыть ExTracker", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )

# --- ХЕНДЛЕРЫ ---
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
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Перейти в канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
                [InlineKeyboardButton(text="Проверить подписку", callback_data="check_sub")],
            ]
        )
        await message.answer_photo(
            photo=IMG_SUBSCRIBE,
            caption="Для доступа к терминалу ExTracker, пожалуйста, подпишитесь на наш новостной канал.",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return
    caption = (
        f"<b>Добро пожаловать в ExTracker, {message.from_user.first_name}.</b>\n\n"
        "Ваш доступ к терминалу мониторинга крупных ончейн-сделок активирован."
    )
    await message.answer_photo(photo=IMG_START, caption=caption, reply_markup=inline_start_kb(), parse_mode="HTML")
    await message.answer("Используйте меню ниже для навигации:", reply_markup=main_reply_kb())

@dp.message(F.text == "🚀 Открыть ExTracker")
async def btn_open_app(message: types.Message):
    await message.answer("Нажмите кнопку ниже, чтобы открыть приложение:", reply_markup=inline_start_kb())

@dp.message(F.text == "💬 Поддержка")
async def btn_support(message: types.Message):
    text = "<b>Служба поддержки ExTracker</b>\n\nНаша команда на связи 24/7.\n\n📩 Пишите сюда: @ExTrackerSupport"
    await message.answer_photo(photo=IMG_SUPPORT, caption=text, parse_mode="HTML")

@dp.message(F.text == "👤 Профиль")
async def btn_profile(message: types.Message):
    plan = await verify_plan(message.from_user.id)
    if plan == "expired":
        text = (
            "<b>Профиль пользователя</b>\n\n⚠️ <b>Подписка истекла.</b>\n"
            "Ваш PRO тариф приостановлен. Продлите его в боте."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Оплатить PRO ($9)", callback_data="pay_pro")]]
        )
        await message.answer_photo(photo=IMG_PROFILE, caption=text, reply_markup=kb, parse_mode="HTML")
        return
    status = "PRO" if plan != "free" else "FREE"
    text = f"<b>Профиль пользователя</b>\n\nID: <code>{message.from_user.id}</code>\nТариф: <b>{status}</b>"
    await message.answer_photo(photo=IMG_PROFILE, caption=text, parse_mode="HTML")

@dp.message(F.text == "ℹ️ О нас")
async def btn_about(message: types.Message):
    text = "<b>О проекте ExTracker</b>\n\nExTracker — профессиональная инфраструктура для ончейн-аналитики."
    await message.answer_photo(photo=IMG_ABOUT, caption=text, parse_mode="HTML")

@dp.message(F.text == "💎 Тарифы")
async def btn_plans(message: types.Message):
    plan = await verify_plan(message.from_user.id)
    current = {"free": "FREE", "pro": "PRO", "expired": "истёк"}.get(plan, "FREE")
    if plan == "pro":
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        text = (
            "<b>Тарифные планы ExTracker</b>\n\n"
            "Ваш текущий план: <b>PRO</b> ✅\n\n"
            "<b>PRO ($9/мес)</b> — продлить можно в «Профиль»."
        )
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="💸 Оплатить PRO ($9)", callback_data="pay_pro")]]
        )
        text = (
            "<b>Тарифные планы ExTracker</b>\n\n"
            f"Ваш текущий план: <b>{current}</b>\n\n"
            "<b>FREE ($0)</b> — базовый доступ\n"
            "<b>PRO ($9/мес)</b> — мгновенные уведомления, открытые адреса, безлимит"
        )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- ОПЛАТА ---
@dp.callback_query(F.data == "pay_pro")
async def callback_pay_pro(callback: types.CallbackQuery):
    await send_crypto_invoice(callback.message, 9.0, "ExTracker PRO", "pro_30d")
    await callback.answer()

async def send_crypto_invoice(message: types.Message, amount_usd: float, title: str, payload: str):
    if not CRYPTO_PAY_TOKEN:
        await message.answer("Ошибка: токен не настроен.")
        return
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {
        "asset": "USDT",
        "amount": str(amount_usd),
        "description": title,
        "payload": f"{payload}_{message.chat.id}",
        "expires_in": 3600,
    }
    try:
        session = await get_http()
        async with session.post(url, json=data, headers=headers) as resp:
            res = await resp.json()
            if res.get("ok"):
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить", url=res["result"]["bot_invoice_url"])]]
                )
                await message.answer(f"Счет на {title} создан:", reply_markup=kb)
            else:
                await message.answer("Ошибка создания счета.")
    except Exception as e:
        print(f"⚠️ send_crypto_invoice: {e}")
        await message.answer("Ошибка сервера.")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await start(callback.message)
    else:
        await callback.answer("Вы не подписаны!", show_alert=True)

# --- STARTUP / SHUTDOWN ---
async def on_startup(bot: Bot):
    if not RENDER_URL:
        raise ValueError("RENDER_URL не задан в env!")
    kwargs = {"drop_pending_updates": False}
    if WEBHOOK_SECRET:
        kwargs["secret_token"] = WEBHOOK_SECRET
    await bot.set_webhook(f"{RENDER_URL}/webhook", **kwargs)
    await get_http()
    print(f"✅ Webhook: {RENDER_URL}/webhook")

async def on_shutdown(bot: Bot):
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
        print("✅ HTTP-сессия закрыта")

def main():
    app = web.Application()
    handler_kwargs = {"dispatcher": dp, "bot": bot}
    if WEBHOOK_SECRET:
        handler_kwargs["secret_token"] = WEBHOOK_SECRET
    SimpleRequestHandler(**handler_kwargs).register(app, path="/webhook")
    app.router.add_post("/crypto_webhook", crypto_webhook)
    setup_application(app, dp, bot=bot, on_startup=on_startup, on_shutdown=on_shutdown)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()
