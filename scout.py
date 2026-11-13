import asyncio
import aiohttp
import os
from datetime import datetime

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Токены для сканирования
TOKENS = [
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", # WIF
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", # BONK
    "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"  # POPCAT
]

async def get_traders_from_dexscreener(session, token_ca):
    # Получаем список пар для токена
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_ca}"
    try:
        async with session.get(url) as resp:
            if resp.status != 200: return []
            data = await resp.json()
            if not data.get("pairs"): return []
            
            # Берем самую ликвидную пару
            pair = sorted(data["pairs"], key=lambda x: x.get("liquidity", {}).get("usd", 0) or 0, reverse=True)[0]
            pair_addr = pair.get("pairAddress")
            if not pair_addr: return []

            # Запрашиваем последние транзакции по этой паре
            tx_url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_addr}"
            async with session.get(tx_url) as tx_resp:
                if tx_resp.status != 200: return []
                tx_data = await tx_resp.json()
                
                # В DexScreener API нет прямого списка адресов покупателей, 
                # поэтому мы возвращаем пустой список (этот API не подходит для скаута)
                return []
    except Exception as e:
        print(f"Ошибка DexScreener: {e}")
        return []

# Так как DexScreener не дает список кошельков, 
# мы используем запасной вариант: генерируем фейковый список (для теста)
# В реальности нужен платный API (Birdeye) или парсинг через Helius.
async def mock_scout():
    print("⚠️ Внимание: Бесплатные API не дают список топ-трейдеров.")
    print("⚠️ Для реального поиска китов нужен платный API Birdeye или Helius.")
    print("✅ Скрипт завершен (без добавления китов).")

async def main():
    print("🚀 УМНЫЙ РАЗВЕДЧИК ЗАПУЩЕН...")
    async with aiohttp.ClientSession() as session:
        await mock_scout()

if __name__ == "__main__":
    asyncio.run(main())
