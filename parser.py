import os
import time
import aiohttp
import asyncio
from datetime import datetime
from aiohttp import web

# --- ЯВНЫЙ ПРИНТ ПРИ СТАРТЕ ---
print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
print("!!! ФАЙЛ PARSER.PY ЗАГРУЖЕН И ЗАПУЩЕН !!!")
print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
print(f"URL базы: {SUPABASE_URL}")
print(f"Ключ базы (первые 5 символов): {SUPABASE_KEY[:5] if SUPABASE_KEY else 'НЕТ КЛЮЧА'}...")

async def handle(request): return web.Response(text="TEST PARSER IS RUNNING")

async def main():
    # 1. Запускаем веб-сервер
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Веб-сервер запущен на порту {port}")

    # 2. Бесконечный цикл записи (в главном потоке)
    print("🚀 НАЧИНАЮ ПИСАТЬ В БАЗУ...")
    
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
                        print(f"✅ УСПЕХ! Запись добавлена в базу.")
                    else:
                        text = await resp.text()
                        print(f"❌ ОШИБКА БАЗЫ: {resp.status} - {text}")
            except Exception as e:
                print(f"❌ ОШИБКА СЕТИ: {e}")
            
            print("Жду 10 секунд...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
