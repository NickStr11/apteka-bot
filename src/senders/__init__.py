"""Senders package - отправка сообщений через различные каналы."""

from .whatsapp import send_whatsapp
from .telegram import send_telegram
from .sms import send_sms

__all__ = ["send_whatsapp", "send_telegram", "send_sms"]
