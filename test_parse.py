"""Test email parsing with attachments."""
import imaplib
import email
from email.header import decode_header
import sys
sys.path.insert(0, 'src')

from parsers import parse_html, parse_pdf_bytes, parse_docx_bytes
from extractors import extract_phone, extract_order_number

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
        print(f"\n{'='*50}")
        print(f"📧 От: {sender}")
        print(f"📝 Тема: {subj}")
        print(f"{'='*50}")
        
        all_text = subj + "\n"
        
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                
                charset = part.get_content_charset() or "utf-8"
                
                if "attachment" in disp:
                    fname = part.get_filename() or ""
                    print(f"\n📎 Вложение: {fname}")
                    
                    if fname.lower().endswith(".pdf"):
                        text = parse_pdf_bytes(payload)
                        all_text += text
                        print(f"   📄 Извлечено {len(text)} символов")
                    elif fname.lower().endswith(".docx"):
                        text = parse_docx_bytes(payload)
                        all_text += text
                        print(f"   📄 Извлечено {len(text)} символов")
                        
                elif ctype == "text/plain":
                    text = payload.decode(charset, errors="replace")
                    all_text += text
                    print(f"\n📝 Текст письма:\n{text[:500]}...")
                    
                elif ctype == "text/html":
                    text = parse_html(payload.decode(charset, errors="replace"))
                    all_text += text
                    
            except Exception as e:
                print(f"   ⚠️ Ошибка: {e}")
        
        # Extract data
        phone = extract_phone(all_text)
        order = extract_order_number(all_text)
        
        print(f"\n{'='*50}")
        print("🔍 РЕЗУЛЬТАТ ПАРСИНГА:")
        print(f"   📱 Телефон: {phone or '❌ не найден'}")
        print(f"   🔢 Заказ: {order or '❌ не найден'}")
        print(f"{'='*50}")

mail.logout()
