"""Tests for phone and order extractors."""

import pytest
from src.extractors.phone import extract_phone, extract_all_phones, normalize_phone
from src.extractors.order import extract_order_number, extract_all_order_numbers


class TestPhoneExtraction:
    """Test cases for phone number extraction."""
    
    def test_plus7_format_with_parentheses(self):
        """Test +7 (999) 123-45-67 format."""
        text = "Телефон покупателя: +7 (999) 123-45-67"
        assert extract_phone(text) == "+79991234567"
    
    def test_8_format_with_parentheses(self):
        """Test 8(999)1234567 format."""
        text = "Позвоните на 8(999)1234567"
        assert extract_phone(text) == "+79991234567"
    
    def test_dashed_format(self):
        """Test 8-999-123-45-67 format."""
        text = "Контакт: 8-999-123-45-67"
        assert extract_phone(text) == "+79991234567"
    
    def test_compact_plus7(self):
        """Test +79991234567 format."""
        text = "тел: +79991234567"
        assert extract_phone(text) == "+79991234567"
    
    def test_10_digits_starting_with_9(self):
        """Test 9991234567 format (10 digits)."""
        text = "Номер 9991234567 для связи"
        assert extract_phone(text) == "+79991234567"
    
    def test_spaced_format(self):
        """Test 8 999 123 45 67 format with spaces."""
        text = "Звоните: 8 999 123 45 67"
        assert extract_phone(text) == "+79991234567"
    
    def test_no_phone(self):
        """Test text without phone number."""
        text = "Заказ готов, приходите!"
        assert extract_phone(text) is None
    
    def test_normalize_10_digits(self):
        """Test normalization of 10-digit number."""
        assert normalize_phone("9991234567") == "+79991234567"
    
    def test_normalize_11_digits_with_8(self):
        """Test normalization of 11-digit number starting with 8."""
        assert normalize_phone("89991234567") == "+79991234567"
    
    def test_extract_all_phones(self):
        """Test extraction of multiple phone numbers."""
        text = "Первый: +7 999 111-11-11, второй: 8(888)222-22-22"
        phones = extract_all_phones(text)
        assert len(phones) == 2
        assert "+79991111111" in phones
        assert "+78882222222" in phones


class TestOrderExtraction:
    """Test cases for order number extraction."""
    
    def test_zakazno_format(self):
        """Test Заказ №12345 format."""
        text = "Ваш Заказ №12345678 готов к выдаче"
        assert extract_order_number(text) == "12345678"
    
    def test_zakaza_colon_format(self):
        """Test заказа: 12345 format."""
        text = "Номер заказа: 87654321"
        assert extract_order_number(text) == "87654321"
    
    def test_hash_format(self):
        """Test Заказ #12345 format."""
        text = "Заказ #999888777"
        assert extract_order_number(text) == "999888777"
    
    def test_id_format(self):
        """Test ID: 12345 format."""
        text = "Ваш ID: 123456789"
        assert extract_order_number(text) == "123456789"
    
    def test_just_number_sign(self):
        """Test № 12345 format."""
        text = "Забрать № 55544433"
        assert extract_order_number(text) == "55544433"
    
    def test_zayavka_format(self):
        """Test Заявка №12345 format."""
        text = "Заявка №11112222"
        assert extract_order_number(text) == "11112222"
    
    def test_no_order(self):
        """Test text without order number."""
        text = "Добро пожаловать в аптеку!"
        assert extract_order_number(text) is None
    
    def test_short_number_ignored(self):
        """Test that too short numbers are ignored."""
        text = "Заказ №123"  # Too short (3 digits)
        assert extract_order_number(text) is None
    
    def test_extract_all_orders(self):
        """Test extraction of multiple order numbers."""
        text = "Заказы: №11111111 и №22222222"
        orders = extract_all_order_numbers(text)
        assert len(orders) == 2
        assert "11111111" in orders
        assert "22222222" in orders


class TestRealWorldExamples:
    """Test with real-world-like email content."""
    
    def test_apteka_ru_email_format(self):
        """Test typical apteka.ru email format."""
        email_text = """
        Уважаемый покупатель!
        
        Ваш заказ №1234567890 готов к выдаче в аптеке.
        
        Контактный телефон: +7 (926) 555-12-34
        
        Ждём вас!
        """
        
        phone = extract_phone(email_text)
        order = extract_order_number(email_text)
        
        assert phone == "+79265551234"
        assert order == "1234567890"
    
    def test_multiline_with_noise(self):
        """Test extraction from noisy multiline text."""
        text = """
        ===== УВЕДОМЛЕНИЕ =====
        Дата: 15.01.2024
        
        Клиент: Иванов И.И.
        Заказ: #998877665544
        
        Для уточнения звоните:
        8 (495) 123-45-67
        
        Спасибо за покупку!
        """
        
        phone = extract_phone(text)
        order = extract_order_number(text)
        
        assert phone == "+74951234567"
        assert order == "998877665544"
