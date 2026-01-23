import httpx
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

def extract_product_from_url(url: str) -> str | None:
    """
    Extracts product name from apteka.ru URL.
    Tries HTML parsing first, then falls back to slug extraction.
    """
    if 'apteka.ru' not in url:
        return None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    try:
        # 1. Try fetching and parsing H1
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                h1 = soup.find('h1')
                if h1:
                    name = h1.text.strip()
                    if name:
                        return name
                
                # Try title as fallback
                title = soup.find('title')
                if title:
                    name = title.text.strip()
                    # Clean up common apteka.ru title suffix
                    name = re.sub(r'\s*— купить в интернет-аптеке.*', '', name, flags=re.IGNORECASE)
                    if name:
                        return name
    except Exception as e:
        logger.error(f"Error fetching Apteka.ru URL: {e}")

    # 2. Fallback: extract from URL slug
    # Example: https://apteka.ru/product/aspirin-ekspress-500mg-n12-tab-ship-5e326620ca7680000109559c/
    match = re.search(r'/product/([^/]+)', url)
    if match:
        slug = match.group(1)
        # Remove the ID part (last dash and hex string)
        # 5e326620ca7680000109559c
        slug = re.sub(r'-[a-f0-9]{24}$', '', slug)
        # Replace dashes with spaces and capitalize
        name = slug.replace('-', ' ').strip().capitalize()
        if name:
            return name

    return None
