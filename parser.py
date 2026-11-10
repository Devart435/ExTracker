import asyncio
import json
import os
import websockets

# Берем ключ из переменных окружения Render (мы добавили его туда)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

# Список кошельков китов для отслеживания (для теста взял пару известных)
WHALE_WALLETS = [
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", # Пример адреса
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"  # Пример адреса
]

async def listen_to_whales():
    if not HELIUS_API_KEY:
        print("ОШИБКА: HELIUS_API_KEY не найден в переменных окружения!")
        return

    # URL для WebSocket подключения к Helius
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    
    print("Запуск парсера. Подключение к Helius...")

    async with websockets.connect(ws_url) as websocket:
        # Подписываемся на транзакции, где участвуют наши кошельки
        subscribe_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "transactionSubscribe",
            "params": [
                {
                    "accountInclude": WHALE_WALLETS, # Слушаем эти адреса
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

        # Бесконечно слушаем входящие сообщения
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)

                # Проверяем, что это уведомление о транзакции
                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]
                    signature = tx["signature"]
                    
                    # Тут можно добавить логику фильтрации по сумме,
                    # но для начала просто выведем факт транзакции
                    print(f"\n--- НОВАЯ ТРАНЗАКЦИЯ КИТА ---")
                    print(f"Подпись: {signature}")
                    print(f"Слот: {tx['slot']}")
                    # В реальном коде здесь мы бы парсили сумму и отправляли в БД

            except websockets.exceptions.ConnectionClosed:
                print("Соединение с Helius закрыто. Переподключение...")
                break
            except Exception as e:
                print(f"Ошибка: {e}")

async def main():
    # Бесконечный цикл для переподключения при обрыве связи
    while True:
        try:
            await listen_to_whales()
        except Exception as e:
            print(f"Критическая ошибка: {e}. Перезапуск через 5 секунд...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
