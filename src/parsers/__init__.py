"""Parsers package - извлечение текста из различных форматов."""

from .html_parser import parse_html
from .pdf_parser import parse_pdf, parse_pdf_bytes
from .docx_parser import parse_docx, parse_docx_bytes

__all__ = ["parse_html", "parse_pdf", "parse_pdf_bytes", "parse_docx", "parse_docx_bytes"]

