"""HTML to plain text parser."""

from bs4 import BeautifulSoup
import html2text


def parse_html(html_content: str) -> str:
    """
    Convert HTML content to plain text.
    
    Uses html2text for better formatting preservation,
    falls back to BeautifulSoup for simple extraction.
    
    Args:
        html_content: Raw HTML string
        
    Returns:
        Clean plain text
    """
    if not html_content:
        return ""
    
    # Try html2text first (better at preserving structure)
    try:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_emphasis = True
        h.body_width = 0  # No wrapping
        text = h.handle(html_content)
        return text.strip()
    except Exception:
        pass
    
    # Fallback to BeautifulSoup
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style", "head", "meta", "link"]):
            element.decompose()
        
        # Get text with spaces between elements
        text = soup.get_text(separator=" ", strip=True)
        
        # Clean up multiple spaces
        import re
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    except Exception:
        return html_content
