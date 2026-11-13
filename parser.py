import asyncio
import json
import os
import time
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

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
SOLANA_WHALES = []
TON_WHALES = []
price_cache = {"TON": 0.0, "SOL": 0.0, "last_update": 0}
seen_tx = set()
token_cache = {}

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

async def load_whales_from_db():
    global SOLANA_WHALES, TON_WHALES
    print("🔄 Загружаем китов из базы...")
    url = f"{SUPABASE_URL}/rest/v1/tracked_whales?select=address,network"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                SOLANA_WHALES = list(set([w['address'] for w in data if w['network'] == 'Solana']))
                TON_WHALES = list(set([w['address'] for w in data if w['network'] == 'TON']))
                print(f"✅ В базе: {len(SOLANA_WHALES)} Solana китов, {len(TON_WHALES)} TON китов.")
    except Exception as e: print(f"❌ Ошибка БД: {e}")

async def save_to_db(wallet, action, amount_usd, token, network, tx_hash, ca=""):
    await update_prices()
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
    await update_prices()
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    enhanced_url = f"https://api.helius.xyz/v0/transactions/?api-key={HELIUS_API_KEY}"
    
    while True:
        if not SOLANA_WHALES:
            await asyncio.sleep(30); await load_whales_from_db(); continue
        try:
            print("🔌 Подключаемся к WebSocket Helius...")
            async with websockets.connect(ws_url, ping_interval=30) as ws:
                sub_msg = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": [{"mentions": SOLANA_WHALES}, {"commitment": "confirmed"}]}
                await ws.send(json.dumps(sub_msg))
                print(f"👀 Solana: Следим за {len(SOLANA_WHALES)} китами...")
                
                async for message in ws:
                    data = json.loads(message)
                    if "params" in data and "result" in data["params"]:
                        logs = data["params"]["result"]
                        if logs.get("err"): continue
                        signature = logs.get("signature")
                        if not signature: continue
                        
                        # Запрос к Enhanced API для умного парсинга
                        payload = {"transactions": [signature]}
                        async with session.post(enhanced_url, json=payload) as r:
                            tx_data = await r.json()
                            if not tx_data or not isinstance(tx_data, list): continue
                            
                            try:
                                tx = tx_data[0]
                                tx_type = tx.get("type")
                                source = tx.get("source")
                                
                                # 1. ЛОВИМ ТОЛЬКО СВАПЫ (ПОКУПКИ/ПРОДАЖИ)
                                if tx_type not in ["SWAP", "AGGREGATOR_SWAP"]:
                                    continue
                                
                                # 2. ОТСЕКАЕМ БОТОВ (JITO, SYSTEM_PROGRAM, TRANSFER)
                                if source in ["JITO", "SYSTEM_PROGRAM"]:
                                    continue
                                
                                # 3. СЧИТАЕМ СУММУ В USD
                                account_data = tx.get("accountData", [])
                                wallet = tx.get("feePayer")
                                sol_diff = 0
                                for acc in account_data:
                                    if acc.get("account") == wallet:
                                        sol_diff = acc.get("nativeBalanceChange", 0) / 1_000_000_000
                                        break
                                
                                usd_amount = abs(sol_diff) * price_cache["SOL"]
                                action = "BUY" if sol_diff < 0 else "SELL"
                                
                                if usd_amount < MIN_SWAP_USD: continue
                                
                                # 4. ИЩЕМ КУПЛЕННЫЙ/ПРОДАННЫЙ ТОКЕН
                                token_ticker = "SOL"
                                token_ca = ""
                                token_transfers = tx.get("tokenTransfers", [])
                                for t in token_transfers:
                                    if t.get("mint") and t.get("mint") != "So11111111111111111111111111111111111111112":
                                        token_ca = t.get("mint")
                                        token_ticker = await get_token_ticker(token_ca)
                                        break
                                
                                if token_ca:
                                    await save_to_db(wallet, action, usd_amount, token_ticker, "Solana", signature, token_ca)
                                    
                            except Exception as ex: pass
        except Exception as e:
            print(f"❌ Solana WS ошибка: {e}. Перезапуск...")
            await asyncio.sleep(10)

async def listen_to_ton():
    await update_prices()
    headers = {"Authorization": f"Bearer {TONAPI_KEY}", "Accept": "application/json"} if TONAPI_KEY else {}
    
    while True:
        if not TON_WHALES:
            await asyncio.sleep(30); await load_whales_from_db(); continue

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
                                            token_ticker = jetton_info.get("symbol", "UNKNOWN") if jetton_info else "TON"
                                            token_ca = jetton_info.get("address", "") if jetton_info else ""
                                            await save_to_db(wallet, "BUY", usd_amount, token_ticker, "TON", tx_hash, token_ca)
            except Exception as e: pass
        
        await asyncio.sleep(15)

async def handle(request): return web.Response(text="ExTracker Parser is running...")
async def start_web_server():
    app = web.Application(); app.router.add_get('/', handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))); await site.start()
    print("✅ Веб-сервер запущен")

async def main():
    global session
    print("🚀 СТАРТ УМНОГО ПАРСЕРА...")
    session = aiohttp.ClientSession()
    await start_web_server()
    await asyncio.sleep(2)
    await load_whales_from_db()
    asyncio.create_task(update_prices())
    asyncio.create_task(listen_to_solana())
    asyncio.create_task(listen_to_ton())
    
    while True:
        await asyncio.sleep(3600)
        await load_whales_from_db()

if __name__ == "__main__":
    asyncio.run(main())
