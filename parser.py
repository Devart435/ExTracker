import asyncio
import json
import os
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

# Заставляем Python выводить логи мгновенно (без задержек)
sys.stdout.reconfigure(line_buffering=True)

# Ключи из переменных окружения Render
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Реальные адреса китов
WHALE_WALLETS = [
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", # Wintermute
    "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm", # Jump Trading
    "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt"  # DWF Labs
]

# --- ОБМАНКА ДЛЯ RENDER (чтобы сервис не спал) ---
async def handle(request):
    return web.Response(text="ExTracker Parser is running...")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

# --- ПОЛУЧЕНИЕ КУРСА SOL ---
async def get_sol_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT') as resp:
                data = await resp.json()
                return float(data['price'])
    except Exception:
        return 85.0

# --- УВЕДОМЛЕНИЯ В ТЕЛЕГРАМ (ПОКА НЕ РАБОТАЕТ, НО КОД ЕСТЬ) ---
async def send_telegram_notification(action, wallet, amount, time):
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return
        
    indicator = "🟢" if action == "BUY" else "🔴"
    header = "КИТ ЗАКУПИЛСЯ!" if action == "BUY" else "КИТ ПРОДАЛ!"
        
    text = (
        f"{indicator} <b>{header}</b>\n\n"
        f"Действие: {action}\n"
        f"Сумма: ${amount:,.2f}\n"
        f"Кошелек: <code>{wallet[:6]}...{wallet[-6:]}</code>\n"
        f"Время: {time}\n"
        f"Сеть: Solana"
    )
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload)
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

# --- СОХРАНЕНИЕ В SUPABASE ---
async def save_to_db(wallet, action, amount):
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    data = {"wallet": wallet, "action": action, "amount": amount, "token": "SOL"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 201:
                    print(f"✅ Сделка сохранена в БД: {wallet[:8]}... на ${amount:.2f}")
                else:
                    print(f"❌ Ошибка записи в БД: {resp.status}")
    except Exception as e:
        print(f"Ошибка записи: {e}")

# --- ОСНОВНАЯ ЛОГИКА ---
async def listen_to_whales():
    if not HELIUS_API_KEY or not SUPABASE_URL:
        print("ОШИБКА: Не хватает ключей!")
        return

    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    print("Парсер запущен. Подключение к Helius...")

    async with websockets.connect(ws_url) as websocket:
        subscribe_message = {
            "jsonrpc": "2.0", "id": 1, "method": "transactionSubscribe",
            "params": [
                {"accountInclude": WHALE_WALLETS, "vote": False, "failed": False},
                {"commitment": "confirmed", "encoding": "jsonParsed", "transactionDetails": "full", "maxSupportedTransactionVersion": 1}
            ]
        }
        await websocket.send(json.dumps(subscribe_message))
        print("Подписка отправлена. Ждем сделки...")

        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]
                    transaction = tx["transaction"]
                    meta = transaction.get("meta", {})
                    pre_balances = meta.get("preBalances", [])
                    post_balances = meta.get("postBalances", [])
                    account_keys = transaction["transaction"]["message"]["accountKeys"]
                    
                    for i in range(len(account_keys)):
                        if i < len(pre_balances) and i < len(post_balances):
                            diff = post_balances[i] - pre_balances[i]
                            if abs(diff) > 1_000_000_000: 
                                amount_sol = abs(diff) / 1_000_000_000
                                sol_price = await get_sol_price()
                                amount_usd = amount_sol * sol_price
                                wallet = account_keys[i]
                                action = "BUY" if diff > 0 else "SELL"
                                
                                print(f"Найдена сделка: {action} на {amount_usd:.2f}$")
                                await save_to_db(wallet, action, amount_usd)
                                await send_telegram_notification(action, wallet, amount_usd, datetime.now().strftime("%H:%M:%S"))
            except websockets.exceptions.ConnectionClosed:
                print("Соединение закрыто. Переподключение...")
                break
            except Exception as e:
                print(f"Ошибка: {e}")

async def main():
    asyncio.create_task(start_web_server())
    while True:
        try:
            await listen_to_whales()
        except Exception as e:
            print(f"Критическая ошибка: {e}. Перезапуск...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
