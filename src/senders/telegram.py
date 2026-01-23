"""Telegram sender via Bot API."""

from dataclasses import dataclass
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError


@dataclass
class TelegramResult:
    """Result of Telegram send operation."""
    success: bool
    message_id: int | None = None
    error: str | None = None


async def send_telegram(
    chat_id: int,
    message: str,
    bot_token: str,
) -> TelegramResult:
    """
    Send Telegram message to chat_id.
    
    Note: Bot can only send messages to users who have started it.
    Use this primarily for admin notifications.
    
    Args:
        chat_id: Telegram user/chat ID
        message: Message text to send
        bot_token: Telegram Bot API token
        
    Returns:
        TelegramResult with success status and message ID or error
    """
    if not bot_token:
        return TelegramResult(
            success=False,
            error="Telegram bot token not configured"
        )
    
    bot = Bot(token=bot_token)
    
    try:
        result = await bot.send_message(chat_id=chat_id, text=message)
        return TelegramResult(
            success=True,
            message_id=result.message_id
        )
    except TelegramAPIError as e:
        return TelegramResult(
            success=False,
            error=f"Telegram API error: {e}"
        )
    except Exception as e:
        return TelegramResult(
            success=False,
            error=str(e)
        )
    finally:
        await bot.session.close()


async def send_telegram_to_customer(
    telegram_id: int,
    message: str,
    bot_token: str,
) -> TelegramResult:
    """
    Send notification to customer by their telegram_id.
    
    Args:
        telegram_id: Customer's Telegram ID (from database)
        message: Notification message
        bot_token: Bot token
        
    Returns:
        TelegramResult
    """
    return await send_telegram(telegram_id, message, bot_token)


async def send_admin_report(
    admin_id: int,
    order_number: str,
    phone: str,
    channels: dict[str, bool],
    bot_token: str,
) -> TelegramResult:
    """
    Send status report to admin.
    
    Args:
        admin_id: Admin's Telegram user ID
        order_number: Order number that was processed
        phone: Customer phone number
        channels: Dict with channel names and success status
        bot_token: Telegram Bot API token
        
    Returns:
        TelegramResult
    """
    # Build status message
    status_lines = []
    for channel, success in channels.items():
        emoji = "✅" if success else "❌"
        status_lines.append(f"{emoji} {channel}")
    
    all_success = all(channels.values())
    header = "📦 Уведомление отправлено" if all_success else "⚠️ Частичная отправка"
    
    message = f"""{header}

🔢 Заказ: №{order_number}
📱 Телефон: {phone}

Каналы:
{chr(10).join(status_lines)}"""
    
    return await send_telegram(admin_id, message, bot_token)
