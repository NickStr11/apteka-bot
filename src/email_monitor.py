"""Email monitoring and processing via IMAP."""

import asyncio
import email
import imaplib
import sys
from dataclasses import dataclass
from datetime import datetime, date
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import AsyncIterator

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from parsers import parse_html, parse_pdf_bytes, parse_docx_bytes
from extractors import extract_phone, extract_order_number
import re
from bs4 import BeautifulSoup


@dataclass
class EmailContent:
    """Parsed email content."""
    subject: str
    sender: str
    body_text: str
    attachments_text: str
    raw_body: str


@dataclass
class OrderData:
    """Extracted order data."""
    order_number: str | None
    phone: str | None
    products: list[str]  # List of product names
    total: float  # Total sum
    source_subject: str


def decode_email_header(header: str | None) -> str:
    """Decode email header to string."""
    if not header:
        return ""
    
    decoded_parts = []
    for part, encoding in decode_header(header):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    
    return " ".join(decoded_parts)


def extract_text_from_email(msg: Message) -> tuple[str, str, str]:
    """
    Extract text from email message.
    
    Returns:
        Tuple of (plain_text_body, html_converted_body, attachments_text)
    """
    plain_text = ""
    html_text = ""
    attachments_text = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Skip multipart containers
            if content_type.startswith("multipart/"):
                continue
            
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                
                # Determine charset
                charset = part.get_content_charset() or "utf-8"
                
                # Handle attachments
                if "attachment" in content_disposition:
                    filename = part.get_filename() or ""
                    filename_lower = filename.lower()
                    
                    if filename_lower.endswith(".pdf"):
                        attachments_text += f"\n--- {filename} ---\n"
                        attachments_text += parse_pdf_bytes(payload)
                    elif filename_lower.endswith(".docx"):
                        attachments_text += f"\n--- {filename} ---\n"
                        attachments_text += parse_docx_bytes(payload)
                    elif filename_lower.endswith((".txt", ".csv")):
                        attachments_text += f"\n--- {filename} ---\n"
                        attachments_text += payload.decode(charset, errors="replace")
                
                # Handle inline content
                elif content_type == "text/plain":
                    plain_text += payload.decode(charset, errors="replace")
                elif content_type == "text/html":
                    html_text += parse_html(payload.decode(charset, errors="replace"))
                    
            except Exception:
                continue
    else:
        # Single part message
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            
            if content_type == "text/html":
                html_text = parse_html(text)
            else:
                plain_text = text
    
    return plain_text, html_text, attachments_text


def parse_katren_email(html_content: str) -> tuple[str | None, list[str], float]:
    """
    Parse Katren/apteka.ru email to extract phone, products, and total.
    
    Returns:
        Tuple of (phone, products_list, total)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    phone = None
    products = []
    total = 0.0
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        
        # Extract phone - look for "Телефон клиента:" pattern with mobile number
        # Mobile numbers start with +7 or 8, followed by 9xx (mobile prefix)
        phone_match = re.search(
            r'Телефон\s*клиента[:\s]*\+?([78]?\d{10})', 
            text, 
            re.IGNORECASE
        )
        if phone_match:
            phone = phone_match.group(1)
            # Normalize to 7XXXXXXXXXX format
            phone = re.sub(r'[\s\-\(\)]', '', phone)
            if phone.startswith('8') and len(phone) == 11:
                phone = '7' + phone[1:]
            elif len(phone) == 10:
                phone = '7' + phone
        
        # Extract products from table - look for rows with product data
        tables = soup.find_all('table')
        logger.info(f"📧 Found {len(tables)} tables in email")
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    first_cell_text = cells[0].get_text(strip=True)
                    # Skip headers and summary rows
                    skip_words = ['ТОВАР', 'ИТОГО', 'ИТОГО:', 'НАИМЕНОВАНИЕ', 'НАЗВАНИЕ', 'СУММА', 'ПРОИЗВОДИТЕЛЬ', 'КОЛ-ВО', 'ЦЕНА']
                    if any(w in first_cell_text.upper() for w in skip_words):
                        continue
                    # Skip empty or very short cells
                    if len(first_cell_text) < 5:
                        continue
                    # Check if it looks like a product:
                    # - Has Latin brand name (BIODERMA, VICHY, etc)
                    # - OR has Cyrillic letters
                    # - AND has drug measurements (МЛ, МГ, N60, ТАБЛ, КАПС, etc)
                    is_brand = bool(re.search(r'[A-Z]{3,}', first_cell_text))  # Latin brand
                    is_cyrillic = bool(re.search(r'[А-Яа-яЁё]{3,}', first_cell_text))  # Cyrillic
                    # Extended patterns: 1000МЛ, 500МГ, N60, №60, ТАБЛ, КАПС, etc
                    # Also match special product types and dosage forms
                    has_measure = bool(re.search(
                        r'(\d+[,.]?\d*\s*(МЛ|МГ|ШТ|Г|ML|MG)|N\d+|№\d+|ТАБЛ|КАПС|ОБОЛОЧ|КРЕМ|ГЕЛЬ|МАЗЬ|Р-Р|СИРОП|ПАКЕТ|ПОР|СУПП|СВЕЧИ|ДРАЖЕ|АМПУЛ|ГЛЮКОМЕТР|НАБОР|ТЕСТ.?ПОЛОСК|БИНТ|ШПРИЦ|ПЛАСТЫР|ГРАДУСНИК|ТОНОМЕТР|ИНГАЛЯТОР|НЕБУЛАЙЗЕР|КАПЛИ|РАСТВОР|СПРЕЙ|ЛОСЬОН|ЭМУЛЬС|БАЛЬЗАМ|ПАСТА|ПОРОШОК)', 
                        first_cell_text, 
                        re.IGNORECASE
                    ))
                    
                    if (is_brand or is_cyrillic) and has_measure:
                        # Clean up product name - keep it readable
                        product_name = first_cell_text.strip()[:100]
                        if product_name and product_name not in products:
                            products.append(product_name)
                            logger.info(f"📧 Found product: {product_name[:50]}...")
        
        # Fallback: look for product-like patterns in text if no table products found
        if not products:
            logger.info("📧 No table products found, trying text patterns...")
            # Look for lines that look like product names
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                # Skip short lines, headers, and known non-product patterns
                if len(line) < 10 or len(line) > 150:
                    continue
                skip_words = ['ИТОГО', 'ПРОИЗВОДИТЕЛЬ', 'КОЛ-ВО', 'ЦЕНА', 'СУММА', 'ТОВАР', 'КЛИЕНТ', 'ТЕЛЕФОН', 'ЗАКАЗ', 'АДРЕС', 'АПТЕК', 'ЗДРАВСТВУЙТЕ', 'УВАЖЕНИЕМ', 'ПУЛЬС', 'КАТРЕН']
                if any(w in line.upper() for w in skip_words):
                    continue
                # Product patterns: Cyrillic text + dosage forms OR measurements
                # Match: "Бетаметазон-ВЕРТЕКС крем д/наруж прим 0,05 % туба 30 г"
                if re.search(r'[А-Яа-яЁё]{4,}.*(крем|мазь|гель|табл|капс|сироп|капли|раствор|спрей|порошок|суппозит|свечи|ампул|\d+\s*(мл|мг|г|шт))', line, re.IGNORECASE):
                    # Clean up the product name - take only the first part before numbers/manufacturer
                    product_name = line.strip()[:100]
                    if product_name and product_name not in products:
                        products.append(product_name)
                        logger.info(f"📧 Found product from text: {product_name[:50]}...")
                        if len(products) >= 10:
                            break
        
        # Extract total - prioritize "Сумма для клиента" (customer price, not pharmacy price)
        # In Katren emails, the last number in ИТОГО row is the customer price
        total_patterns = [
            r'Сумма для клиента[:\s]*(\d+(?:[,.]\d+)?)',  # Direct match
            r'Цена для клиента[:\s]*(\d+(?:[,.]\d+)?)',  # Alternative
        ]
        
        for pattern in total_patterns:
            total_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if total_match:
                total_str = total_match.group(1).replace(',', '.').replace(' ', '')
                try:
                    total = float(total_str)
                    if total > 0:
                        logger.info(f"📧 Found total (customer): {total}")
                        break
                except ValueError:
                    pass
        
        # Fallback: find ИТОГО line and take the LAST number (customer price is rightmost column)
        if total == 0:
            itogo_match = re.search(r'ИТОГО[:\s]*(.+)', text, re.IGNORECASE)
            if itogo_match:
                itogo_line = itogo_match.group(1)
                # Find all numbers in the ИТОГО line, take the last one
                numbers = re.findall(r'(\d+(?:[,.]\d+)?)', itogo_line)
                if numbers:
                    last_number = numbers[-1].replace(',', '.')
                    try:
                        total = float(last_number)
                        logger.info(f"📧 Found total from ИТОГО (last number): {total}")
                    except ValueError:
                        pass
                
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"📧 Parse error: {e}")
    
    logger.info(f"📧 Parse result: phone={phone}, products={len(products)}, total={total}")
    return phone, products, total


class EmailMonitor:
    """IMAP email monitor for apteka notifications."""
    
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        folder: str = "INBOX",
        from_filter: str = "apteka.ru",
        since_date: date | None = None,
        timeout: int = 20,
    ):
        self.host = host
        self.user = user
        self.password = password
        self.folder = folder
        self.from_filter = from_filter
        # Default to today if not specified
        self.since_date = since_date or date.today()
        self.timeout = timeout
        self._connection: imaplib.IMAP4_SSL | None = None
    
    def connect(self) -> None:
        """Establish IMAP connection."""
        self._connection = imaplib.IMAP4_SSL(self.host, timeout=self.timeout)
        self._connection.login(self.user, self.password)
        self._connection.select(self.folder)
    
    def disconnect(self) -> None:
        """Close IMAP connection."""
        if self._connection:
            try:
                self._connection.close()
                self._connection.logout()
            except Exception:
                pass
            self._connection = None
    
    def fetch_unread_emails(self) -> list[EmailContent]:
        """
        Fetch unread emails from configured sender(s).
        
        Returns:
            List of EmailContent objects
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Always reconnect to avoid stale connections
        self.disconnect()
        self.connect()
        logger.info("📧 Connected to IMAP server")
        
        assert self._connection is not None
        
        emails: list[EmailContent] = []
        
        # Support multiple senders (comma-separated) or empty filter
        senders = [s.strip() for s in self.from_filter.split(",") if s.strip()]
        
        # Use yesterday's date to catch overnight emails (Render may restart)
        # SINCE filter uses DD-MMM-YYYY format (e.g., 26-Jan-2026)
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        since_str = yesterday.strftime("%d-%b-%Y")
        logger.info(f"📧 Searching emails since {since_str}")
        
        if not senders:
            # If no senders specified, fetch all unread emails
            search_criteria = f'(UNSEEN SINCE {since_str})'
            emails.extend(self._search_and_fetch(search_criteria))
        else:
            # Search for each filter
            for filter_sender in senders:
                search_criteria = f'(UNSEEN SINCE {since_str} FROM "{filter_sender}")'
                emails.extend(self._search_and_fetch(search_criteria))
        
        return emails

    def _search_and_fetch(self, search_criteria: str) -> list[EmailContent]:
        """Helper to search and fetch emails by criteria."""
        emails: list[EmailContent] = []
        if not self._connection:
            return emails
            
        try:
            _, message_numbers = self._connection.search(None, search_criteria)
            
            for num in message_numbers[0].split():
                try:
                    _, msg_data = self._connection.fetch(num, "(RFC822)")
                    
                    if not msg_data or not msg_data[0]:
                        continue
                    
                    raw_email = msg_data[0][1]
                    if isinstance(raw_email, bytes):
                        msg = email.message_from_bytes(raw_email)
                    else:
                        continue
                    
                    subject = decode_email_header(msg.get("Subject"))
                    sender = decode_email_header(msg.get("From"))
                    
                    plain_text, html_text, attachments = extract_text_from_email(msg)
                    
                    # Prefer plain text, fall back to HTML
                    body = plain_text if plain_text.strip() else html_text
                    
                    emails.append(EmailContent(
                        subject=subject,
                        sender=sender,
                        body_text=body,
                        attachments_text=attachments,
                        raw_body=plain_text + "\n" + html_text,
                    ))
                    
                    # Mark as read
                    self._connection.store(num, "+FLAGS", "\\Seen")
                    
                except Exception:
                    continue
                    
        except Exception:
            pass
            
        return emails
    
    def process_email(self, email_content: EmailContent) -> OrderData:
        """
        Extract order data from email.
        
        Args:
            email_content: Parsed email content
            
        Returns:
            OrderData with extracted phone, products, and total
        """
        # Try Katren parser first (for HTML emails)
        phone, products, total = parse_katren_email(email_content.raw_body)
        
        # Fallback to basic extraction if Katren parser didn't find phone
        if not phone:
            full_text = "\n".join([
                email_content.subject,
                email_content.body_text,
                email_content.attachments_text,
            ])
            phone = extract_phone(full_text)
        
        # Extract order number from subject
        order_number = extract_order_number(email_content.subject)
        
        return OrderData(
            order_number=order_number,
            phone=phone,
            products=products,
            total=total,
            source_subject=email_content.subject,
        )


async def monitor_loop(
    monitor: EmailMonitor,
    callback,
    check_interval: int = 60,
) -> None:
    """
    Continuous monitoring loop.
    
    Args:
        monitor: EmailMonitor instance
        callback: Async callback function(OrderData) for processing
        check_interval: Seconds between checks
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"📧 Email monitor started, checking every {check_interval}s")
    logger.info(f"📧 Host: {monitor.host}, User: {monitor.user}, Folder: {monitor.folder}")
    logger.info(f"📧 From filter: '{monitor.from_filter}', Since: {monitor.since_date}")
    
    while True:
        try:
            logger.info("📧 Checking for new emails...")
            emails = await asyncio.wait_for(
                asyncio.to_thread(monitor.fetch_unread_emails),
                timeout=max(30, monitor.timeout + 15),
            )
            logger.info(f"📧 Found {len(emails)} unread email(s)")
            
            for email_content in emails:
                # Filter: only process emails with "заказ" in subject (skip spam/bonuses)
                subject_lower = email_content.subject.lower()
                if 'заказ' not in subject_lower:
                    logger.info(f"📧 Skipping non-order email: {email_content.subject[:50]}...")
                    continue
                    
                logger.info(f"📧 Processing: {email_content.subject[:50]}...")
                order_data = monitor.process_email(email_content)
                logger.info(f"📧 Extracted phone: {order_data.phone}, products: {len(order_data.products)}")
                await callback(order_data)

        except asyncio.TimeoutError:
            logger.error("Email check timed out; Telegram bot remains active")
            monitor.disconnect()
        except Exception as e:
            logger.error(f"📧 Error in monitor loop: {e}")
            # Reconnect on error
            monitor.disconnect()
            
        await asyncio.sleep(check_interval)
