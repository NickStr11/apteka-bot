"""Test WhatsApp connection via Green-API."""
import httpx

INSTANCE_ID = "1103482032"
TOKEN = "bba3e83f5ed44671819b38a7465ad33a6407b03b0a934f0682"

# Check instance state
url = f"https://api.green-api.com/waInstance{INSTANCE_ID}/getStateInstance/{TOKEN}"

print("Проверяю подключение к WhatsApp...")
try:
    response = httpx.get(url, timeout=10)
    data = response.json()
    print(f"Статус: {data}")
    
    if data.get("stateInstance") == "authorized":
        print("✅ WhatsApp подключён и готов к отправке!")
    else:
        print("⚠️ WhatsApp не авторизован. Отсканируй QR-код в Green-API.")
except Exception as e:
    print(f"❌ Ошибка: {e}")
