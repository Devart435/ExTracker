import asyncio
import json
import os
import websockets
import aiohttp
from supabase import create_client, Client

# Ключи из переменных окружения Render
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

# Подключаемся к Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# РЕАЛЬНЫЕ АДРЕСА АКТИВНЫХ КИТОВ (Маркет-мейкеры и фонды на Solana)
# Они совершают сделки каждый день, поэтому ты быстро увидишь результат
WHALE_WALLETS = [
    "5sTQ5ih7xtctBhMXHr3f1aWdaXazWrWfoehqWdqWnTFP", # Wintermute
    "GXbJWY8H5YwvhrRYZvSWUAcGMGjR7ygUkQNwZxefgzdm", # Jump Trading
    "HwDkuDCUipJHHKodBBCjffFvrjhmd4iVVh7fq25fShvt", # DWF Labs
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", # Крупный холдер
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS"  # Активный трейдер
]

# Функция для получения реального курса SOL к USD с Binance
async def get_sol_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT') as resp:
                data = await resp.json()
                return float(data['price'])
    except Exception as e:
        print(f"Ошибка получения курса: {e}")
        return 85.0 # Запасной курс, если Binance недоступен

async def listen_to_whales():
    if not HELIUS_API_KEY or not SUPABASE_URL:
        print("ОШИБКА: Не хватает ключей в переменных окружения!")
        return

    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    print("Запуск парсера с реальным курсом. Подключение к Helius...")

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
        print("Подписка отправлена. Ждем реальные сделки...")

        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)

                if data.get("method") == "transactionNotification":
                    tx = data["params"]["result"]
                    signature = tx["signature"]
                    transaction = tx["transaction"]
                    
                    # === ЛОГИКА ВЫЧИСЛЕНИЯ РЕАЛЬНОЙ СУММЫ И КОШЕЛЬКА ===
                    meta = transaction.get("meta", {})
                    pre_balances = meta.get("preBalances", [])
                    post_balances = meta.get("postBalances", [])
                    account_keys = transaction["transaction"]["message"]["accountKeys"]
                    
                    for i in range(len(account_keys)):
                        if i < len(pre_balances) and i < len(post_balances):
                            diff = post_balances[i] - pre_balances[i]
                            
                            # Если изменение баланса больше 1 SOL (1_000_000_000 лампортов)
                            if abs(diff) > 1_000_000_000: 
                                amount_sol = abs(diff) / 1_000_000_000
                                
                                # Получаем актуальный курс SOL
                                sol_price = await get_sol_price()
                                amount_usd = amount_sol * sol_price
                                
                                wallet = account_keys[i]
                                action = "BUY" if diff > 0 else "SELL"
                                
                                print(f"Найдена сделка: {action} на {amount_usd:.2f}$ (Курс SOL: {sol_price}$)")

                                # Сохраняем в Supabase
                                try:
                                    supabase.table("whale_transactions").insert({
                                        "wallet": wallet,
                                        "action": action,
                                        "amount": amount_usd,
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
