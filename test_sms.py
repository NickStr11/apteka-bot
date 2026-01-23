"""Test SMS Gateway."""
import asyncio
import base64
import httpx

API_KEY = "eyJhbGciOiJIUzM4NCJ9.eyJzdWIiOiJDbDNybHZFZ25GUTBGelNmdVJHb1Z4d3Jpa0MyIiwiZXhwIjoxNzY5NzA2OTQ1fQ.MM4zXF5S-BD4TGBqCBAT8Hargf-Ox3isYhafEs6AptAIOFTFk0ISdqR564gdnzAa"
PHONE = "+79086810960"

async def test_sms():
    url = "https://api.smstext.app/push"
    
    auth_string = f"apikey:{API_KEY}"
    auth_bytes = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Content-Type": "application/json",
    }
    
    message = "🏥 Тест SMS!\nЗаказ №MA-280706178 готов.\nИтого: 1199₽"
    
    payload = [{"mobile": PHONE, "text": message}]
    
    print(f"Отправляю SMS на {PHONE}...")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=30)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code == 200:
            print("✅ SMS отправлена!")
        else:
            print("❌ Ошибка отправки")

asyncio.run(test_sms())
