"""Configuration loader from .env file."""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration."""
    
    # Email
    email_host: str
    email_user: str
    email_password: str
    email_folder: str
    email_from_filter: str
    
    # WhatsApp
    greenapi_instance_id: str
    greenapi_token: str
    
    # SMS Gateway
    smsgateway_api_key: str
    
    # Telegram
    telegram_bot_token: str
    telegram_admin_id: str
    
    # Yandex SpeechKit
    yandex_speechkit_api_key: str
    
    # Google Sheets
    google_credentials_path: str
    
    # Notification
    notification_message: str
    
    # Phone blacklist (comma-separated)
    ignore_phones: list[str]


def load_config(env_path: str | Path | None = None) -> Config:
    """Load configuration from .env file."""
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    return Config(
        email_host=os.getenv("EMAIL_HOST", "imap.gmail.com"),
        email_user=os.getenv("EMAIL_USER", ""),
        email_password=os.getenv("EMAIL_PASSWORD", ""),
        email_folder=os.getenv("EMAIL_FOLDER", "INBOX"),
        email_from_filter=os.getenv("EMAIL_FROM_FILTER", ""),
        
        greenapi_instance_id=os.getenv("GREENAPI_INSTANCE_ID", ""),
        greenapi_token=os.getenv("GREENAPI_TOKEN", ""),
        
        smsgateway_api_key=os.getenv("SMSGATEWAY_API_KEY", ""),
        
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_admin_id=os.getenv("TELEGRAM_ADMIN_ID", ""),
        
        yandex_speechkit_api_key=os.getenv("YANDEX_SPEECHKIT_API_KEY", ""),
        
        google_credentials_path=os.getenv(
            "GOOGLE_CREDENTIALS_PATH",
            "photo-gallery-484020-c9d57645a635.json"
        ),
        
        notification_message=os.getenv(
            "NOTIFICATION_MESSAGE",
            "Ваш заказ №{order_number} готов к выдаче!"
        ),
        
        ignore_phones=[
            p.strip() for p in os.getenv("IGNORE_PHONES", "").split(",") if p.strip()
        ],
    )
