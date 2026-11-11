import asyncio
import json
import os
import sys
import time
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime

# Подключаем библиотеку для работы с TON
from pytoniq_core import Address, Cell, begin_cell, Slice

sys.stdout.reconfigure(line_buffering=True)

_raw_supabase = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = _raw_supabase.replace("/rest/v1/", "").replace("/rest/v1", "").rstrip("/")

SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
TON_API_KEY = os.getenv("TON_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- КЭШ ЦЕН И ТОКЕНОВ ---
price_cache = {"TON": 0.0, "SOL": 0.0, "last_update": 0}
jetton_cache = {} 

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
                print(f"💰 Цены обновлены: TON=${price_cache['TON']:.3f}, SOL=${price_cache['SOL']:.2f}")
    except Exception as e:
        print(f"Ошибка получения цен: {e}")

async def get_jetton_info(jetton_master):
    if jetton_master in jetton_cache:
        return jetton_cache[jetton_master]
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://tonapi.io/v2/jettons/{jetton_master}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    symbol = data.get("metadata", {}).get("symbol", "TOKEN")
                    decimals = data.get("metadata", {}).get("decimals", 9)
                    price = data.get("dex_usd_price", 0.0)
                    if price and price > 0:
                        jetton_cache[jetton_master] = (symbol, decimals, price)
                        return symbol, decimals, price
    except: pass
    return None, 9, 0.0

# --- ПАРСИНГ JETTON ИЗ BOC ---
def parse_jetton_transfer(body_boc_base64):
    try:
        # Декодируем base64 в Cell
        cell = Cell.from_boc_base64(body_boc_base64)
        slice_data = cell.begin_parse()
        
        # Проверяем op-code (0x0f8a7ea5 для transfer, 0x178d4519 для internal_transfer)
        op_code = slice_data.load_uint(32)
        
        if op_code == 0x0f8a7ea5: # Jetton Transfer
            query_id = slice_data.load_uint(64)
            amount = slice_data.load_coins()
            destination = slice_data.load_address()
            response_destination = slice_data.load_address()
            custom_payload = slice_data.load_ref()
            forward_ton_amount = slice_data.load_coins()
            forward_payload = slice_data.load_ref()
            
            # В forward_payload обычно лежит jetton_master
            # Но проще запросить инфу по адресу destination (который и есть jetton_master)
            return str(destination), amount
    except Exception as e:
        pass
    return None, 0

async def handle(request): return web.Response(text="ExTracker Parser is running...")

async def start_web_server():
    app = web.Application(); app.router.add_get('/', handle)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port); await site.start()

async def save_to_db(wallet, action, amount, token="SOL", network="Solana"):
    if amount <= 0: return
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    data = {"wallet": wallet, "action": action, "amount": amount, "token": token, "network": network}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 201: print(f"✅ Сохранено: {wallet[:8]}... ${amount:.2f} ({token})")
                else: print(f"❌ Ошибка БД: {resp.status}")
    except Exception as e: print(f"Ошибка записи: {e}")

async def send_telegram_notification(action, wallet, amount, time, token_symbol, network):
    if not BOT_TOKEN or not SUPABASE_URL: return
    indicator = "🟢" if action == "BUY" else "🔴"
    header = "КИТ ЗАКУПИЛСЯ!" if action == "BUY" else "КИТ ПРОДАЛ!"
    text = f"{indicator} <b>{header}</b>\n\nДействие: {action}\nТокен: {token_symbol}\nСеть: {network}\nСумма: ${amount:,.2f}\nКошелек: <code>{wallet}</code>\nВремя: {time}"
    
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
                if not isinstance(users, list): return
                for u in users:
                    if u.get('chat_id'):
                        send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                        payload = {"chat_id": u['chat_id'], "text": text, "parse_mode": "HTML"}
                        await session.post(send_url, json=payload)
    except Exception as e: pass

# --- SOLANA ---
async def listen_to_solana():
    await update_prices()
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    WHALE_WALLETS_SOL = ["5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm", "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt"]
    
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "transactionSubscribe", "params": [{"accountInclude": WHALE_WALLETS_SOL, "vote": False, "failed": False}, {"commitment": "confirmed", "encoding": "jsonParsed", "transactionDetails": "full", "maxSupportedTransactionVersion": 1}]}))
        while True:
            try:
                data = json.loads(await ws.recv())
                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]["transaction"]
                    meta = tx.get("meta", {})
                    keys = tx["transaction"]["message"]["accountKeys"]
                    
                    token_name = "SOL"
                    post_token = meta.get("postTokenBalances", [])
                    if post_token and len(post_token) > 0:
                        token_name = "SPL_TOKEN" 

                    for i in range(len(keys)):
                        pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
                        if i < len(pre) and i < len(post):
                            diff = post[i] - pre[i]
                            if abs(diff) > 10_000_000_000: 
                                amount = (abs(diff) / 1_000_000_000) * price_cache["SOL"]
                                action = "BUY" if diff > 0 else "SELL"
                                wallet_addr = keys[i] if isinstance(keys[i], str) else keys[i].get("pubkey", "")
                                await save_to_db(wallet_addr, action, amount, token_name, "Solana")
                                await send_telegram_notification(action, wallet_addr, amount, datetime.now().strftime("%H:%M:%S"), token_name, "Solana")
            except Exception as e: 
                print(f"Solana WS error: {e}")
                break

# --- TON ---
TON_WHALE_WALLETS = [
    "EQA-02X0tU5AWxXcJDwa7oWMXzSjacjaFiHBZ6VNEswMj3Vw", "EQAI7sfVjEv0ywHV2SbP-9bhdDJ8-Z0k1BpxM0WleeP2PxTW",
    "EQAL1QRD508kA3pYrYaLID7Xr5wBtBy-lwlF5oUKneP2PxTW", "EQAM3pli9yMP4bb1AkmEQ5tQksm_ymQ8K23fC3K7dlZzq_qU",
    "EQA_cc5tIQ4haNbMVFUD1d0bNRt17S7wgWEqfP_xEaTACLUB", "EQAf4vJc2TgGKH5CGFd6uHNIHLI4qLO7UICMqG4SttVxAhpY"
]

async def listen_to_ton():
    await update_prices()
    print("TON парсер запущен...")
    processed_txs = set()
    
    while True:
        for wallet in TON_WHALE_WALLETS:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://toncenter.com/api/v2/getTransactions?address={wallet}&limit=5&api_key={TON_API_KEY}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok") and data.get("result"):
                                for tx in data["result"]:
                                    tx_hash = tx.get("transaction_id", {}).get("hash")
                                    if tx_hash in processed_txs: continue
                                    
                                    utime = int(tx.get("utime", 0))
                                    if int(datetime.now().timestamp()) - utime > 300: continue
                                    
                                    in_msg = tx.get("in_msg", {})
                                    
                                    # 1. Обычный TON
                                    if isinstance(in_msg, dict) and int(in_msg.get("value", 0)) > 0:
                                        amount = (int(in_msg["value"]) / 1_000_000_000) * price_cache["TON"]
                                        if 10_000 < amount < 500_000:
                                            processed_txs.add(tx_hash)
                                            await save_to_db(wallet, "BUY", amount, "TON", "TON")
                                            await send_telegram_notification("BUY", wallet, amount, datetime.now().strftime("%H:%M:%S"), "TON", "TON")
                                    
                                    # 2. JETTON
                                    if isinstance(in_msg, dict) and "msg_data" in in_msg:
                                        msg_data = in_msg.get("msg_data", {})
                                        body = msg_data.get("body", "")
                                        if body:
                                            jetton_master, jetton_amount = parse_jetton_transfer(body)
                                            if jetton_master:
                                                symbol, decimals, price = await get_jetton_info(jetton_master)
                                                if symbol and price > 0:
                                                    usd_amount = (jetton_amount / (10 ** decimals)) * price
                                                    if usd_amount > 1000:
                                                        processed_txs.add(tx_hash)
                                                        await save_to_db(wallet, "BUY", usd_amount, symbol, "TON")
                                                        await send_telegram_notification("BUY", wallet, usd_amount, datetime.now().strftime("%H:%M:%S"), symbol, "TON")
            except Exception as e:
                pass
        await asyncio.sleep(10)

async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(listen_to_solana())
    asyncio.create_task(listen_to_ton())
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
