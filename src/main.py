"""
Pharmacy Notification System - Main Application

Monitors email for new orders, saves to Google Sheets,
and sends notifications via WhatsApp (with SMS fallback).
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from email_monitor import EmailMonitor
from extractors import extract_phone, extract_order_number, extract_products, extract_total, format_products_for_notification
from database.sheets import get_client, get_sheet, add_order, find_order_by_number, update_order_status, get_pending_orders, OrderRow
from senders.whatsapp import send_whatsapp, check_whatsapp_status
from senders.sms_gateway import send_sms_gateway

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("apteka.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


async def process_new_emails(config, sheet):
    """Check email for new orders and add to spreadsheet."""
    logger.info("Проверяю почту на новые заказы...")
    
    monitor = EmailMonitor(
        host=config.email_host,
        user=config.email_user,
        password=config.email_password,
        folder=config.email_folder,
        from_filter=config.email_from_filter,
    )
    
    try:
        monitor.connect()
        emails = monitor.fetch_unread_emails()
        
        if not emails:
            logger.info("Новых писем нет")
            return 0
        
        added_count = 0
        for email_content in emails:
            # Parse email
            full_text = "\n".join([
                email_content.subject,
                email_content.body_text,
                email_content.attachments_text,
            ])
            
            phone = extract_phone(full_text)
            order_number = extract_order_number(full_text)
            products = extract_products(full_text)
            _, total_client = extract_total(full_text)
            
            if not phone:
                logger.warning(f"Телефон не найден в письме: {email_content.subject}")
                continue
            
            if not order_number:
                logger.warning(f"Номер заказа не найден в письме: {email_content.subject}")
                continue
            
            # Check for duplicates
            existing = find_order_by_number(sheet, order_number)
            if existing:
                logger.info(f"Заказ {order_number} уже существует в строке {existing}")
                continue
            
            # Format products for display
            products_text = ", ".join([f"{p.name[:20]} x{p.quantity}" for p in products])
            
            # Add to spreadsheet
            order = OrderRow(
                date=datetime.now().strftime("%d.%m.%Y %H:%M"),
                order_number=order_number,
                phone=phone,
                products=products_text,
                total=total_client,
                wa_status="",
                sms_status="",
                sent="",
                note="",
            )
            
            row = add_order(sheet, order)
            logger.info(f"✅ Добавлен заказ {order_number} для {phone} (строка {row})")
            added_count += 1
        
        return added_count
        
    finally:
        monitor.disconnect()


async def send_notifications(config, sheet):
    """Send SMS notifications for all pending orders."""
    logger.info("Отправляю SMS уведомления...")
    
    pending = get_pending_orders(sheet)
    if not pending:
        logger.info("Нет заказов для отправки")
        return
    
    logger.info(f"Найдено {len(pending)} заказов для отправки")
    
    sent_count = 0
    failed_count = 0
    
    for row_num, order in pending:
        logger.info(f"Отправляю SMS: заказ {order.order_number} на {order.phone}...")
        
        # Format short SMS message
        message = f"Заказ {order.order_number} готов! Сумма: {order.total:.0f}р. Ждём в аптеке!"
        
        # Send SMS
        sms_result = await send_sms_gateway(
            phone=order.phone,
            message=message,
            api_key=config.smsgateway_api_key,
        )
        
        if sms_result.success:
            logger.info(f"✅ SMS отправлен: {order.order_number}")
            update_order_status(
                sheet, row_num, 
                sms_status="✅", 
                sent=datetime.now().strftime("%d.%m.%Y %H:%M")
            )
            sent_count += 1
        else:
            logger.error(f"❌ SMS не отправлен: {sms_result.error}")
            update_order_status(sheet, row_num, sms_status="❌")
            failed_count += 1
        
        # Small delay between messages
        await asyncio.sleep(2)
    
    logger.info(f"📊 Итого: отправлено {sent_count}, ошибок {failed_count}")


async def monitor_loop(config, sheet, check_interval: int = 300):
    """
    Main monitoring loop.
    
    Args:
        check_interval: Seconds between email checks (default 5 min)
    """
    logger.info(f"🚀 Запущен мониторинг почты (интервал: {check_interval} сек)")
    
    while True:
        try:
            await process_new_emails(config, sheet)
        except Exception as e:
            logger.error(f"Ошибка при проверке почты: {e}")
        
        await asyncio.sleep(check_interval)


async def main():
    """Main entry point."""
    import sys
    
    # Load config
    config = load_config()
    
    # Initialize Google Sheets
    logger.info("Подключаюсь к Google Sheets...")
    client = get_client(config.google_credentials_path)
    sheet = get_sheet(client)
    logger.info(f"✅ Подключено к таблице: {sheet.title}")
    
    # Parse command line args
    mode = sys.argv[1] if len(sys.argv) > 1 else "monitor"
    
    if mode == "monitor":
        # Continuous monitoring mode
        await monitor_loop(config, sheet)
        
    elif mode == "check":
        # One-time email check
        count = await process_new_emails(config, sheet)
        logger.info(f"Добавлено заказов: {count}")
        
    elif mode == "send":
        # Send all pending notifications
        await send_notifications(config, sheet)
        
    elif mode == "all":
        # Check email and send notifications
        await process_new_emails(config, sheet)
        await send_notifications(config, sheet)
        
    else:
        print("Usage: python main.py [monitor|check|send|all]")
        print("  monitor - continuous email monitoring (default)")
        print("  check   - check email once and add to sheet")
        print("  send    - send notifications for pending orders")
        print("  all     - check email and send notifications")


if __name__ == "__main__":
    asyncio.run(main())
