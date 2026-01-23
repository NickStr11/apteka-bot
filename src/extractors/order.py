"""Order number extraction."""

import re
from typing import Pattern

# Паттерны для номеров заказов
ORDER_PATTERNS: list[Pattern[str]] = [
    # apteka.ru формат: MA-280706178, заказ номер MA-280706178
    re.compile(r'[Зз]аказ\s+номер\s+([A-Z]{1,3}-?\d{6,15})', re.IGNORECASE),
    re.compile(r'\b([A-Z]{1,3}-\d{6,15})\b'),
    
    # Заказ №12345 / заказа #12345 / Заказ: 12345
    re.compile(r'[Зз]аказ[а-яё]*\s*[№#:\s]+(\d{4,15})', re.IGNORECASE),
    
    # Ордер №12345
    re.compile(r'[Оо]рдер[а-яё]*\s*[№#:\s]+(\d{4,15})', re.IGNORECASE),
    
    # Номер заказа: 12345 / номер заказа 12345
    re.compile(r'[Нн]омер\s+заказа[:\s]+(\d{4,15})', re.IGNORECASE),
    
    # Order №12345 / Order #12345
    re.compile(r'[Oo]rder\s*[№#:\s]+(\d{4,15})', re.IGNORECASE),
    
    # ID: 12345 / ID заказа: 12345
    re.compile(r'\bID[:\s]+(\d{4,15})\b', re.IGNORECASE),
    
    # № 12345 (просто номер со знаком №)
    re.compile(r'№\s*(\d{5,15})'),
    
    # Заявка №12345
    re.compile(r'[Зз]аявк[а-яё]*\s*[№#:\s]+(\d{4,15})', re.IGNORECASE),
]


def extract_order_number(text: str) -> str | None:
    """
    Extract order number from text.
    
    Supports formats:
    - Заказ №12345
    - заказа #12345
    - Номер заказа: 12345
    - Order #12345
    - ID: 12345
    - № 12345
    - Заявка №12345
    
    Args:
        text: Text containing order number
        
    Returns:
        Order number as string or None
    """
    if not text:
        return None
    
    for pattern in ORDER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    
    return None


def extract_all_order_numbers(text: str) -> list[str]:
    """
    Extract all unique order numbers from text.
    
    Args:
        text: Text containing order numbers
        
    Returns:
        List of order numbers
    """
    if not text:
        return []
    
    orders: set[str] = set()
    
    for pattern in ORDER_PATTERNS:
        for match in pattern.finditer(text):
            orders.add(match.group(1))
    
    return list(orders)
