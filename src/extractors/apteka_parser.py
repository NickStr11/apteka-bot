import httpx
from bs4 import BeautifulSoup
import re
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProductInfo:
    """Product info from apteka.ru."""
    name: str
    price: float = 0.0


def extract_product_from_url(url: str) -> str | None:
    """
    Extracts product name from apteka.ru URL.
    Tries HTML parsing first, then falls back to slug extraction.
    """
    info = extract_product_with_price(url)
    return info.name if info else None


def extract_product_with_price(url: str) -> ProductInfo | None:
    """
    Extracts product name AND price from apteka.ru URL.
    Returns ProductInfo with name and price.
    """
    if 'apteka.ru' not in url:
        return None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    name = None
    price = 0.0
    
    try:
        # 1. Try fetching and parsing
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Get product name from H1
                h1 = soup.find('h1')
                if h1:
                    name = h1.text.strip()
                
                # Try title as fallback for name
                if not name:
                    title = soup.find('title')
                    if title:
                        name = title.text.strip()
                        name = re.sub(r'\s*— купить в интернет-аптеке.*', '', name, flags=re.IGNORECASE)
                
                # Try to get price from JSON-LD
                scripts = soup.find_all('script', type='application/ld+json')
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            # Check for Product schema
                            if data.get('@type') == 'Product':
                                offers = data.get('offers', {})
                                if isinstance(offers, dict):
                                    price_str = offers.get('price')
                                    if price_str:
                                        price = float(price_str)
                                        break
                                elif isinstance(offers, list) and offers:
                                    price_str = offers[0].get('price')
                                    if price_str:
                                        price = float(price_str)
                                        break
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue
                
                # Fallback: try meta tag og:price:amount
                if price == 0:
                    meta_price = soup.find('meta', property='product:price:amount')
                    if meta_price and meta_price.get('content'):
                        try:
                            price = float(meta_price['content'])
                        except ValueError:
                            pass
                
                # Fallback: look for price in common selectors
                if price == 0:
                    price_elem = soup.select_one('[class*="price"]')
                    if price_elem:
                        price_text = price_elem.get_text()
                        # Extract number from text like "299 ₽" or "1 234,56 руб"
                        price_match = re.search(r'(\d[\d\s]*[,.]?\d*)', price_text)
                        if price_match:
                            price_str = price_match.group(1).replace(' ', '').replace(',', '.')
                            try:
                                price = float(price_str)
                            except ValueError:
                                pass

    except Exception as e:
        logger.error(f"Error fetching Apteka.ru URL: {e}")

    # 2. Fallback for name: extract from URL slug
    if not name:
        match = re.search(r'/product/([^/]+)', url)
        if match:
            slug = match.group(1)
            slug = re.sub(r'-[a-f0-9]{24}$', '', slug)
            name = slug.replace('-', ' ').strip().capitalize()

    if name:
        return ProductInfo(name=name, price=price)
    
    return None

