import asyncio
import aiohttp
import os
from datetime import datetime
from aiohttp import web

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

async def handle(request): return web.Response(text="TEST PARSER IS RUNNING")
async def start_web_server():
    app = web.Application(); app.router.add_get('/', handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))); await site.start()
    print("✅ Веб-сервер запущен")

async def test_writer():
    print("🚀 ТЕСТОВЫЙ ПАРСЕР ЗАПУЩЕН!")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                url = f"{SUPABASE_URL}/rest/v1/whale_transactions"
                headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
                
                data = {
                    "wallet": "TEST_WALLET_123", 
                    "action": "BUY", 
                    "amount": 10000, 
                    "token": "TEST", 
                    "network": "Solana", 
                    "tx_hash": f"test_hash_{datetime.now().timestamp()}", 
                    "contract_address": "TEST_CA",
                    "created_at": datetime.now().isoformat()
                }
                
                async with session.post(url, headers=headers, json=data) as resp:
                    if resp.status in [200, 201]:
                        print(f"✅ ТЕСТОВАЯ ЗАПИСЬ ДОБАВЛЕНА В БАЗУ! (${data['amount']})")
                    else:
                        text = await resp.text()
                        print(f"❌ ОШИБКА БАЗЫ: {resp.status} - {text}")
            except Exception as e:
                print(f"❌ ОШИБКА СЕТИ: {e}")
            
            await asyncio.sleep(10)

async def main():
    await start_web_server()
    asyncio.create_task(test_writer())
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
