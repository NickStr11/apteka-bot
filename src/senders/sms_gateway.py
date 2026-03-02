"""SMS Gateway via smstext.app."""

import base64
from dataclasses import dataclass

import httpx


@dataclass
class SMSResult:
    """Result of SMS sending."""
    success: bool
    message_id: str | None = None
    error: str | None = None


async def send_sms(
    phone: str,
    message: str,
    api_key: str,
) -> SMSResult:
    """
    Send SMS via smstext.app gateway.

    Args:
        phone: Phone number (e.g. +79991234567)
        message: Text message
        api_key: API key from smstext.app
    """
    url = "https://api.smstext.app/push"

    auth_string = f"apikey:{api_key}"
    auth_bytes = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Content-Type": "application/json",
    }

    if not phone.startswith("+"):
        phone = f"+{phone}"

    payload = [{"mobile": phone, "text": message}]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, json=payload, headers=headers, timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return SMSResult(success=True, message_id=data[0])

            return SMSResult(
                success=False,
                error=f"HTTP {response.status_code}: {response.text}",
            )

    except Exception as e:
        return SMSResult(success=False, error=str(e))
