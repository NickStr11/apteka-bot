"""Quick test of email connection with multiple senders."""
import imaplib

HOST = "imap.gmail.com"
USER = "lovelykimura832@gmail.com"
PASSWORD = "ztrv pndd qslg jtsh"
FROM_FILTERS = ["s1963@yandex.ru", "nsv11061992@gmail.com"]

print(f"Connecting to {HOST}...")
try:
    mail = imaplib.IMAP4_SSL(HOST)
    mail.login(USER, PASSWORD)
    print("✅ Login successful!")
    
    mail.select("INBOX")
    
    total = 0
    for sender in FROM_FILTERS:
        _, messages = mail.search(None, f'(FROM "{sender}")')
        count = len(messages[0].split()) if messages[0] else 0
        print(f"📧 {sender}: {count} писем")
        total += count
    
    print(f"\n📊 Всего: {total} писем от обоих адресов")
    
    if total > 0:
        print("✅ Готово к работе!")
    else:
        print("⚠️ Отправь тестовое письмо с одного из адресов.")
    
    mail.logout()
except Exception as e:
    print(f"❌ Error: {e}")
