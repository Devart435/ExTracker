import asyncio
import json
import os
import sys
import time
import aiohttp
import html
from aiohttp import web
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)

# --- НАСТРОЙКИ ---
_raw_supabase = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = _raw_supabase.replace("/rest/v1/", "").replace("/rest/v1", "").rstrip("/")

SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
TON_API_KEY = os.getenv("TON_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ИСПРАВЛЕНО: правильный URL Vercel
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://extracker-eight.vercel.app")

# ID известных токенов
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

MIN_SWAP_USD_SOL = 15000
MIN_SWAP_USD_TON = 5000

# --- КЭШИ ---
price_cache = {"TON": 0.0, "SOL": 0.0, "last_update": 0}
jetton_cache = {}

# --- АНТИ-БОТ ---
blacklist = set()
swap_history = defaultdict(list)

# --- ЦЕНЫ ---
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
                print(f"💰 Цены: TON=${price_cache['TON']:.3f}, SOL=${price_cache['SOL']:.2f}")
    except Exception as e:
        print(f"Ошибка цен: {e}")

async def background_price_updater():
    while True:
        await update_prices()
        await asyncio.sleep(60)

# --- ИНФО О ТОКЕНЕ ---
async def get_jetton_info(mint_or_master):
    if mint_or_master in jetton_cache:
        return jetton_cache[mint_or_master]
    try:
        async with aiohttp.ClientSession() as session:
            if len(mint_or_master) >= 40:
                url = f"https://tokens.jup.ag/token/{mint_or_master}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        symbol = data.get("symbol", "TOKEN")
                        decimals = data.get("decimals", 9)
                        jetton_cache[mint_or_master] = (symbol, decimals, 0.0)
                        return symbol, decimals, 0.0
            else:
                url = f"https://tonapi.io/v2/jettons/{mint_or_master}"
                headers = {"Authorization": f"Bearer {TON_API_KEY}"} if TON_API_KEY else {}
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        symbol = data.get("metadata", {}).get("symbol", "TOKEN")
                        decimals = data.get("metadata", {}).get("decimals", 9)
                        price = data.get("dex_usd_price", 0.0)
                        if price and price > 0:
                            jetton_cache[mint_or_master] = (symbol, decimals, price)
                            return symbol, decimals, price
    except: pass
    return None, 9, 0.0

# --- ВЕБ-СЕРВЕР ---
async def handle(request): return web.Response(text="ExTracker Auto-Discovery is running...")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# --- АНТИ-БОТ ---
def is_mev_bot(wallet, network, swap_time):
    key = f"{network}:{wallet}"
    if key in blacklist:
        return True
    history = swap_history[key]
    history.append(swap_time)
    history = [t for t in history if swap_time - t < 10]
    swap_history[key] = history
    if len(history) > 2:
        blacklist.add(key)
        print(f"🚫 Blacklist (MEV): {wallet[:8]}...")
        return True
    return False

# --- SUPABASE ---
async def save_swap_to_db(wallet, action, amount_usd, token_symbol, network, tx_hash, contract_address=""):
    if amount_usd <= 0: return
    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    data = {
        "wallet": wallet,
        "action": action,
        "amount": round(amount_usd, 2),
        "token": token_symbol,
        "network": network,
        "tx_hash": tx_hash,
        "contract_address": contract_address,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 201:
                    print(f"✅ DB: {wallet[:8]}... ${amount_usd:,.2f} ({token_symbol})")
                else:
                    print(f"❌ DB Error: {resp.status} - {await resp.text()}")
    except Exception as e:
        print(f"DB Exception: {e}")

# --- TELEGRAM ALERT ---
async def send_telegram_alert(wallet, action, amount_usd, token_symbol, network, tx_hash, contract_address=""):
    if not BOT_TOKEN: return
    
    safe_token = html.escape(str(token_symbol))
    
    indicator = "🟢" if action == "BUY" else "🔴"
    entry_type = "Fresh Entry" if action == "BUY" else "Сброс позиции"
    explorer = f"https://solscan.io/tx/{tx_hash}" if network == "Solana" else f"https://tonviewer.com/transaction/{tx_hash}"
    chart = f"https://dexscreener.com/solana/{contract_address}" if network == "Solana" else f"https://dexscreener.com/ton/{contract_address}"
    
    text = (
        f"{indicator} <b>{action} • {network}</b> | <i>{entry_type}</i>\n\n"
        f"Токен: <b>{safe_token}</b>\n"
        f"Сумма: <b>${amount_usd:,.2f}</b>\n"
        f"CA: <code>{contract_address or wallet}</code>\n\n"
        f"<a href=\"{explorer}\">Открыть транзакцию</a> • <a href=\"{chart}\">График</a>"
    )
    
    if network == "Solana":
        buy_buttons = [
            {"text": "Купить: Trojan", "url": f"https://t.me/solana_trojanbot?start={contract_address}"},
            {"text": "Купить: BullX", "url": f"https://t.me/BullXBot?start={contract_address}"}
        ]
    else:  # TON
        buy_buttons = [
            {"text": "Купить: Blum", "url": f"https://t.me/blum/app?startapp={contract_address}"},
            {"text": "Свап: STON.fi", "url": f"https://app.ston.fi/swap?jetton={contract_address}"}
        ]
    
    keyboard_rows = [buy_buttons]
    if WEBAPP_URL:
        keyboard_rows.append([
            {"text": "Открыть в ExTracker", "web_app": {"url": WEBAPP_URL}},
            {"text": "Скрыть кита", "callback_data": f"mute_whale:{wallet}"}
        ])
    else:
        keyboard_rows.append([
            {"text": "Скрыть кита", "callback_data": f"mute_whale:{wallet}"}
        ])
    
    kb = {"inline_keyboard": keyboard_rows}
    
    url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount_usd}&max_amount=gte.{amount_usd}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                users = await resp.json()
                if not isinstance(users, list): return
                for u in users:
                    if u.get('chat_id'):
                        await session.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": u['chat_id'],
                                "text": text,
                                "parse_mode": "HTML",
                                "disable_web_page_preview": True,
                                "reply_markup": kb
                            }
                        )
                        await asyncio.sleep(1)
    except Exception as e:
        print(f"TG Error: {e}")

# --- SOLANA ---
async def process_solana_batch(session, signatures):
    if not signatures: return
    url = f"https://api.helius.xyz/v0/transactions/?api-key={HELIUS_API_KEY}"
    try:
        async with session.post(url, json={"transactions": signatures}) as resp:
            if resp.status != 200:
                print(f"Helius Batch Error: {resp.status}")
                return
            txs = await resp.json()
            for tx in txs:
                if tx.get("type") != "SWAP": continue
                
                fee_payer = tx.get("feePayer")
                if not fee_payer: continue
                
                total_usd = 0.0
                token_in = None
                token_out = None
                contract_address = ""
                
                for nt in tx.get("nativeTransfers", []):
                    from_acc = nt.get("fromUserAccount", "")
                    to_acc = nt.get("toUserAccount", "")
                    if from_acc != fee_payer and to_acc != fee_payer: continue
                    
                    amt_sol = abs(nt.get("amount", 0)) / 1e9
                    if amt_sol < 0.05: continue
                    
                    if from_acc == fee_payer:
                        token_in = "SOL"
                        total_usd += amt_sol * price_cache["SOL"]
                    elif to_acc == fee_payer:
                        token_out = "SOL"
                        total_usd += amt_sol * price_cache["SOL"]
                
                for tt in tx.get("tokenTransfers", []):
                    from_acc = tt.get("fromUserAccount", "")
                    to_acc = tt.get("toUserAccount", "")
                    if from_acc != fee_payer and to_acc != fee_payer: continue
                    
                    mint = tt.get("mint", "")
                    amt = tt.get("tokenAmount", 0)
                    
                    if mint == USDC_MINT:
                        if from_acc == fee_payer: token_in = "USDC"
                        elif to_acc == fee_payer: token_out = "USDC"
                        total_usd += amt
                        contract_address = USDC_MINT
                    elif mint == USDT_MINT:
                        if from_acc == fee_payer: token_in = "USDT"
                        elif to_acc == fee_payer: token_out = "USDT"
                        total_usd += amt
                        contract_address = USDT_MINT
                    else:
                        sym, dec, prc = await get_jetton_info(mint)
                        usd_val = amt * prc if prc > 0 else 0
                        if usd_val > total_usd:
                            total_usd = usd_val
                        if from_acc == fee_payer: token_in = sym or "SPL"
                        elif to_acc == fee_payer: token_out = sym or "SPL"
                        contract_address = mint
                
                if total_usd < MIN_SWAP_USD_SOL: continue
                if is_mev_bot(fee_payer, "Solana", time.time()): continue
                
                stable_tokens = {"SOL", "USDC", "USDT"}
                if token_in in stable_tokens and token_out not in stable_tokens:
                    action = "BUY"
                    token_symbol = token_out or "UNKNOWN"
                elif token_in not in stable_tokens and token_out in stable_tokens:
                    action = "SELL"
                    token_symbol = token_in or "UNKNOWN"
                else:
                    action = "BUY"
                    token_symbol = token_out or token_in or "UNKNOWN"
                
                await save_swap_to_db(fee_payer, action, total_usd, token_symbol, "Solana", tx.get("signature", ""), contract_address)
                await send_telegram_alert(fee_payer, action, total_usd, token_symbol, "Solana", tx.get("signature", ""), contract_address)
                
    except Exception as e:
        print(f"Solana Batch Exception: {e}")

async def listen_to_solana():
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    
    signature_queue = []
    last_batch_time = time.time()
    BATCH_SIZE = 20
    BATCH_INTERVAL = 4
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.ws_connect(ws_url) as ws:
                    await ws.send_json({
                        "jsonrpc": "2.0", "id": 1,
                        "method": "logsSubscribe",
                        "params": [{"mentions": [JUPITER_PROGRAM]}, {"commitment": "confirmed"}]
                    })
                    print("Solana (Jupiter) слушаем...")
                    
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT: continue
                        data = json.loads(msg.data)
                        if "params" not in data: continue
                        
                        log = data["params"]["result"]
                        signature = log.get("signature")
                        if signature:
                            signature_queue.append(signature)
                        
                        if len(signature_queue) >= BATCH_SIZE or (time.time() - last_batch_time > BATCH_INTERVAL and signature_queue):
                            await process_solana_batch(session, signature_queue[:BATCH_SIZE])
                            signature_queue = signature_queue[BATCH_SIZE:]
                            last_batch_time = time.time()
            except Exception as e:
                print(f"Solana WS Reconnect: {e}")
                await asyncio.sleep(3)

# --- TON ---
async def listen_to_ton():
    print("TON (TonAPI) слушаем...")
    url = "https://tonapi.io/v2/sse/transactions?accounts=ALL&operations=StonfiSwap,JettonSwap"
    headers = {"Authorization": f"Bearer {TON_API_KEY}"} if TON_API_KEY else {}
    
    event_queue = asyncio.Queue()
    
    async def process_event_worker():
        while True:
            event_id = await event_queue.get()
            try:
                await asyncio.sleep(1.1)
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://tonapi.io/v2/events/{event_id}", headers=headers) as resp:
                        if resp.status != 200:
                            event_queue.task_done()
                            continue
                        event = await resp.json()
                        
                        for action in event.get("actions", []):
                            if action.get("type") != "JettonSwap": continue
                            swap = action.get("JettonSwap", {})
                            if not swap: continue
                            
                            user_wallet = swap.get("user_wallet", {}).get("address")
                            if not user_wallet: continue
                            
                            total_usd = 0.0
                            token_symbol = "TON"
                            contract_address = ""
                            
                            if swap.get("ton_in"):
                                amt_ton = int(swap["ton_in"]) / 1e9
                                total_usd += amt_ton * price_cache["TON"]
                                token_symbol = "TON"
                            if swap.get("ton_out"):
                                amt_ton = int(swap["ton_out"]) / 1e9
                                total_usd += amt_ton * price_cache["TON"]
                                token_symbol = "TON"
                            
                            if swap.get("jetton_master_in"):
                                contract_address = swap["jetton_master_in"].get("address", "")
                                sym, dec, prc = await get_jetton_info(contract_address)
                                if sym: token_symbol = sym
                            elif swap.get("jetton_master_out"):
                                contract_address = swap["jetton_master_out"].get("address", "")
                                sym, dec, prc = await get_jetton_info(contract_address)
                                if sym: token_symbol = sym
                            
                            if total_usd < MIN_SWAP_USD_TON: continue
                            if is_mev_bot(user_wallet, "TON", time.time()): continue
                            
                            action_type = "BUY" if swap.get("ton_in") else "SELL"
                            
                            await save_swap_to_db(user_wallet, action_type, total_usd, token_symbol, "TON", event.get("event_id", ""), contract_address)
                            await send_telegram_alert(user_wallet, action_type, total_usd, token_symbol, "TON", event.get("event_id", ""), contract_address)
            except Exception as e:
                print(f"TON Event Error: {e}")
            finally:
                event_queue.task_done()
    
    asyncio.create_task(process_event_worker())
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line.startswith(b'data: '):
                                try:
                                    data = json.loads(line[6:])
                                    event_id = data.get("event_id")
                                    if event_id:
                                        await event_queue.put(event_id)
                                except json.JSONDecodeError:
                                    pass
                    else:
                        print(f"TON SSE Error: {resp.status}")
                        await asyncio.sleep(5)
        except Exception as e:
            print(f"TON SSE Connection: {e}")
            await asyncio.sleep(5)

# --- ЗАПУСК ---
async def main():
    print("🚀 ExTracker Auto-Discovery запущен")
    await asyncio.gather(
        start_web_server(),
        background_price_updater(),
        listen_to_solana(),
        listen_to_ton()
    )

if __name__ == "__main__":
    asyncio.run(main())
