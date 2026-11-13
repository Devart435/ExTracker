import asyncio
import json
import os
import time
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

# Принудительный вывод логов
sys.stdout.reconfigure(line_buffering=True)

# --- НАСТРОЙКИ ---
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY") 
TON_API_KEY = os.getenv("TON_API_KEY")
TONAPI_KEY = os.getenv("TONAPI_KEY") 
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MIN_SWAP_USD = 5000
session = None

# --- 10 РЕАЛЬНЫХ КИТОВ SOLANA ---
SOLANA_WHALES = [
    "EYKNBYxK7kiEJMNiytbat18X8koug7GNHGLAqEZsFrGB", 
    "AwroU2o6sahxKS6xPG4by6zxg9hjiczHWp7CqsWmRion", 
    "GuRfuByNZoFb2TJKj3x6SZEwaZzt8rn2MG1PAgEzWizm", 
    "DevY6MwW43tUstcYDcs21FdzAUqrKBE2e54ETkWPUft2",
    "FHpcNSe6tb2n15bAdq4BkeYWGyZKFD7yLYrH92ng7wCT",
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", 
    "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm",
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS",
    "FWznbcNXWQuHTawe9RxvQ2LdCENssh12dsznf4RiouN5"
]

TON_WHALES = [
    "EQA-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw",
    "EQAI7sfVjEv0ywHV2SbP-9bhdDJ8-Z0k1BpxM0WleeP2PxTW"
]

price_cache = {"TON": 0.0, "SOL": 0.0, "last_update": 0}
seen_tx = set()
token_cache = {}
WRAPPED_SOL = "So11111111111111111111111111111111111111112"

async def update_prices():
    global price_cache
    if time.time() - price_cache["last_update"] < 60: return
    try:
        async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT') as r_ton, \
                   session.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT') as r_sol:
            data_ton = await r_ton.json()
            data_sol = await r_sol.json()
            price_cache["TON"] = float(data_ton['price'])
            price_cache["SOL"] = float(data_sol['price'])
            price_cache["last_update"] = time.time()
    except Exception as e: print(f"Ошибка цен: {e}")

async def get_token_ticker(contract_address):
    if contract_address in token_cache: return token_cache[contract_address]
    try:
        async with session.get(f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}") as r:
            if r.status == 200:
                data = await r.json()
                if data.get("pairs"):
                    symbol = data["pairs"][0].get("baseToken", {}).get("symbol", "UNKNOWN")
                    token_cache[contract_address] = symbol
                    return symbol
    except: pass
    return "UNKNOWN"

async def save_to_db(wallet, action, amount_usd, token, network, tx_hash, ca=""):
    if amount_usd < MIN_SWAP_USD or tx_hash in seen_tx: return
    seen_tx.add(tx_hash)
    if len(seen_tx) > 10000: seen_tx.clear()
    
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    data = {"wallet": wallet, "action": action, "amount": round(amount_usd, 2), "token": token, "network": network, "tx_hash": tx_hash, "contract_address": ca, "created_at": datetime.now().isoformat()}
    
    try:
        await session.post(url, headers=headers, json=data)
        print(f"✅ СОХРАНЕНО: {wallet[:6]}... {action} {token} ${amount_usd:.2f}")
        await send_telegram_alert(action, wallet, amount_usd, token, network)
    except Exception as e: print(f"❌ Ошибка БД: {e}")

async def send_telegram_alert(action, wallet, amount, token, network):
    if not BOT_TOKEN: return
    indicator = "🟢" if action == "BUY" else "🔴"
    text = f"{indicator} <b>КИТ {action}</b>\n\nТокен: ${token}\nСеть: {network}\nСумма: ${amount:,.2f}\nКошелек: <code>{wallet}</code>"
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with session.get(url, headers=headers) as resp:
            users = await resp.json()
            for u in users:
                if u.get('chat_id'):
                    await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": u['chat_id'], "text": text, "parse_mode": "HTML"})
    except: pass

async def listen_to_solana():
    print("➡️ Запуск слушателя Solana...")
    await update_prices()
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    rpc_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    
    while True:
        try:
            print("🔌 Подключаемся к WebSocket Helius...")
            async with websockets.connect(ws_url, ping_interval=30) as ws:
                sub_msg = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": [{"mentions": SOLANA_WHALES}, {"commitment": "confirmed"}]}
                await ws.send(json.dumps(sub_msg))
                print(f"👀 Solana: Подписка успешна! Следим за {len(SOLANA_WHALES)} китами...")
                
                async for message in ws:
                    data = json.loads(message)
                    if "params" in data and "result" in data["params"]:
                        logs = data["params"]["result"]
                        if logs.get("err"): continue
                        signature = logs.get("signature")
                        if not signature: continue
                        
                        print(f"🔔 Транзакция от кита! Hash: {signature[:10]}...")
                        
                        rpc_payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
                        async with session.post(rpc_url, json=rpc_payload) as r:
                            tx_data = await r.json()
                            try:
                                meta = tx_data["result"]["meta"]
                                if not meta: continue
                                pre_balances = meta["preBalances"]
                                post_balances = meta["postBalances"]
                                diff_lamports = abs(post_balances[0] - pre_balances[0])
                                sol_amount = diff_lamports / 1_000_000_000
                                usd_amount = sol_amount * price_cache["SOL"]
                                
                                if usd_amount > MIN_SWAP_USD:
                                    account_keys = tx_data["result"]["transaction"]["message"]["accountKeys"]
                                    wallet = account_keys[0]["pubkey"] if isinstance(account_keys[0], dict) else account_keys[0]
                                    action = "BUY" if post_balances[0] < pre_balances[0] else "SELL"
                                    
                                    token_ticker = "SOL"
                                    token_ca = ""
                                    if meta.get("postTokenBalances"):
                                        for tb in meta["postTokenBalances"]:
                                            if tb.get("owner") == wallet and tb.get("mint") != WRAPPED_SOL:
                                                if tb.get("uiTokenAmount", {}).get("uiAmount", 0) > 0:
                                                    token_ca = tb.get("mint")
                                                    token_ticker = await get_token_ticker(token_ca)
                                                    break
                                    
                                    if token_ca != "":
                                        await save_to_db(wallet, action, usd_amount, token_ticker, "Solana", signature, token_ca)
                                    else:
                                        print(f"ℹ️ Перевод SOL (${usd_amount:.2f}), пропускаем.")
                            except Exception as ex: 
                                print(f"⚠️ Ошибка парсинга: {ex}")
        except Exception as e:
            print(f"❌ Solana WS ошибка: {e}. Перезапуск через 10 сек...")
            await asyncio.sleep(10)

async def listen_to_ton():
    print("➡️ Запуск слушателя TON...")
    await update_prices()
    print(f"👀 TON: Следим за {len(TON_WHALES)} китами через TONAPI...")
    
    headers = {"Authorization": f"Bearer {TONAPI_KEY}", "Accept": "application/json"} if TONAPI_KEY else {}
    
    while True:
        for wallet in TON_WHALES:
            try:
                url = f"https://tonapi.io/v2/accounts/{wallet}/events?limit=5"
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for event in data.get("events", []):
                            if event.get("in_progress") == False and any("JettonSwap" in action.get("type", "") for action in event.get("actions", [])):
                                for action in event["actions"]:
                                    if "JettonSwap" in action.get("type", ""):
                                        ton_amount = float(action.get("JettonSwap", {}).get("amount_in", "0")) / 1e9
                                        if ton_amount == 0:
                                            ton_amount = float(action.get("JettonSwap", {}).get("amount_out", "0")) / 1e9
                                            
                                        usd_amount = ton_amount * price_cache["TON"]
                                        if usd_amount > MIN_SWAP_USD:
                                            tx_hash = event.get("event_id", "")
                                            jetton_info = action.get("JettonSwap", {}).get("jetton_master_in") or action.get("JettonSwap", {}).get("jetton_master_out")
                                            token_ticker = "TON"
                                            if jetton_info:
                                                token_ticker = jetton_info.get("symbol", "UNKNOWN")
                                                token_ca = jetton_info.get("address", "")
                                            else:
                                                token_ca = ""
                                            await save_to_db(wallet, "BUY", usd_amount, token_ticker, "TON", tx_hash, token_ca)
                    elif resp.status == 401:
                        print("❌ Ошибка TONAPI: Неверный ключ (401).")
                        await asyncio.sleep(60)
            except Exception as e:
                print(f"TON ошибка: {e}")
        
        await asyncio.sleep(15)

async def handle(request): return web.Response(text="ExTracker Parser is running...")
async def start_web_server():
    app = web.Application(); app.router.add_get('/', handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))); await site.start()
    print("✅ Веб-сервер запущен")

async def main():
    global session
    print("🚀 СТАРТ ПАРСЕРА...")
    session = aiohttp.ClientSession()
    await start_web_server()
    await asyncio.sleep(2)
    asyncio.create_task(update_prices())
    asyncio.create_task(listen_to_solana())
    asyncio.create_task(listen_to_ton())
    
    try:
        while True: await asyncio.sleep(3600)
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())
