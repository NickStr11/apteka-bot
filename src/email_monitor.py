"""Email monitoring and processing via IMAP."""

import asyncio
import email
import imaplib
import sys
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import AsyncIterator

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from parsers import parse_html, parse_pdf_bytes, parse_docx_bytes
from extractors import extract_phone, extract_order_number


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


class EmailMonitor:
    """IMAP email monitor for apteka notifications."""
    
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        folder: str = "INBOX",
        from_filter: str = "apteka.ru",
    ):
        self.host = host
        self.user = user
        self.password = password
        self.folder = folder
        self.from_filter = from_filter
        self._connection: imaplib.IMAP4_SSL | None = None
    
    def connect(self) -> None:
        """Establish IMAP connection."""
        self._connection = imaplib.IMAP4_SSL(self.host)
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
        if not self._connection:
            self.connect()
        
        assert self._connection is not None
        
        emails: list[EmailContent] = []
        
        # Support multiple senders (comma-separated)
        senders = [s.strip() for s in self.from_filter.split(",")]
        
        for filter_sender in senders:
            search_criteria = f'(UNSEEN FROM "{filter_sender}")'
            
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
            OrderData with extracted phone and order number
        """
        # Combine all text sources for extraction
        full_text = "\n".join([
            email_content.subject,
            email_content.body_text,
            email_content.attachments_text,
        ])
        
        phone = extract_phone(full_text)
        order_number = extract_order_number(full_text)
        
        return OrderData(
            order_number=order_number,
            phone=phone,
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
    while True:
        try:
            emails = monitor.fetch_unread_emails()
            
            for email_content in emails:
                order_data = monitor.process_email(email_content)
                await callback(order_data)
                
        except Exception:
            # Reconnect on error
            monitor.disconnect()
            
        await asyncio.sleep(check_interval)
