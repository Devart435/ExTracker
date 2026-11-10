import asyncio
import json
import os
import websockets
from supabase import create_client, Client

# Ключи из переменных окружения Render
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

# Подключаемся к Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

WHALE_WALLETS = [
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", 
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"  
]

async def listen_to_whales():
    if not HELIUS_API_KEY or not SUPABASE_URL:
        print("ОШИБКА: Не хватает ключей!")
        return

    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    print("Парсер запущен. Подключение к Helius...")

    async with websockets.connect(ws_url) as websocket:
        subscribe_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "transactionSubscribe",
            "params": [
                {"accountInclude": WHALE_WALLETS, "vote": False, "failed": False},
                {"commitment": "confirmed", "encoding": "jsonParsed", "transactionDetails": "full", "maxSupportedTransactionVersion": 1}
            ]
        }
        
        await websocket.send(json.dumps(subscribe_message))
        print("Подписка отправлена. Ждем сделки...")

        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)

                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]
                    signature = tx["signature"]
                    
                    # Временная заглушка для суммы
                    fake_amount = 150000 
                    wallet_address = "0x71C...8a9f" 

                    # Сохраняем в Supabase
                    try:
                        supabase.table("whale_transactions").insert({
                            "wallet": wallet_address,
                            "action": "BUY",
                            "amount": fake_amount,
                            "token": "SOL"
                        }).execute()
                        print(f"Сделка сохранена в БД: {signature[:10]}...")
                    except Exception as e:
                        print(f"Ошибка записи в Supabase: {e}")

            except websockets.exceptions.ConnectionClosed:
                print("Соединение закрыто. Переподключение...")
                break
            except Exception as e:
                print(f"Ошибка: {e}")

async def main():
    while True:
        try:
            await listen_to_whales()
        except Exception as e:
            print(f"Критическая ошибка: {e}. Перезапуск...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
