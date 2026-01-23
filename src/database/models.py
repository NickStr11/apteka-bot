"""Database models and operations for logging."""

import aiosqlite
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "notifications.db"


@dataclass
class NotificationLog:
    """Log entry for a sent notification."""
    id: int | None
    order_number: str
    phone: str
    whatsapp_sent: bool
    telegram_sent: bool
    sms_sent: bool
    error_message: str | None
    created_at: datetime


async def init_db() -> None:
    """Initialize database schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL,
                phone TEXT NOT NULL,
                whatsapp_sent BOOLEAN DEFAULT FALSE,
                telegram_sent BOOLEAN DEFAULT FALSE,
                sms_sent BOOLEAN DEFAULT FALSE,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица связи телефон → telegram_id
        await db.execute("""
            CREATE TABLE IF NOT EXISTS telegram_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_order_number 
            ON notification_logs(order_number)
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at 
            ON notification_logs(created_at)
        """)
        
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_phone 
            ON telegram_users(phone)
        """)
        
        await db.commit()


async def save_telegram_user(
    phone: str,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> bool:
    """
    Save phone -> telegram_id mapping.
    
    Returns:
        True if saved successfully
    """
    # Normalize phone
    phone = phone.replace('+', '').replace(' ', '').replace('-', '')
    if len(phone) == 10:
        phone = '7' + phone
    
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT OR REPLACE INTO telegram_users 
                (phone, telegram_id, username, first_name)
                VALUES (?, ?, ?, ?)
                """,
                (phone, telegram_id, username, first_name)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def get_telegram_id_by_phone(phone: str) -> int | None:
    """
    Get telegram_id for phone number.
    
    Args:
        phone: Phone in any format
        
    Returns:
        telegram_id if found, None otherwise
    """
    # Normalize phone
    phone = phone.replace('+', '').replace(' ', '').replace('-', '')
    if len(phone) == 10:
        phone = '7' + phone
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT telegram_id FROM telegram_users WHERE phone = ?",
            (phone,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def log_notification(
    order_number: str,
    phone: str,
    whatsapp_sent: bool = False,
    telegram_sent: bool = False,
    sms_sent: bool = False,
    error_message: str | None = None,
) -> int:
    """
    Log notification send attempt.
    
    Returns:
        ID of the created log entry
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO notification_logs 
            (order_number, phone, whatsapp_sent, telegram_sent, sms_sent, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (order_number, phone, whatsapp_sent, telegram_sent, sms_sent, error_message)
        )
        await db.commit()
        return cursor.lastrowid or 0


async def get_recent_logs(limit: int = 50) -> list[NotificationLog]:
    """Get recent notification logs."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM notification_logs 
            ORDER BY created_at DESC 
            LIMIT ?
            """,
            (limit,)
        )
        rows = await cursor.fetchall()
        
        return [
            NotificationLog(
                id=row["id"],
                order_number=row["order_number"],
                phone=row["phone"],
                whatsapp_sent=bool(row["whatsapp_sent"]),
                telegram_sent=bool(row["telegram_sent"]),
                sms_sent=bool(row["sms_sent"]),
                error_message=row["error_message"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]


async def check_duplicate(order_number: str, hours: int = 24) -> bool:
    """
    Check if order was already processed recently.
    
    Args:
        order_number: Order number to check
        hours: Time window in hours
        
    Returns:
        True if duplicate found
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM notification_logs 
            WHERE order_number = ? 
            AND created_at > datetime('now', ?)
            """,
            (order_number, f"-{hours} hours")
        )
        row = await cursor.fetchone()
        return row is not None and row[0] > 0
