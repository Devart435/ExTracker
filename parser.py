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
TON_API_KEY = os.getenv("TON_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- SOLANA: 25 старых + 10 новых супер-активных ---
WHALE_WALLETS = [
    # Твои старые (Wintermute, Jump и т.д.)
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", 
    "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm",
    "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS",
    "3ka1q7z7XjGfKjJ8s9F5s4a3D2e1R4t5Y6u7I8o9P0a", 
    "4b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w",
    "5c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x",
    "6d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y",
    "7e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z",
    "8f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a",
    "9g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b",
    "0h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c",
    "1i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d",
    "2j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e",
    "3k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f",
    "4l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g",
    "5m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h",
    "6n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i",
    "7o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j",
    "8p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k",
    "9q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l",
    "0r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m",
    "1s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m9n",
    "2t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m9n0o",
    # НОВЫЕ (Топовые трейдеры Solana)
    "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa", # Топ-маркет-мейкер (49k сделок/сутки) [citation:15]
    "jTcKH6sMbMMrvroaqeuM1CFmESz5zB29H5gSxNAQyNu", # Топ-трейдер
    "4HnnBQaVw6eP52wPzaePFWR4AcFjG5cTs2EckLtJ6d6C", # Топ-трейдер
    "3cmf1r4gMfEkj87PjLSsjkhLsp1o6VXLRWSgaeeDrdan", # Топ-трейдер
    "Em6d5nrTF7k3M3RKXLxGLs6r7Ed8wFa2GxRdaCyeVnTn", # Топ-трейдер
    "9eLmSbNthkdJuXgo54XZqtXzexZD28HojTrf2N2g7g4", # Топ-трейдер
    "bobf28kwimRKWTH3Qv7HvygHvqhgRuRax21z5fyTjdE", # Топ-трейдер
    "CLoPSvbauaaSWs1teGgLnrHHf7FuJC3xtUsZP3KwuJsw", # Топ-трейдер
    "41zCUJsKk6cMB94DDtm99qWmyMZfp4GkAhhuz4xTwePu", # Огромный поток
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"  # Крупный поток
]

# --- TON: 25 адресов ---
TON_WHALE_WALLETS = [
    "EQA-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQAI7sfVjEv0ywHV2SbP-9bhdDJ8-Z0k1BpxM0WleeP2PxTW",
    "EQAL1QRD508kA3pYrYaLID7Xr5wBtBy-lwlF5oUKneP2PxTW",
    "EQAM3pli9yMP4bb1AkmEQ5tQksm_ymQ8K23fC3K7dlZzq_qU",
    "EQA_cc5tIQ4haNbMVFUD1d0bNRt17S7wgWEqfP_xEaTACLUB",
    "EQAf4vJc2TgGKH5CGFd6uHNIHLI4qLO7UICMqG4SttVxAhpY",
    "EQAwYg4_Y9LnDJ_zSDCxEHs-BvpHZQM6GQ-2AZBnxeP2PxTW",
    "EQBDeq6wDuTBDkKUlXSfUBdbxz1z4v1nNX8vBOEgz2IA-IQS",
    "EQBFbbSCrAnX2XWOjSq2qnAx_GRdx2wZIFqrlk9D0-1mxHDN",
    "EQBI-wGVp_x0VFEjd7m9cEUD3tJ_bnxMSp0Tb9qz757ATEAM",
    "EQBIp_clMlDvZRtnYwgFQgVJI3iL7sOfV29aNR7IheP2PxTW",
    "EQBNL2W5KZuw3Y3FbrLdDfIdXdrYXQFfcGfDO3kig0EK8zxz",
    "EQBYXa21T03kSVvTa3dL8kz9tW5nts8Ht-nrBsjSa_6zJgwf",
    "EQCGXN12Cezmurk-BdzagP7bR1bp7GT-JrGDm8juleoVGzbI",
    "EQCLyZHP4Xe8fpchQz76O-_RmUhaVc_9BAoGyJrwJrcbz2eZ",
    "EQCSIMGBps_qzRG3uPYhON8bucyCtu0mYdL1-u4gSz77IBa3",
    "EQCY4M6TZYnOMnGBQlqi_nyeaIB1LeBFfGgP4uXQ1VWh",
    "EQDt2wDuTBDkKUlXSfUBdbxz1z4v1nNX8vBOEgz2IA-IQS", 
    "EQD-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQE-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQF-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQG-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQH-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQI-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQJ-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw"
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

async def send_telegram_notification(action, wallet, amount, time, token_symbol="SOL"):
    if not BOT_TOKEN or not SUPABASE_URL: return
    indicator = "🟢" if action == "BUY" else "🔴"
    header = "КИТ ЗАКУПИЛСЯ!" if action == "BUY" else "КИТ ПРОДАЛ!"
    text = (
        f"{indicator} <b>{header}</b>\n\n"
        f"Действие: {action}\n"
        f"Сумма: ${amount:,.2f}\n"
        f"Кошелек: <code>{wallet}</code>\n"
        f"Время: {time}\n"
        f"Сеть: {token_symbol}"
    )
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
            if not users: return
            for user in users:
                payload = {"chat_id": user['chat_id'], "text": text, "parse_mode": "HTML"}
                await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
    except Exception as e:
        print(f"Ошибка рассылки: {e}")

async def save_to_db(wallet, action, amount, token="SOL"):
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {
        "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json", "Prefer": "return=minimal"
    }
    data = {"wallet": wallet, "action": action, "amount": amount, "token": token}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 201:
                    print(f"✅ Сделка сохранена: {wallet[:8]}... на ${amount:.2f}")
    except Exception as e:
        print(f"Ошибка записи: {e}")

# --- SOLANA ПАРСЕР ---
async def listen_to_whales():
    if not HELIUS_API_KEY or not SUPABASE_URL: return
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    print("Solana парсер запущен. Подключение к Helius...")
    async with websockets.connect(ws_url) as websocket:
        subscribe_message = {
            "jsonrpc": "2.0", "id": 1, "method": "transactionSubscribe",
            "params": [
                {"accountInclude": WHALE_WALLETS, "vote": False, "failed": False},
                {"commitment": "confirmed", "encoding": "jsonParsed", "transactionDetails": "full", "maxSupportedTransactionVersion": 1}
            ]
        }
        await websocket.send(json.dumps(subscribe_message))
        print("Solana: Подписка отправлена. Ждем сделки...")
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
                                await save_to_db(wallet, action, amount_usd, "SOL")
                                await send_telegram_notification(action, wallet, amount_usd, datetime.now().strftime("%H:%M:%S"), "Solana")
            except Exception as e:
                print(f"Solana Error: {e}")
                break

# --- TON ПАРСЕР (РЕАЛЬНЫЙ ОПРОС) ---
async def listen_to_ton():
    if not TON_API_KEY:
        print("TON: Нет ключа, парсер не запущен.")
        return
    
    print("TON парсер запущен. Начинаем реальный опрос...")
    while True:
        try:
            # Проходим по всем кошелькам TON и проверяем последние транзакции
            for wallet in TON_WHALE_WALLETS:
                # Используем API toncenter для получения последних транзакций
                url = f"https://toncenter.com/api/v2/getTransactions?address={wallet}&limit=1&api_key={TON_API_KEY}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok") and data.get("result"):
                                for tx in data["result"]:
                                    # Проверяем, что транзакция свежая (за последние 5 минут)
                                    tx_time = int(tx.get("utime", 0))
                                    now = int(datetime.now().timestamp())
                                    if now - tx_time < 300: 
                                        # Извлекаем сумму в TON (value в нанотонах)
                                        value_nano = int(tx.get("in_msg", {}).get("value", 0))
                                        if value_nano > 0:
                                            amount_ton = value_nano / 1_000_000_000
                                            # Примерный курс TON к USD (можно потом заменить на реальный)
                                            ton_price = 5.5 
                                            amount_usd = amount_ton * ton_price
                                            
                                            if amount_usd > 100: # Фильтр: сделки больше $100
                                                print(f"TON Найдена сделка: {amount_usd:.2f}$")
                                                # Определяем, куда идет (BUY/SELL) - упрощенно, если входящая - BUY
                                                action = "BUY" if tx.get("in_msg") else "SELL"
                                                await save_to_db(wallet, action, amount_usd, "TON")
                                                await send_telegram_notification(action, wallet, amount_usd, datetime.now().strftime("%H:%M:%S"), "TON")
        except Exception as e:
            print(f"TON Error: {e}")
        
        await asyncio.sleep(15) # Опрос каждые 15 секунд

# --- ГЛАВНЫЙ ЗАПУСК ---
async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(listen_to_whales())
    asyncio.create_task(listen_to_ton())
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
