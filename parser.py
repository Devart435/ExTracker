import asyncio
import json
import os
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

WHALE_WALLETS = [
    # === 1. МАРКЕТ-МЕЙКЕРЫ (Подтвержденные) ===
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", # Wintermute (Primary MM) [citation:3]
    "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa", # Wintermute (Market Making) [citation:3]
    "BMnT51N4iSNhWU5PyFFgWwFvN1jgaiiDr9ZHgnkm3iLJ", # Wintermute (OTC/Trading) [citation:3]
    "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm", # Jump Trading [citation:3]
    "6v3snejEvRsTzeUZV2yKAcRgbxRz3iMJJgpeqJ1CxM6P", # Jump Capital [citation:3]
    "5pU7WKL47At6rHLM4CmFCSPRdT32J1LHSgPFhWGuXZqc", # Jump Capital [citation:3]
    "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt", # DWF Labs (Official) [citation:3]
    "B5dWf97VwfKumCT377Nh8rC51qoi7o5tYou3ZNzrR3P3", # DWF Labs (Suspected) [citation:3]
    
    # === 2. ПРОГРАММЫ (Генерируют тонны транзакций) ===
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", # Raydium AMM v4 [citation:4][citation:8]
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", # Raydium CLMM [citation:4][citation:8]
    
    # === 3. КРУПНЕЙШИЕ ТРЕЙДЕРЫ (Из Dune Analytics) ===
    "jTcKH6sMbMMrvroaqeuM1CFmESz5zB29H5gSxNAQyNu", # Топ-трейдер (объем $74M+ за 7 дней) [citation:11][citation:14]
    "4HnnBQaVw6eP52wPzaePFWR4AcFjG5cTs2EckLtJ6d6C", # Топ-трейдер (объем $32M+) [citation:11][citation:14]
    "3cmf1r4gMfEkj87PjLSsjkhLsp1o6VXLRWSgaeeDrdan", # Топ-трейдер (объем $15M+) [citation:11][citation:14]
    "Em6d5nrTF7k3M3RKXLxGLs6r7Ed8wFa2GxRdaCyeVnTn", # Топ-трейдер (объем $14M+) [citation:11][citation:14]
    "9eLmSbNthkdJuXgo54XZqtXzexZD28HojTrf2N2g7g4", # Топ-трейдер (объем $12M+) [citation:11][citation:14]
    "bobf28kwimRKWTH3Qv7HvygHvqhgRuRax21z5fyTjdE", # Топ-трейдер (объем $11M+) [citation:11][citation:14]
    "CLoPSvbauaaSWs1teGgLnrHHf7FuJC3xtUsZP3KwuJsw", # Топ-трейдер (объем $9.8M+) [citation:11][citation:14]
    
    # === 4. КРУПНЫЕ СТЕЙКЕРЫ / ХОЛДЕРЫ ===
    "MJKqp326RZCHnAAbew9MDdui3iCKWco7fsK9sVuZTX2", # Топ-1 стейкер (5.1M SOL) [citation:1]
    "52C9T2T7JRojtxumYnYZhyUmrN7kqzvCLc4Ksvjk7TxD", # Топ-2 стейкер (4.3M SOL) [citation:1]
    "8BseXT9EtoEhBTKFFYkwTnjKSUZwhtmdKY2Jrj8j45Rt", # Топ-3 стейкер (3.9M SOL) [citation:1]
    "GitYucwpNcg6Dx1Y15UQ9TQn8LZMX1uuqQNn8rXxEWNC", # Kraken Staking [citation:1]
    "9QgXqrgdbVU8KcpfskqJpAXKzbaYQJecgMAruSWoXDkM", # Топ-5 стейкер (3.1M SOL) [citation:1]
    
    # === 5. АКТИВНЫЕ ТРЕЙДЕРЫ (Из Dune) ===
    "41zCUJsKk6cMB94DDtm99qWmyMZfp4GkAhhuz4xTwePu", # Огромный поток ($5.9B+) [citation:6]
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9", # Крупный поток ($2.8B+) [citation:6]
    "3ADzk5YDP9sgorvPSs9YPxigJiSqhgddpwHwwPwmEFib"  # Крупный поток ($2B+) [citation:6]
]

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

async def get_sol_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT') as resp:
                data = await resp.json()
                return float(data['price'])
    except Exception:
        return 85.0

async def send_telegram_notification(action, wallet, amount, time):
    if not BOT_TOKEN or not SUPABASE_URL:
        return
        
    indicator = "🟢" if action == "BUY" else "🔴"
    header = "КИТ ЗАКУПИЛСЯ!" if action == "BUY" else "КИТ ПРОДАЛ!"
        
    text = (
        f"{indicator} <b>{header}</b>\n\n"
        f"Действие: {action}\n"
        f"Сумма: ${amount:,.2f}\n"
        f"Кошелек: <code>{wallet}</code>\n"
        f"Время: {time}\n"
        f"Сеть: Solana"
    )
    
    # Ищем только АКТИВНЫХ пользователей, чей фильтр подходит под сумму
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
            
            if not users:
                print(f"Сделка на ${amount:.2f} не попала в фильтры активных пользователей.")
                return
                
            for user in users:
                chat_id = user['chat_id']
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                }
                await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
                
        print(f"Уведомление разослано {len(users)} пользователям (сделка ${amount:.2f})")
    except Exception as e:
        print(f"Ошибка рассылки: {e}")

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
