import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
RENDER_URL = os.getenv("RENDER_URL")
CHANNEL_ID = "@extracker_ru"

# Твои картинки из Supabase
IMG_SUBSCRIBE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000fb8482108889f22a32b53712.png"
IMG_SUPPORT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000aa2c821087ec3f3ea12422f6.png"
IMG_PROFILE = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000033e082109342702b717a9f88.png"
IMG_ABOUT = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_00000000a090821293d0cb7b8d988b9e.png"
IMG_START = "https://wqktvtlmimvfdcogkzlf.supabase.co/storage/v1/object/public/banners/file_0000000002e882108efdb662d3c35408.png"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
        [
            InlineKeyboardButton(text="Профиль", callback_data="profile"),
            InlineKeyboardButton(text="Поддержка", callback_data="support")
        ],
        [InlineKeyboardButton(text="О нас", callback_data="about")]
    ])

    caption = (
        f"<b>Добро пожаловать в ExTracker, {message.from_user.first_name}.</b>\n\n"
        "Ваш доступ к терминалу мониторинга крупных ончейн-сделок и смарт-мани в сетях TON и Solana активирован.\n\n"
        "Нажмите кнопку ниже, чтобы открыть терминал и начать поиск транзакций китов."
    )
    try:
        await message.answer_photo(photo=IMG_START, caption=caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer(caption, reply_markup=kb, parse_mode="HTML")

# --- СТАРТ ---
@dp.message(CommandStart())
async def start(message: types.Message):
    is_sub = await check_sub(message.from_user.id)
    
    if not is_sub:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перейти в канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
            [InlineKeyboardButton(text="Проверить подписку", callback_data="check_sub")]
        ])
        text = "Для доступа к терминалу ExTracker, пожалуйста, подпишитесь на наш новостной канал."
        try:
            await message.answer_photo(photo=IMG_SUBSCRIBE, caption=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    await show_main_menu(message)

# --- ПРОВЕРКА ПОДПИСКИ ---
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    is_sub = await check_sub(callback.from_user.id)
    if is_sub:
        await callback.message.delete()
        await show_main_menu(callback.message)
    else:
        await callback.answer("Вы все еще не подписаны на канал!", show_alert=True)

# --- ПРОФИЛЬ ---
@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]])
    text = (
        "<b>Профиль пользователя</b>\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        "Статус аккаунта: <b>FREE</b>\n"
        "Лимит сессии: <b>3 часа</b>\n"
        "Остаток времени: <b>02:59:59</b>"
    )
    try:
        await callback.message.answer_photo(photo=IMG_PROFILE, caption=text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

# --- ПОДДЕРЖКА ---
@dp.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]])
    text = (
        "<b>Служба поддержки ExTracker</b>\n\n"
        "По вопросам работы терминала, оплаты или технических неполадок обращайтесь:\n"
        "@ExTrackerSupport"
    )
    try:
        await callback.message.answer_photo(photo=IMG_SUPPORT, caption=text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

# --- О НАС ---
@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]])
    
    # HTML-разметка, чтобы _ в ссылке не ломала текст
    text = (
        "<b>О проекте ExTracker</b>\n\n"
        "ExTracker — это профессиональная инфраструктура для ончейн-аналитики. Мы предоставляем трейдерам и инвесторам доступ к данным о движениях «умных денег» (Smart Money) в режиме реального времени.\n\n"
        "<b>Ключевые возможности:</b>\n"
        "• Мониторинг более 100 активных кошельков китов.\n"
        "• Мгновенные алерты о крупных сделках (BUY/SELL).\n"
        "• Встроенный веб-терминал с фильтрацией объемов.\n\n"
        "<b>Наши ресурсы:</b>\n"
        "• Новостной канал: @extracker_ru\n"
        "• Комьюнити: @extracker_community\n\n"
        "<b>ExTracker Team</b>"
    )
    
    try:
        await callback.message.answer_photo(photo=IMG_ABOUT, caption=text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

# --- НАЗАД ---
@dp.callback_query(F.data == "back")
async def back_to_start(callback: types.CallbackQuery):
    await callback.message.delete()
    await show_main_menu(callback.message)
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
