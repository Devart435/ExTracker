import asyncio
import aiohttp
import os
import json

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Токены для сканирования (WIF, BONK, POPCAT, SOL, JUP)
TOKENS = [
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", # WIF
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", # BONK
    "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", # POPCAT
    "So11111111111111111111111111111111111111112",  # SOL
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"   # JUP
]

async def fetch_top_traders(session, token_ca):
    # Запрос к публичному API GMGN для получения топ-трейдеров по токену
    url = f"https://gmgn.ai/api/v1/token/top_traders?chain=sol&address={token_ca}&period=7d"
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                traders = data.get("data", {}).get("trader_list", [])
                smart_whales = []
                
                for t in traders:
                    addr = t.get('address')
                    pnl = t.get('profit', 0)
                    winrate = t.get('winrate', 0)
                    txs = t.get('total_txs', 0)
                    
                    # УМНЫЙ ФИЛЬТР:
                    # 1. Отсекаем ботов (Слишком высокий винрейт и много транзакций)
                    if winrate > 95 and txs > 5000:
                        print(f"🤖 Отсекаем бота: {addr[:6]}... (Winrate: {winrate}%, Txs: {txs})")
                        continue
                    
                    # 2. Отсекаем тех, кто в минусе (нам нужны только профитные)
                    if pnl < 1000: 
                        continue
                    
                    # 3. Отсекаем тех, у кого слишком мало транзакций (новички, случайно залетевшие)
                    if txs < 20:
                        continue

                    smart_whales.append(addr)
                
                return smart_whales
    except Exception as e:
        print(f"Ошибка запроса к GMGN: {e}")
    return []

async def add_to_db(session, address):
    url = f"{SUPABASE_URL}/rest/v1/tracked_whales"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates"}
    data = {"address": address, "network": "Solana", "name": "Smart Scout"}
    try:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status in [200, 201]:
                return True
    except: pass
    return False

async def main():
    print("🚀 УМНЫЙ РАЗВЕДЧИК ЗАПУЩЕН...")
    async with aiohttp.ClientSession() as session:
        new_whales_count = 0
        for token in TOKENS:
            traders = await fetch_top_traders(session, token)
            for addr in traders:
                added = await add_to_db(session, addr)
                if added: new_whales_count += 1
            await asyncio.sleep(2)
        
        print(f"✅ Разведка окончена. Добавлено новых китов: {new_whales_count}")
        print("Скрипт завершает работу.")

if __name__ == "__main__":
    asyncio.run(main())
