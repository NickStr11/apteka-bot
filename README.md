# Apteka Notify

Автономная система уведомлений клиентов аптеки.

## Возможности

- 📧 Автоматический мониторинг почтового ящика
- 📄 Парсинг HTML писем, PDF и DOCX вложений
- 📱 Извлечение номера телефона и заказа (regex)
- 💬 Отправка уведомлений через WhatsApp, Telegram, SMS
- 🤖 Telegram бот для ручного ввода
- 📊 Логирование и отчёты

## Установка

```bash
# Создание виртуального окружения
python -m venv .venv

# Активация (Windows)
.\.venv\Scripts\activate

# Установка зависимостей
pip install -e .

# Или с dev зависимостями
pip install -e ".[dev]"
```

## Конфигурация

1. Скопируйте `.env.example` в `.env`
2. Заполните все переменные:

```bash
# Email
EMAIL_HOST=imap.mail.ru
EMAIL_USER=your@mail.ru
EMAIL_PASSWORD=app_password

# WhatsApp (Green-API)
GREENAPI_INSTANCE_ID=your_id
GREENAPI_TOKEN=your_token

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_ID=your_telegram_id

# SMS.ru
SMSRU_API_ID=your_api_id
```

## Использование

```bash
# Запуск полной системы (почта + бот)
python -m src.main

# Только мониторинг почты
python -m src.main email

# Только Telegram бот
python -m src.main bot
```

## Тестирование

```bash
# Запуск тестов
pytest tests/ -v
```

## Структура

```
src/
├── main.py              # Точка входа
├── config.py            # Настройки
├── email_monitor.py     # IMAP мониторинг
├── parsers/             # HTML, PDF, DOCX парсеры
├── extractors/          # Regex для телефонов и заказов
├── senders/             # WhatsApp, Telegram, SMS
├── bot/                 # Telegram бот
└── database/            # SQLite логирование
```

## API Шлюзы

### WhatsApp
- [Green-API](https://green-api.com/) - рекомендуется
- [Wazzup24](https://wazzup24.com/) - альтернатива

### SMS
- [SMS.ru](https://sms.ru/) - рекомендуется
- [SMSC.ru](https://smsc.ru/) - альтернатива

## Автозапуск (Windows)

Создайте задачу в Task Scheduler:
```
Триггер: При запуске системы
Действие: python -m src.main
Рабочий каталог: D:\code\apteka
```
