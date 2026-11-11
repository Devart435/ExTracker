import asyncio
import json
import os
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

# --- БЕЗОПАСНАЯ ЗАГРУЗКА URL ---
_raw_supabase = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = _raw_supabase.replace("/rest/v1/", "").replace("/rest/v1", "").rstrip("/")

SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
TON_API_KEY = os.getenv("TON_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

WHALE_WALLETS = [
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm",
    "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS", "3ka1q7z7XjGfKjJ8s9F5s4a3D2e1R4t5Y6u7I8o9P0a",
    "4b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w", "5c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x",
    "6d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y", "7e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z",
    "8f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a", "9g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b",
    "0h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c", "1i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d",
    "2j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e", "3k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f",
    "4l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g", "5m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h",
    "6n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i", "7o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j",
    "8p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k", "9q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l",
    "0r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m", "1s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m9n",
    "2t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m9n0o", "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa",
    "jTcKH6sMbMMrvroaqeuM1CFmESz5zB29H5gSxNAQyNu", "4HnnBQaVw6eP52wPzaePFWR4AcFjG5cTs2EckLtJ6d6C",
    "3cmf1r4gMfEkj87PjLSsjkhLsp1o6VXLRWSgaeeDrdan", "Em6d5nrTF7k3M3RKXLxGLs6r7Ed8wFa2GxRdaCyeVnTn",
    "9eLmSbNthkdJuXgo54XZqtXzexZD28HojTrf2N2g7g4", "bobf28kwimRKWTH3Qv7HvygHvqhgRuRax21z5fyTjdE",
    "CLoPSvbauaaSWs1teGgLnrHHf7FuJC3xtUsZP3KwuJsw", "41zCUJsKk6cMB94DDtm99qWmyMZfp4GkAhhuz4xTwePu",
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"
]

TON_WHALE_WALLETS = [
    "EQA-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw", "EQAI7sfVjEv0ywHV2SbP-9bhdDJ8-Z0k1BpxM0WleeP2PxTW",
    "EQAL1QRD508kA3pYrYaLID7Xr5wBtBy-lwlF5oUKneP2PxTW", "EQAM3pli9yMP4bb1AkmEQ5tQksm_ymQ8K23fC3K7dlZzq_qU",
    "EQA_cc5tIQ4haNbMVFUD1d0bNRt17S7wgWEqfP_xEaTACLUB", "EQAf4vJc2TgGKH5CGFd6uHNIHLI4qLO7UICMqG4SttVxAhpY",
    "EQAwYg4_Y9LnDJ_zSDCxEHs-BvpHZQM6GQ-2AZBnxeP2PxTW", "EQBDeq6wDuTBDkKUlXSfUBdbxz1z4v1nNX8vBOEgz2IA-IQS",
    "EQBFbbSCrAnX2XWOjSq2qnAx_GRdx2wZIFqrlk9D0-1mxHDN", "EQBI-wGVp_x0VFEjd7m9cEUD3tJ_bnxMSp0Tb9qz757ATEAM",
    "EQBIp_clMlDvZRtnYwgFQgVJI3iL7sOfV29aNR7IheP2PxTW", "EQBNL2W5KZuw3Y3FbrLdDfIdXdrYXQFfcGfDO3kig0EK8zxz",
    "EQBYXa21T03kSVvTa3dL8kz9tW5nts8Ht-nrBsjSa_6zJgwf", "EQCGXN12Cezmurk-BdzagP7bR1bp7GT-JrGDm8juleoVGzbI",
    "EQCLyZHP4Xe8fpchQz76O-_RmUhaVc_9BAoGyJrwJrcbz2eZ", "EQCSIMGBps_qzRG3uPYhON8bucyCtu0mYdL1-u4gSz77IBa3",
    "EQCY4M6TZYnOMnGBQlqi_nyeaIB1LeBFfGgP4uXQ1VWh", "EQDt2wDuTBDkKUlXSfUBdbxz1z4v1nNX8vBOEgz2IA-IQS",
    "EQD-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw", "EQE-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQF-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw", "EQG-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQH-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw", "EQI-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQJ-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw"
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

async def save_to_db(wallet, action, amount, token="SOL"):
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    data = {"wallet": wallet, "action": action, "amount": amount, "token": token}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 201: print(f"✅ Сделка сохранена: {wallet[:8]}... на ${amount:.2f}")
                else: print(f"❌ Ошибка БД: {resp.status}")
    except Exception as e: print(f"Ошибка записи: {e}")

async def send_telegram_notification(action, wallet, amount, time, token_symbol):
    if not BOT_TOKEN or not SUPABASE_URL: return
    indicator = "🟢" if action == "BUY" else "🔴"
    header = "КИТ ЗАКУПИЛСЯ!" if action == "BUY" else "КИТ ПРОДАЛ!"
    text = f"{indicator} <b>{header}</b>\n\nДействие: {action}\nСумма: ${amount:,.2f}\nКошелек: <code>{wallet}</code>\nВремя: {time}\nСеть: {token_symbol}"
    
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
                if not isinstance(users, list): return # Защита
                for u in users:
                    if u.get('chat_id'):
                        await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": u['chat_id'], "text": text, "parse_mode": "HTML"})
    except Exception as e: print(f"Ошибка рассылки: {e}")

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
                    for i in range(len(keys)):
                        pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
                        if i < len(pre) and i < len(post):
                            diff = post[i] - pre[i]
                            if abs(diff) > 1_000_000_000:
                                amount = (abs(diff) / 1_000_000_000) * await get_sol_price()
                                action = "BUY" if diff > 0 else "SELL"
                                await save_to_db(keys[i], action, amount, "SOL")
                                await send_telegram_notification(action, keys[i], amount, datetime.now().strftime("%H:%M:%S"), "Solana")
            except Exception as e: print(f"Solana Error: {e}"); break

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
                                        amount = (int(in_msg["value"]) / 1_000_000_000) * 5.5
                                        if amount > 10:
                                            print(f"TON Сделка: {amount:.2f}$")
                                            await save_to_db(wallet, "BUY", amount, "TON")
                                            await send_telegram_notification("BUY", wallet, amount, datetime.now().strftime("%H:%M:%S"), "TON")
            except Exception: pass
        await asyncio.sleep(15)

async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(listen_to_solana())
    asyncio.create_task(listen_to_ton())
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
