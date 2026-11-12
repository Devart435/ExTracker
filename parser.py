import asyncio
import json
import os
import time
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

# --- НАСТРОЙКИ ---
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "a2ca2df25ac18a4002269b4ddd8fced26fd4f1d7b5fde89281e7c9400fe59501")
TON_API_KEY = os.getenv("TON_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Защита от лишних слешей в URL базы
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MIN_SWAP_USD = 5000

# --- СПИСОК КОШЕЛЬКОВ КИТОВ (для TON) ---
TON_WHALES = [
    "EQA-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQAI7sfVjEv0ywHV2SbP-9bhdDJ8-Z0k1BpxM0WleeP2PxTW"
]

price_cache = {"TON": 0.0, "SOL": 0.0, "last_update": 0}

async def update_prices():
    global price_cache
    if time.time() - price_cache["last_update"] < 60: return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT') as r_ton, \
                       session.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT') as r_sol:
                data_ton = await r_ton.json()
                data_sol = await r_sol.json()
                price_cache["TON"] = float(data_ton['price'])
                price_cache["SOL"] = float(data_sol['price'])
                price_cache["last_update"] = time.time()
                print(f"Цены: SOL=${price_cache['SOL']}, TON=${price_cache['TON']}")
    except Exception as e: print(f"Ошибка цен: {e}")

async def save_to_db(wallet, action, amount_usd, token, network, tx_hash, ca=""):
    if amount_usd < MIN_SWAP_USD: return
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    data = {"wallet": wallet, "action": action, "amount": round(amount_usd, 2), "token": token, "network": network, "tx_hash": tx_hash, "contract_address": ca, "created_at": datetime.now().isoformat()}
    
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, headers=headers, json=data)
            print(f"✅ Сохранено: {wallet[:6]}... {action} {token} ${amount_usd:.2f}")
            await send_telegram_alert(action, wallet, amount_usd, token, network)
    except Exception as e: print(f"Ошибка БД: {e}")

async def send_telegram_alert(action, wallet, amount, token, network):
    if not BOT_TOKEN: return
    indicator = "🟢" if action == "BUY" else "🔴"
    text = f"{indicator} <b>КИТ {action}</b>\n\nТокен: {token}\nСеть: {network}\nСумма: ${amount:,.2f}\nКошелек: <code>{wallet}</code>"
    
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
                for u in users:
                    if u.get('chat_id'):
                        await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": u['chat_id'], "text": text, "parse_mode": "HTML"})
    except Exception as e: print(f"Ошибка пуша: {e}")

async def listen_to_solana():
    await update_prices()
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=30) as ws:
                sub_msg = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": [{"mentions": [JUPITER_PROGRAM]}, {"commitment": "confirmed"}]}
                await ws.send(json.dumps(sub_msg))
                print("Solana: Подключено к Helius. Ждем свапы...")
                
                async for message in ws:
                    data = json.loads(message)
                    if "params" in data and "result" in data["params"]:
                        logs = data["params"]["result"]
                        if logs.get("err"): continue
                        
                        signature = logs.get("signature")
                        if not signature: continue
                        
                        # Проверяем, что это реальный свап
                        if any("swap" in log.lower() for log in logs.get("logs", [])):
                            # Делаем запрос к Helius, чтобы узнать реальную сумму сделки
                            async with aiohttp.ClientSession() as session:
                                rpc_payload = {
                                    "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                                    "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                                }
                                async with session.post(ws_url, json=rpc_payload) as r:
                                    tx_data = await r.json()
                                    try:
                                        meta = tx_data["result"]["meta"]
                                        pre_balances = meta["preBalances"]
                                        post_balances = meta["postBalances"]
                                        
                                        # Считаем разницу в SOL (перевод)
                                        diff_lamports = abs(post_balances[0] - pre_balances[0])
                                        sol_amount = diff_lamports / 1_000_000_000
                                        
                                        # Переводим в USD
                                        usd_amount = sol_amount * price_cache["SOL"]
                                        
                                        if usd_amount > MIN_SWAP_USD:
                                            # Достаем адрес того, кто сделал свап
                                            account_keys = tx_data["result"]["transaction"]["message"]["accountKeys"]
                                            wallet = account_keys[0]["pubkey"] if isinstance(account_keys[0], dict) else account_keys[0]
                                            
                                            # Определяем, покупка или продажа (упрощенно)
                                            action = "BUY" if post_balances[0] < pre_balances[0] else "SELL"
                                            
                                            await save_to_db(wallet, action, usd_amount, "SOL", "Solana", signature)
                                    except Exception as e:
                                        pass # Если транзакция сложная, пропускаем
                                        
        except Exception as e:
            print(f"Solana WS ошибка: {e}. Перезапуск через 5 сек...")
            await asyncio.sleep(5)

async def listen_to_ton():
    await update_prices()
    print("TON: Парсер запущен. Опрос кошельков...")
    
    while True:
        for wallet in TON_WHALES:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"X-API-Key": TON_API_KEY} if TON_API_KEY else {}
                    url = f"https://toncenter.com/api/v2/getTransactions?address={wallet}&limit=5"
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok") and data.get("result"):
                                for tx in data["result"]:
                                    if int(datetime.now().timestamp()) - int(tx.get("utime", 0)) > 300: continue
                                    in_msg = tx.get("in_msg", {})
                                    if isinstance(in_msg, dict) and int(in_msg.get("value", 0)) > 0:
                                        amount = (int(in_msg["value"]) / 1_000_000_000) * price_cache["TON"]
                                        if amount > MIN_SWAP_USD:
                                            tx_hash = tx.get("transaction_id", {}).get("hash", "")
                                            await save_to_db(wallet, "BUY", amount, "TON", "TON", tx_hash)
            except Exception as e:
                print(f"TON ошибка: {e}")
        
        await asyncio.sleep(10)

async def handle(request): return web.Response(text="ExTracker Parser is running...")
async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

async def main():
    await start_web_server()
    asyncio.create_task(update_prices())
    asyncio.create_task(listen_to_solana())
    asyncio.create_task(listen_to_ton())
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
