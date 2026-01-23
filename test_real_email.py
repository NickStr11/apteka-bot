"""Test product extraction from real email."""
import imaplib
import email
from email.header import decode_header
import sys
sys.path.insert(0, 'src')

from parsers import parse_html
from extractors import extract_phone, extract_order_number, extract_products, extract_total, format_products_for_notification

HOST = "imap.gmail.com"
USER = "lovelykimura832@gmail.com"
PASSWORD = "ztrv pndd qslg jtsh"
FROM_FILTERS = ["s1963@yandex.ru", "nsv11061992@gmail.com"]

def decode_header_str(header):
    if not header:
        return ""
    decoded = []
    for part, enc in decode_header(header):
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)

print("Connecting...")
mail = imaplib.IMAP4_SSL(HOST)
mail.login(USER, PASSWORD)
mail.select("INBOX")

for sender in FROM_FILTERS:
    _, messages = mail.search(None, f'(FROM "{sender}")')
    for num in messages[0].split():
        _, msg_data = mail.fetch(num, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        
        subj = decode_header_str(msg.get("Subject"))
        
        all_text = subj + "\n"
        
        for part in msg.walk():
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                
                if ctype == "text/html":
                    all_text += parse_html(payload.decode(charset, errors="replace"))
                elif ctype == "text/plain":
                    all_text += payload.decode(charset, errors="replace")
            except:
                pass
        
        print("="*60)
        print("РЕЗУЛЬТАТ ПАРСИНГА:")
        print("="*60)
        
        phone = extract_phone(all_text)
        order = extract_order_number(all_text)
        products = extract_products(all_text)
        total_pharm, total_client = extract_total(all_text)
        
        print(f"📱 Телефон: {phone or '❌'}")
        print(f"🔢 Заказ: {order or '❌'}")
        print(f"\n📦 Товары ({len(products)} шт):")
        
        for p in products:
            print(f"   • {p.name[:40]} x{p.quantity} = {p.total_client:.0f}₽")
        
        print(f"\n💰 Итого: {total_client:.0f}₽")
        
        print("\n" + "="*60)
        print("ТЕКСТ ДЛЯ УВЕДОМЛЕНИЯ:")
        print("="*60)
        notification = f"Заказ №{order} готов!\n\n"
        notification += format_products_for_notification(products, total_client)
        print(notification)

mail.logout()
