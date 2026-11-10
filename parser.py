import asyncio
import json
import os
import websockets
from aiohttp import web

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

WHALE_WALLETS = [
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", 
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"  
]

# --- ВЕБ-СЕРВЕР ДЛЯ ОБМАНА RENDER ---
async def handle(request):
    return web.Response(text="ExTracker Parser is running...")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port} (для обмана Render)")

# --- ЛОГИКА ПАРСЕРА ---
async def listen_to_whales():
    if not HELIUS_API_KEY:
        print("ОШИБКА: HELIUS_API_KEY не найден!")
        return

    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    print("Запуск парсера. Подключение к Helius...")

    async with websockets.connect(ws_url) as websocket:
        subscribe_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "transactionSubscribe",
            "params": [
                {
                    "accountInclude": WHALE_WALLETS,
                    "vote": False,
                    "failed": False
                },
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "maxSupportedTransactionVersion": 1
                }
            ]
        }
        
        await websocket.send(json.dumps(subscribe_message))
        print("Подписка отправлена. Ожидание транзакций...")

        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]
                    signature = tx["signature"]
                    print(f"\n--- НОВАЯ ТРАНЗАКЦИЯ КИТА ---")
                    print(f"Подпись: {signature}")
                    print(f"Слот: {tx['slot']}")
            except websockets.exceptions.ConnectionClosed:
                print("Соединение с Helius закрыто. Переподключение...")
                break
            except Exception as e:
                print(f"Ошибка: {e}")

async def main():
    asyncio.create_task(start_web_server())
    while True:
        try:
            await listen_to_whales()
        except Exception as e:
            print(f"Критическая ошибка: {e}. Перезапуск через 5 секунд...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
