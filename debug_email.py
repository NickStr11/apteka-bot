"""Debug - show full extracted text."""
import imaplib
import email
from email.header import decode_header
import sys
sys.path.insert(0, 'src')

from parsers import parse_html

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
        
        print("="*60)
        print("ПОЛНЫЙ ТЕКСТ ПИСЬМА:")
        print("="*60)
        
        for part in msg.walk():
            ctype = part.get_content_type()
            
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                
                charset = part.get_content_charset() or "utf-8"
                
                if ctype == "text/html":
                    text = parse_html(payload.decode(charset, errors="replace"))
                    print(f"\n--- HTML ({len(text)} символов) ---")
                    print(text)
                elif ctype == "text/plain":
                    text = payload.decode(charset, errors="replace")
                    print(f"\n--- PLAIN TEXT ---")
                    print(text)
                    
            except Exception as e:
                print(f"Error: {e}")

mail.logout()
