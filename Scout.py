import asyncio
import aiohttp
import os
import json

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Токены, за которыми следим (WIF, BONK, POPCAT, SOL, JUP)
TOKENS = [
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "So11111111111111111111111111111111111111112",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
]

async def fetch_top_traders(session, token_ca):
    # Запрос к бесплатному публичному API GMGN (аналог DexScreener)
    # (Эндпоинт может меняться, но логика такая)
    url = f"https://gmgn.ai/api/v1/token/top_traders?chain=sol&address={token_ca}"
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                # GMGN отдает список трейдеров в data['data']['trader_list']
                traders = data.get("data", {}).get("trader_list", [])
                return [t['address'] for t in traders if t.get('address')]
    except: pass
    return []

async def add_to_db(session, address):
    url = f"{SUPABASE_URL}/rest/v1/tracked_whales"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates"}
    data = {"address": address, "network": "Solana", "name": "Auto Scout"}
    try:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status in [200, 201]:
                return True
    except: pass
    return False

async def main():
    print("🚀 РАЗВЕДЧИК ЗАПУЩЕН...")
    async with aiohttp.ClientSession() as session:
        while True:
            new_whales_count = 0
            for token in TOKENS:
                traders = await fetch_top_traders(session, token)
                for addr in traders:
                    added = await add_to_db(session, addr)
                    if added: new_whales_count += 1
                await asyncio.sleep(2) # Пауза между запросами
            
            print(f"✅ Разведка окончена. Добавлено новых китов: {new_whales_count}")
            print("⏳ Ждем 24 часа...")
            await asyncio.sleep(86400)

if __name__ == "__main__":
    asyncio.run(main())
