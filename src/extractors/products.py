"""Product and price extraction from order emails."""

import re
from dataclasses import dataclass


@dataclass
class ProductItem:
    """Single product from order."""
    name: str
    quantity: int
    price_pharmacy: float  # Цена для аптеки
    price_client: float    # Цена для клиента
    total_client: float    # Сумма для клиента


@dataclass
class OrderDetails:
    """Full order details."""
    order_number: str | None
    phone: str | None
    products: list[ProductItem]
    total_pharmacy: float
    total_client: float


def extract_products(text: str) -> list[ProductItem]:
    """
    Extract products and prices from order text.
    
    Parses table format like:
    Товар| Производитель| Кол-во| Цена для аптеки| Сумма для аптеки| Цена для клиента| Сумма для клиента| ШК
    
    Args:
        text: Full email text
        
    Returns:
        List of ProductItem objects
    """
    products: list[ProductItem] = []
    
    # Find table rows (lines with | separator)
    lines = text.split('\n')
    
    for line in lines:
        # Skip lines without table separator
        if '|' not in line:
            continue
            
        # Skip header row
        if 'Товар' in line and 'Производитель' in line:
            continue
            
        # Skip separator rows
        if line.strip().startswith('---') or line.strip() == '---|---|---|---|---|---|---|---':
            continue
            
        # Skip ИТОГО row
        upper_line = line.upper()
        if 'ИТОГО' in upper_line:
            continue
        
        # Parse table row
        parts = [p.strip() for p in line.split('|')]
        
        # Need at least 7 columns: Товар, Производитель, Кол-во, Цена аптеки, Сумма аптеки, Цена клиента, Сумма клиента
        if len(parts) >= 7:
            try:
                name = parts[0].strip()
                if not name or len(name) < 3:
                    continue
                    
                # Try to parse numbers (handle comma as decimal)
                def parse_int(s: str) -> int:
                    s = s.strip()
                    try:
                        return int(s) if s.isdigit() else 1
                    except:
                        return 1
                
                def parse_price(s: str) -> float:
                    s = s.strip().replace(',', '.').replace(' ', '')
                    try:
                        return float(s) if s else 0.0
                    except:
                        return 0.0
                
                quantity = parse_int(parts[2])
                price_pharmacy = parse_price(parts[3])
                price_client = parse_price(parts[5])
                total_client = parse_price(parts[6])
                
                # Validate - at least one price should be > 0
                if price_pharmacy > 0 or price_client > 0 or total_client > 0:
                    products.append(ProductItem(
                        name=name,
                        quantity=quantity,
                        price_pharmacy=price_pharmacy,
                        price_client=price_client,
                        total_client=total_client,
                    ))
            except (IndexError, ValueError):
                continue
    
    return products


def extract_total(text: str) -> tuple[float, float]:
    """
    Extract total amounts from order.
    
    Returns:
        (total_pharmacy, total_client)
    """
    # Pattern: ИТОГО:| | | | 1105,07| | 1199|
    match = re.search(r'ИТОГО[:\s|]+[\d\s,.|]*?([\d,]+)[^\d]*([\d,]+)', text, re.IGNORECASE)
    if match:
        def parse_price(s: str) -> float:
            s = s.strip().replace(',', '.').replace(' ', '')
            try:
                return float(s)
            except:
                return 0.0
        return parse_price(match.group(1)), parse_price(match.group(2))
    
    return 0.0, 0.0


def format_products_for_notification(products: list[ProductItem], total: float) -> str:
    """
    Format products list for SMS/WhatsApp notification.
    
    Args:
        products: List of ProductItem
        total: Total amount
        
    Returns:
        Formatted string for notification
    """
    if not products:
        return ""
    
    lines = []
    for p in products:
        # Shorten long names
        name = p.name[:30] + "..." if len(p.name) > 30 else p.name
        lines.append(f"• {name} x{p.quantity} = {p.total_client:.0f}₽")
    
    lines.append(f"\nИтого: {total:.0f}₽")
    
    return "\n".join(lines)
