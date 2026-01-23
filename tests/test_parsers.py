"""Tests for parsers."""

import pytest
from src.parsers.html_parser import parse_html


class TestHtmlParser:
    """Test cases for HTML parser."""
    
    def test_simple_html(self):
        """Test simple HTML to text conversion."""
        html = "<html><body><p>Hello World</p></body></html>"
        result = parse_html(html)
        assert "Hello World" in result
    
    def test_strips_scripts(self):
        """Test that script tags are removed."""
        html = """
        <html>
        <body>
            <script>alert('bad')</script>
            <p>Safe content</p>
        </body>
        </html>
        """
        result = parse_html(html)
        assert "alert" not in result
        assert "Safe content" in result
    
    def test_strips_styles(self):
        """Test that style tags are removed."""
        html = """
        <html>
        <head><style>.red { color: red; }</style></head>
        <body><p>Styled text</p></body>
        </html>
        """
        result = parse_html(html)
        assert "color" not in result
        assert "Styled text" in result
    
    def test_preserves_line_breaks(self):
        """Test that important structure is preserved."""
        html = """
        <div>
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
        </div>
        """
        result = parse_html(html)
        assert "Paragraph 1" in result
        assert "Paragraph 2" in result
    
    def test_empty_input(self):
        """Test handling of empty input."""
        assert parse_html("") == ""
        assert parse_html(None) == ""
    
    def test_apteka_like_email(self):
        """Test parsing of apteka-like email HTML."""
        html = """
        <html>
        <body>
            <table>
                <tr><td>Заказ №</td><td>12345678</td></tr>
                <tr><td>Телефон</td><td>+7 (999) 123-45-67</td></tr>
            </table>
            <p>Ваш заказ готов!</p>
        </body>
        </html>
        """
        result = parse_html(html)
        assert "12345678" in result
        assert "123-45-67" in result or "1234567" in result
        assert "готов" in result
