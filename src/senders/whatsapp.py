"""WhatsApp sender via Green-API."""

import httpx
from dataclasses import dataclass


@dataclass
class WhatsAppResult:
    """Result of WhatsApp sending."""
    success: bool
    message_id: str | None = None
    error: str | None = None


async def send_whatsapp(
    phone: str,
    message: str,
    instance_id: str,
    token: str,
) -> WhatsAppResult:
    """
    Send WhatsApp message via Green-API.
    
    Args:
        phone: Phone number (e.g. +79991234567 or 79991234567)
        message: Text message
        instance_id: Green-API instance ID
        token: Green-API token
        
    Returns:
        WhatsAppResult with success status
    """
    # Clean phone number (remove + if present)
    phone_clean = phone.lstrip("+")
    
    url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{token}"
    
    payload = {
        "chatId": f"{phone_clean}@c.us",
        "message": message,
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("idMessage"):
                    return WhatsAppResult(
                        success=True,
                        message_id=data["idMessage"],
                    )
            
            return WhatsAppResult(
                success=False,
                error=f"HTTP {response.status_code}: {response.text}",
            )
            
    except Exception as e:
        return WhatsAppResult(
            success=False,
            error=str(e),
        )


async def check_whatsapp_status(
    message_id: str,
    instance_id: str,
    token: str,
) -> str:
    """
    Check WhatsApp message delivery status.
    
    Returns:
        Status string: 'sent', 'delivered', 'read', 'failed'
    """
    # Note: Green-API requires webhook for real-time status updates
    # For now, we assume sent = success
    # In production, implement webhook receiver
    return "sent"


def sync_send_whatsapp(
    phone: str,
    message: str,
    instance_id: str,
    token: str,
) -> WhatsAppResult:
    """Synchronous version of send_whatsapp."""
    import asyncio
    return asyncio.run(send_whatsapp(phone, message, instance_id, token))
