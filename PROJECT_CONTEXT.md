# Apteka Notify

## Цель
Автономная система уведомлений клиентов аптеки: мониторинг почты от apteka.ru, извлечение данных заказов, мультиканальная отправка (WhatsApp/SMS/Telegram).

## Функционал
- [x] Автоматический мониторинг почтового ящика (IMAP)
- [x] Парсинг HTML писем, PDF/DOCX вложений
- [x] Regex-извлечение телефона и номера заказа
- [x] Отправка через WhatsApp (Green-API)
- [x] Отправка SMS (SMS.ru)
- [x] Telegram бот для ручного ввода
- [x] Отчёты администратору в Telegram
- [x] SQLite логирование

## Стек
- Python 3.12
- aiogram 3.x (Telegram)
- httpx (HTTP клиент)
- BeautifulSoup4, html2text (HTML)
- pdfplumber, python-docx (вложения)
- aiosqlite (БД)

## Структура
```
apteka/
├── src/
│   ├── main.py              # Точка входа
│   ├── config.py            # Настройки
│   ├── email_monitor.py     # IMAP
│   ├── parsers/             # HTML, PDF, DOCX
│   ├── extractors/          # Regex
│   ├── senders/             # WhatsApp, Telegram, SMS
│   ├── bot/                 # Telegram бот
│   └── database/            # SQLite
├── tests/
├── .env.example
└── pyproject.toml
```

## Команды
```bash
# Установка
pip install -e .

# Запуск
python -m src.main

# Тесты
pytest tests/ -v
```
