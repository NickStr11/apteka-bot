"""Send test WhatsApp message."""
import httpx

INSTANCE_ID = "1103482032"
TOKEN = "bba3e83f5ed44671819b38a7465ad33a6407b03b0a934f0682"
PHONE = "79086810960"

url = f"https://api.green-api.com/waInstance{INSTANCE_ID}/sendMessage/{TOKEN}"

message = """🏥 Тест системы уведомлений!

Заказ №MA-280706178 готов!

• КАРВЕДИЛОЛ КАНОН x2 = 267₽
• МЕТФОРМИН x1 = 152₽
• ПОЛОСКА САТЕЛЛИТ x1 = 532₽
• ТЕМПАЛГИН x1 = 248₽

Итого: 1199₽

Ждём вас в аптеке! 💊"""

payload = {
    "chatId": f"{PHONE}@c.us",
    "message": message
}

print(f"Отправляю сообщение на {PHONE}...")
try:
    response = httpx.post(url, json=payload, timeout=15)
    data = response.json()
    print(f"Ответ: {data}")
    
    if data.get("idMessage"):
        print("✅ Сообщение отправлено!")
    else:
        print(f"⚠️ Проблема: {data}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
