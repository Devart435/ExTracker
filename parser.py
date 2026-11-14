import asyncio
import json
import os
import time
import sys
import websockets
import aiohttp
from aiohttp import web
from datetime import datetime, timezone
from collections import deque

sys.stdout.reconfigure(line_buffering=True)

# --- НАСТРОЙКИ ---
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
TON_API_KEY = os.getenv("TON_API_KEY")
TONAPI_KEY = os.getenv("TONAPI_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Порог сделки (временно $1000 для тестов)
MIN_SWAP_USD = int(os.getenv("MIN_SWAP_USD", "1000"))

session = None
SOLANA_WHALES = []
TON_WHALES = []
price_cache = {"TON": 0.0, "SOL": 0.0, "last_update": 0}

seen_tx = deque(maxlen=10000)
seen_tx_set = set()
token_cache = {}

metrics = {
    "solana_events": 0,
    "solana_saved": 0,
    "ton_events": 0,
    "ton_saved": 0,
    "errors": 0,
    "started_at": datetime.now(timezone.utc).isoformat(),
}

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)

def is_seen(tx_hash: str) -> bool:
    return tx_hash in seen_tx_set

def mark_seen(tx_hash: str):
    if tx_hash in seen_tx_set:
        return
    if len(seen_tx) == seen_tx.maxlen:
        old = seen_tx[0]
        seen_tx_set.discard(old)
    seen_tx.append(tx_hash)
    seen_tx_set.add(tx_hash)

async def update_prices():
    global price_cache
    if time.time() - price_cache["last_update"] < 60:
        return
    try:
        async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT") as r_ton, \
                   session.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT") as r_sol:
            data_ton = await r_ton.json()
            data_sol = await r_sol.json()
            price_cache["TON"] = float(data_ton["price"])
            price_cache["SOL"] = float(data_sol["price"])
            price_cache["last_update"] = time.time()
            log(f"💰 Цены: TON=${price_cache['TON']:.3f}, SOL=${price_cache['SOL']:.2f}")
    except Exception as e:
        metrics["errors"] += 1
        log(f"⚠️ Ошибка цен: {e}")

async def get_token_ticker(contract_address: str) -> str:
    cached = token_cache.get(contract_address)
    if cached and time.time() - cached["ts"] < 3600:
        return cached["symbol"]
    try:
        async with session.get(f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}") as r:
            if r.status == 200:
                data = await r.json()
                if data.get("pairs"):
                    symbol = data["pairs"][0].get("baseToken", {}).get("symbol", "UNKNOWN")
                    token_cache[contract_address] = {"symbol": symbol, "ts": time.time()}
                    return symbol
            elif r.status == 429:
                log("⚠️ DexScreener rate limit")
    except Exception as e:
        log(f"⚠️ DexScreener error: {e}")
    return "UNKNOWN"

async def load_whales_from_db():
    global SOLANA_WHALES, TON_WHALES
    log("🔄 Загружаем китов из базы...")
    url = f"{SUPABASE_URL}/rest/v1/tracked_whales?select=address,network"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                SOLANA_WHALES = list(set([w["address"] for w in data if w["network"] == "Solana"]))
                TON_WHALES = list(set([w["address"] for w in data if w["network"] == "TON"]))
                log(f"✅ В базе: {len(SOLANA_WHALES)} Solana, {len(TON_WHALES)} TON")
            else:
                log(f"⚠️ load_whales HTTP {resp.status}")
    except Exception as e:
        metrics["errors"] += 1
        log(f"❌ Ошибка БД: {e}")

async def save_to_db(wallet, action, amount_usd, token, network, tx_hash, ca=""):
    await update_prices()
    
    # ДЕБАГ: видим, что пришло на вход
    log(f"🔍 save_to_db: {network} {wallet[:6]}… {action} ${amount_usd:.2f} {token}")

    if amount_usd < MIN_SWAP_USD:
        log(f"🔍 отсев по сумме: ${amount_usd:.2f} < ${MIN_SWAP_USD}")
        return
    if is_seen(tx_hash):
        return
    mark_seen(tx_hash)

    url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }
    data = {
        "wallet": wallet,
        "action": action,
        "amount": round(amount_usd, 2),
        "token": token,
        "network": network,
        "tx_hash": tx_hash,
        "contract_address": ca,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status in (200, 201, 204):
                log(f"✅ СОХРАНЕНО: {network} {wallet[:6]}… {action} {token} ${amount_usd:.2f}")
                if network == "Solana":
                    metrics["solana_saved"] += 1
                else:
                    metrics["ton_saved"] += 1
                await send_telegram_alert(action, wallet, amount_usd, token, network)
            elif resp.status == 409:
                pass
            else:
                metrics["errors"] += 1
                log(f"⚠️ save_to_db HTTP {resp.status}: {await resp.text()}")
    except Exception as e:
        metrics["errors"] += 1
        log(f"❌ Ошибка БД: {e}")

async def send_telegram_alert(action, wallet, amount, token, network):
    if not BOT_TOKEN:
        return
    indicator = "🟢" if action == "BUY" else "🔴"
    text = (
        f"{indicator} <b>КИТ {action}</b>\n\n"
        f"Токен: ${token}\nСеть: {network}\n"
        f"Сумма: ${amount:,.2f}\nКошелек: <code>{wallet}</code>"
    )
    base_url = f"{SUPABASE_URL}/rest/v1/users?is_active=eq.true&min_amount=lte.{amount}&max_amount=gte.{amount}&select=chat_id"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

    all_users = []
    offset = 0
    while True:
        page_url = f"{base_url}&limit=1000&offset={offset}"
        try:
            async with session.get(page_url, headers=headers) as resp:
                if resp.status != 200:
                    break
                chunk = await resp.json()
                if not chunk:
                    break
                all_users.extend(chunk)
                if len(chunk) < 1000:
                    break
                offset += 1000
        except Exception as e:
            log(f"⚠️ alert fetch: {e}")
            break

    for u in all_users:
        chat_id = u.get("chat_id")
        if not chat_id:
            continue
        try:
            await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
        except Exception as e:
            log(f"⚠️ alert send {chat_id}: {e}")

async def listen_to_solana():
    await update_prices()
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    enhanced_url = f"https://api.helius.xyz/v0/transactions/?api-key={HELIUS_API_KEY}"

    while True:
        if not SOLANA_WHALES:
            await asyncio.sleep(30)
            await load_whales_from_db()
            continue
        try:
            log("🔌 Подключаемся к WebSocket Helius…")
            async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                sub_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [{"mentions": SOLANA_WHALES}, {"commitment": "confirmed"}],
                }
                await ws.send(json.dumps(sub_msg))
                log(f"👀 Solana: следим за {len(SOLANA_WHALES)} китами")

                async for message in ws:
                    metrics["solana_events"] += 1
                    try:
                        data = json.loads(message)
                        if "params" not in data or "result" not in data["params"]:
                            continue
                        logs = data["params"]["result"]
                        if logs.get("err"):
                            continue
                        signature = logs.get("signature")
                        if not signature:
                            continue
                        if is_seen(signature):
                            continue

                        payload = {"transactions": [signature]}
                        async with session.post(enhanced_url, json=payload) as r:
                            if r.status != 200:
                                continue
                            tx_data = await r.json()
                            if not tx_data or not isinstance(tx_data, list):
                                continue
                            tx = tx_data[0]
                            tx_type = tx.get("type")
                            source = tx.get("source")

                            if tx_type not in ["SWAP", "AGGREGATOR_SWAP"]:
                                continue
                            if source in ["JITO", "SYSTEM_PROGRAM"]:
                                continue

                            account_data = tx.get("accountData", [])
                            wallet = tx.get("feePayer")
                            sol_diff = 0
                            for acc in account_data:
                                if acc.get("account") == wallet:
                                    sol_diff = acc.get("nativeBalanceChange", 0) / 1_000_000_000
                                    break

                            usd_amount = abs(sol_diff) * price_cache["SOL"]
                            action = "BUY" if sol_diff < 0 else "SELL"

                            if usd_amount < MIN_SWAP_USD:
                                continue

                            token_ticker = "SOL"
                            token_ca = ""
                            for t in tx.get("tokenTransfers", []):
                                if t.get("mint") and t["mint"] != "So11111111111111111111111111111111111111112":
                                    token_ca = t["mint"]
                                    token_ticker = await get_token_ticker(token_ca)
                                    break

                            if token_ca:
                                await save_to_db(wallet, action, usd_amount, token_ticker, "Solana", signature, token_ca)
                    except Exception as e:
                        metrics["errors"] += 1
                        log(f"⚠️ Solana обработка: {e}")
        except Exception as e:
            metrics["errors"] += 1
            log(f"❌ Solana WS: {e}. Перезапуск через 10 сек…")
            await asyncio.sleep(10)

async def listen_to_ton():
    await update_prices()
    headers = {"Authorization": f"Bearer {TONAPI_KEY}", "Accept": "application/json"} if TONAPI_KEY else {}

    while True:
        if not TON_WHALES:
            await asyncio.sleep(30)
            await load_whales_from_db()
            continue

        batch_size = 5
        for i in range(0, len(TON_WHALES), batch_size):
            batch = TON_WHALES[i : i + batch_size]
            for wallet in batch:
                try:
                    url = f"https://tonapi.io/v2/accounts/{wallet}/events?limit=5"
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 429:
                            log("⚠️ TonAPI rate limit → пауза 60 сек")
                            await asyncio.sleep(60)
                            break
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        for event in data.get("events", []):
                            metrics["ton_events"] += 1
                            
                            if event.get("in_progress") is not False:
                                log(f"🔍 TON event in_progress: {event.get('event_id','')[:12]}")
                                continue
                                
                            actions = event.get("actions", [])
                            if not actions:
                                log(f"🔍 TON event без actions: {event.get('event_id','')[:12]}")
                                continue
                                
                            for action in actions:
                                if "JettonSwap" not in action.get("type", ""):
                                    # ДЕБАГ: если это не свап, пишем тип
                                    log(f"🔍 TON action не Swap: {action.get('type')}")
                                    continue

                                swap = action.get("JettonSwap", {})
                                
                                # --- НОВАЯ ЛОГИКА BUY/SELL ---
                                # Если jetton_master_in ЕСТЬ — значит кит отдал токен, получил TON = SELL
                                # Если jetton_master_out ЕСТЬ — значит кит отдал TON, получил токен = BUY
                                jetton_in = swap.get("jetton_master_in")
                                jetton_out = swap.get("jetton_master_out")
                                
                                # Сумма в TON (наноTON)
                                ton_amount = 0.0
                                if swap.get("amount_in") and not jetton_in:
                                    # amount_in в TON (если на входе был TON)
                                    ton_amount = float(swap.get("amount_in", "0")) / 1e9
                                elif swap.get("amount_out") and not jetton_out:
                                    # amount_out в TON (если на выходе был TON)
                                    ton_amount = float(swap.get("amount_out", "0")) / 1e9
                                
                                # Если не смогли определить TON-объем, берем что есть
                                if ton_amount == 0:
                                    try:
                                        ton_amount = float(swap.get("amount_in", "0") or 0) / 1e9
                                        if ton_amount == 0:
                                            ton_amount = float(swap.get("amount_out", "0") or 0) / 1e9
                                    except (ValueError, TypeError):
                                        pass

                                usd_amount = ton_amount * price_cache["TON"]

                                if usd_amount < MIN_SWAP_USD:
                                    log(f"🔍 TON отсев по сумме: ${usd_amount:.2f} < ${MIN_SWAP_USD} (event {event.get('event_id','')[:12]})")
                                    continue

                                if jetton_in:
                                    action_type = "SELL"
                                    token_info = jetton_in
                                elif jetton_out:
                                    action_type = "BUY"
                                    token_info = jetton_out
                                else:
                                    log(f"⚠️ TON: не определили сторону для {event.get('event_id', '')[:12]}")
                                    continue

                                tx_hash = event.get("event_id", "")
                                if not tx_hash or is_seen(tx_hash):
                                    continue

                                token_ticker = token_info.get("symbol", "UNKNOWN") if token_info else "TON"
                                token_ca = token_info.get("address", "") if token_info else ""

                                await save_to_db(wallet, action_type, usd_amount, token_ticker, "TON", tx_hash, token_ca)
                except Exception as e:
                    metrics["errors"] += 1
                    log(f"⚠️ TON {wallet[:6]}: {e}")
            await asyncio.sleep(1.5)
        await asyncio.sleep(15)

async def handle_health(request):
    return web.json_response(
        {
            "status": "ok",
            "uptime_since": metrics["started_at"],
            "solana_whales": len(SOLANA_WHALES),
            "ton_whales": len(TON_WHALES),
            "solana_events": metrics["solana_events"],
            "solana_saved": metrics["solana_saved"],
            "ton_events": metrics["ton_events"],
            "ton_saved": metrics["ton_saved"],
            "errors": metrics["errors"],
            "seen_tx_size": len(seen_tx_set),
            "price_sol": price_cache["SOL"],
            "price_ton": price_cache["TON"],
            "min_swap_usd": MIN_SWAP_USD,
        }
    )

async def handle_root(request):
    return web.Response(text="ExTracker Parser is running...")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()
    log("✅ Веб-сервер запущен (/ и /health)")

async def main():
    global session
    log("🚀 СТАРТ ПАРСЕРА…")
    log(f"⚙️ MIN_SWAP_USD = ${MIN_SWAP_USD} (env)")
    session = aiohttp.ClientSession()
    try:
        await start_web_server()
        await asyncio.sleep(2)
        await load_whales_from_db()
        asyncio.create_task(update_prices())
        asyncio.create_task(listen_to_solana())
        asyncio.create_task(listen_to_ton())

        while True:
            await asyncio.sleep(3600)
            await load_whales_from_db()
    finally:
        if session and not session.closed:
            await session.close()
            log("✅ HTTP-сессия закрыта")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("⛔ Остановлено вручную")
