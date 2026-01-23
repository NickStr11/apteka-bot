"""Phone number extraction and normalization."""

import re
from typing import Pattern

# Паттерны для различных форматов телефонов
# Порядок важен: более специфичные паттерны первыми

PHONE_PATTERNS: list[Pattern[str]] = [
    # Универсальный паттерн для 11 цифр (начинается с 7 или 8)
    # Ищет цифры, разделенные любым кол-вом пробелов, тире или скобок
    re.compile(
        r'(?:(?:\+7|8|7)[\s\-\(\)]*){1}(?:\d[\s\-\(\)]*){10}'
    ),
    # Универсальный паттерн для 10 цифр (начинается с 9)
    re.compile(
        r'\b(?:9[\s\-\(\)]*){1}(?:\d[\s\-\(\)]*){9}\b'
    ),
    # Стандартные форматы (оставляем для точности извлечения групп)
    re.compile(
        r'(?:\+7|8)\s*[\(\-]?\s*(\d{3})\s*[\)\-]?\s*(\d{3})\s*[\-]?\s*(\d{2})\s*[\-]?\s*(\d{2})'
    ),
]


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to +7XXXXXXXXXX format.
    
    Args:
        phone: Raw phone string with any formatting
        
    Returns:
        Normalized phone in +7XXXXXXXXXX format
    """
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) == 10:
        # Assume Russian number without country code
        return f"+7{digits}"
    elif len(digits) == 11:
        if digits.startswith('8') or digits.startswith('7'):
            return f"+7{digits[1:]}"
    elif len(digits) == 12 and digits.startswith('7'):
        return f"+{digits}"
    
    return phone  # Return original if can't normalize


def extract_phone(text: str) -> str | None:
    """
    Extract and normalize phone number from text.
    
    Supports formats:
    - +7 (999) 123-45-67
    - 8(999)1234567
    - 8-999-123-45-67
    - +79991234567
    - 9991234567
    - (999) 123-45-67
    
    Args:
        text: Text containing phone number
        
    Returns:
        Normalized phone in +7XXXXXXXXXX format or None
    """
    if not text:
        return None
    
    for pattern in PHONE_PATTERNS:
        match = pattern.search(text)
        if match:
            raw_number = match.group(0)
            return normalize_phone(raw_number)
    
    return None


def extract_all_phones(text: str) -> list[str]:
    """
    Extract all unique phone numbers from text.
    
    Args:
        text: Text containing phone numbers
        
    Returns:
        List of normalized phone numbers
    """
    if not text:
        return []
    
    phones: set[str] = set()
    
    for pattern in PHONE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            raw_number = ''.join(groups)
            normalized = normalize_phone(raw_number)
            if normalized.startswith('+7') and len(normalized) == 12:
                phones.add(normalized)
    
    return list(phones)
