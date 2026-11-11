import asyncio
import json
import os
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

_raw_supabase = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = _raw_supabase.replace("/rest/v1/", "").replace("/rest/v1", "").rstrip("/")

SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
TON_API_KEY = os.getenv("TON_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- SOLANA ---
WHALE_WALLETS = [
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", 
    "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm",
    "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt"
]

# --- TON ---
TON_WHALE_WALLETS = [
    "EQA-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQAI7sfVjEv0ywHV2SbP-9bhdDJ8-Z0k1BpxM0WleeP2PxTW",
    "EQAL1QRD508kA3pYrYaLID7Xr5wBtBy-lwlF5oUKneP2PxTW"
]

async def handle(request): return web.Response(text="ExTracker Parser is running...")

async def start_web_server():
    app = web.Application(); app.router.add_get('/', handle)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port); await site.start()
    print(f"Веб-сервер запущен на порту {port}")

async def get_sol_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT') as resp:
                data = await resp.json(); return float(data['price'])
    except: return 85.0

async def save_to_db(wallet, action, amount, token, network):
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    # Теперь мы сохраняем и токен, и сеть!
    data = {"wallet": wallet, "action": action, "amount": amount, "token": token, "network": network}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 201: print(f"✅ Сделка сохранена: {token} на ${amount:.2f} ({network})")
                else: print(f"❌ Ошибка БД: {resp.status}")
    except Exception as e: print(f"Ошибка записи: {e}")

async def send_telegram_notification(action, wallet, amount, time, token, network):
    if not BOT_TOKEN or not SUPABASE_URL: return
    indicator = "🟢" if action == "BUY" else "🔴"
    header = "КИТ ЗАКУПИЛСЯ!" if action == "BUY" else "КИТ ПРОДАЛ!"
    text = f"{indicator} <b>{header}</b>\n\nДействие: {action}\nМонета: {token}\nСумма: ${amount:,.2f}\nКошелек: <code>{wallet}</code>\nВремя: {time}\nСеть: {network}"
    
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
                if not isinstance(users, list): return
                for u in users:
                    if u.get('chat_id'):
                        await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": u['chat_id'], "text": text, "parse_mode": "HTML"})
    except Exception as e: print(f"Ошибка рассылки: {e}")

# --- SOLANA ПАРСЕР ---
async def listen_to_solana():
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    print("Solana парсер запущен...")
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "transactionSubscribe", "params": [{"accountInclude": WHALE_WALLETS, "vote": False, "failed": False}, {"commitment": "confirmed", "encoding": "jsonParsed", "transactionDetails": "full", "maxSupportedTransactionVersion": 1}]}))
        while True:
            try:
                data = json.loads(await ws.recv())
                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]["transaction"]
                    meta, keys = tx.get("meta", {}), tx["transaction"]["message"]["accountKeys"]
                    # Пытаемся вытащить название токена (если это не SOL)
                    token_name = "SOL" 
                    if "postTokenBalances" in meta and meta["postTokenBalances"]:
                        mint = meta["postTokenBalances"][0].get("mint")
                        if mint: token_name = f"Token({mint[:4]})" # Заглушка, для реальных имен нужен доп. API

                    for i in range(len(keys)):
                        pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
                        if i < len(pre) and i < len(post):
                            diff = post[i] - pre[i]
                            if abs(diff) > 1_000_000_000: # От 1 SOL
                                amount = (abs(diff) / 1_000_000_000) * await get_sol_price()
                                action = "BUY" if diff > 0 else "SELL"
                                await save_to_db(keys[i], action, amount, token_name, "Solana")
                                await send_telegram_notification(action, keys[i], amount, datetime.now().strftime("%H:%M:%S"), token_name, "Solana")
            except Exception as e: print(f"Solana Error: {e}"); break

# --- TON ПАРСЕР ---
async def listen_to_ton():
    print("TON парсер запущен...")
    while True:
        for wallet in TON_WHALE_WALLETS:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://toncenter.com/api/v2/getTransactions?address={wallet}&limit=1&api_key={TON_API_KEY}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok") and data.get("result"):
                                tx = data["result"][0]
                                if int(datetime.now().timestamp()) - int(tx.get("utime", 0)) < 300:
                                    in_msg = tx.get("in_msg", {})
                                    if isinstance(in_msg, dict) and int(in_msg.get("value", 0)) > 0:
                                        amount = (int(in_msg["value"]) / 1_000_000_000) * 5.5 # Примерный курс TON
                                        if amount > 10:
                                            print(f"TON Сделка: {amount:.2f}$")
                                            # В TON API сложно достать название Jetton (токена), пишем TON
                                            await save_to_db(wallet, "BUY", amount, "TON", "TON") 
                                            await send_telegram_notification("BUY", wallet, amount, datetime.now().strftime("%H:%M:%S"), "TON", "TON")
            except Exception: pass
        await asyncio.sleep(15)

async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(listen_to_solana())
    asyncio.create_task(listen_to_ton())
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
