import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
RENDER_URL = os.getenv("RENDER_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message()
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть ExTracker", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("Привет! Это ExTracker. Нажми кнопку ниже:", reply_markup=kb)

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
