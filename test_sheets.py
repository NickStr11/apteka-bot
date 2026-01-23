"""Test Google Sheets connection."""
import sys
sys.path.insert(0, 'src')

from database.sheets import get_client, get_sheet, add_order, OrderRow
from datetime import datetime

CREDENTIALS_PATH = "photo-gallery-484020-c9d57645a635.json"

print("Подключаюсь к Google Sheets...")

try:
    client = get_client(CREDENTIALS_PATH)
    print("✅ Авторизация успешна!")
    
    sheet = get_sheet(client)
    print(f"✅ Таблица открыта: {sheet.title}")
    
    # Add test order
    test_order = OrderRow(
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        order_number="MA-280706178",
        phone="+79886689915",
        products="КАРВЕДИЛОЛ x2, МЕТФОРМИН x1, ПОЛОСКА x1, ТЕМПАЛГИН x1",
        total=1199.0,
        wa_status="",
        sms_status="",
        sent="",
        note="Тестовый заказ",
    )
    
    row_num = add_order(sheet, test_order)
    print(f"✅ Тестовый заказ добавлен в строку {row_num}")
    print("\n🎉 Проверь таблицу в браузере!")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
