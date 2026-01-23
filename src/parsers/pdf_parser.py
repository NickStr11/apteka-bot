"""PDF to plain text parser."""

from pathlib import Path
from typing import BinaryIO

import pdfplumber


def parse_pdf(source: str | Path | BinaryIO) -> str:
    """
    Extract text from PDF file.
    
    Args:
        source: File path or file-like object
        
    Returns:
        Extracted plain text
    """
    text_parts: list[str] = []
    
    try:
        with pdfplumber.open(source) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception as e:
        return f"[PDF parsing error: {e}]"
    
    return "\n\n".join(text_parts)


def parse_pdf_bytes(content: bytes) -> str:
    """
    Extract text from PDF bytes.
    
    Args:
        content: PDF file content as bytes
        
    Returns:
        Extracted plain text
    """
    import io
    return parse_pdf(io.BytesIO(content))
