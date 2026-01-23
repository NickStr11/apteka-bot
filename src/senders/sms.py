"""SMS sender with multiple providers support."""

import httpx
from dataclasses import dataclass
from enum import Enum


class SmsProvider(Enum):
    """Supported SMS providers."""
    SMSRU = "sms.ru"
    SIGMA = "sigmasms.ru"  # Дешевле: от 1.5₽


@dataclass
class SmsResult:
    """Result of SMS send operation."""
    success: bool
    sms_id: str | None = None
    balance: float | None = None
    error: str | None = None
    provider: str | None = None


async def send_sms_sigma(
    phone: str,
    message: str,
    login: str,
    password: str,
) -> SmsResult:
    """
    Send SMS via SigmaSMS (от 1.5₽/SMS).
    
    Args:
        phone: Phone number in +7XXXXXXXXXX format
        message: Message text
        login: SigmaSMS login
        password: SigmaSMS password
        
    Returns:
        SmsResult
    """
    if not login or not password:
        return SmsResult(
            success=False,
            error="SigmaSMS credentials not configured",
            provider="sigma"
        )
    
    phone_formatted = phone.replace('+', '')
    
    url = "https://online.sigmasms.ru/api/sendings"
    
    payload = {
        "recipient": phone_formatted,
        "type": "sms",
        "payload": {
            "sender": "INFO",  # или ваше имя отправителя
            "text": message
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                auth=(login, password)
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                return SmsResult(
                    success=True,
                    sms_id=data.get("id"),
                    provider="sigma"
                )
            else:
                return SmsResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    provider="sigma"
                )
    except httpx.TimeoutException:
        return SmsResult(success=False, error="Request timeout", provider="sigma")
    except Exception as e:
        return SmsResult(success=False, error=str(e), provider="sigma")


async def send_sms(
    phone: str,
    message: str,
    api_id: str,
) -> SmsResult:
    """
    Send SMS via SMS.ru API.
    
    Args:
        phone: Phone number in +7XXXXXXXXXX format
        message: Message text (max ~70 chars for 1 SMS in cyrillic)
        api_id: SMS.ru API ID
        
    Returns:
        SmsResult with success status and SMS ID or error
    """
    if not api_id:
        return SmsResult(
            success=False,
            error="SMS.ru API ID not configured",
            provider="sms.ru"
        )
    
    # SMS.ru expects phone without +
    phone_formatted = phone.replace('+', '')
    
    url = "https://sms.ru/sms/send"
    params = {
        "api_id": api_id,
        "to": phone_formatted,
        "msg": message,
        "json": 1
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK":
                    sms_data = data.get("sms", {}).get(phone_formatted, {})
                    return SmsResult(
                        success=True,
                        sms_id=sms_data.get("sms_id"),
                        balance=data.get("balance"),
                        provider="sms.ru"
                    )
                else:
                    error_code = data.get("status_code", "unknown")
                    return SmsResult(
                        success=False,
                        error=f"SMS.ru error code: {error_code}",
                        provider="sms.ru"
                    )
            else:
                return SmsResult(
                    success=False,
                    error=f"HTTP {response.status_code}",
                    provider="sms.ru"
                )
    except httpx.TimeoutException:
        return SmsResult(success=False, error="Request timeout", provider="sms.ru")
    except Exception as e:
        return SmsResult(success=False, error=str(e), provider="sms.ru")


async def get_sms_balance(api_id: str) -> float | None:
    """
    Get current SMS.ru balance.
    
    Args:
        api_id: SMS.ru API ID
        
    Returns:
        Balance in rubles or None on error
    """
    if not api_id:
        return None
    
    url = "https://sms.ru/my/balance"
    params = {"api_id": api_id, "json": 1}
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "OK":
                    return data.get("balance")
    except Exception:
        pass
    
    return None
