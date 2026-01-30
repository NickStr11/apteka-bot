# VPS Deployment — Lessons Learned

Наработки из деплоя apteka-bot на Timeweb VPS (Jan 2026).

---

## 🔐 Google Credentials Security

**Проблема:** Google автоматически отзывает service account ключи если обнаружит их в публичном репозитории.

**Решение:**
```gitignore
# В .gitignore СРАЗУ добавляй:
*-credentials*.json
photo-gallery-*.json
*.json  # или вообще все JSON если уверен
```

**Если ключ засветился:**
1. Google Cloud Console → IAM → Service Accounts
2. Найти аккаунт → Keys → Add Key → Create new key (JSON)
3. Скачать новый, удалить старый из репо

---

## 📦 Systemd Service Template

```ini
[Unit]
Description=My Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/my-bot
EnvironmentFile=/opt/my-bot/.env    # ← ВАЖНО! Без этого .env не читается
ExecStart=/opt/my-bot/.venv/bin/python -m src.bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 🔄 Копирование файлов на сервер

**НЕ используй heredoc для JSON** — ломает переносы строк в private_key.

**Правильно:**
```powershell
scp "local_file.json" root@IP:/opt/project/
```

**Альтернатива через base64:**
```bash
# Локально
cat file.json | base64 -w 0 > encoded.txt

# На сервере
echo "BASE64_STRING" | base64 -d > file.json
```

---

## 🖥️ Windows → Linux Issues

**CRLF → LF конвертация:**
```bash
sed -i 's/\r$//' filename.json
file filename.json  # проверка формата
```

---

## ⏱️ JWT Time Sensitivity

Google OAuth требует точного времени на сервере. Проверка:
```bash
timedatectl  # должно быть NTP synchronized: yes
```

---

## 🚀 Автоматизация (TODO)

Для автодеплоя без ручного участия:

1. **SSH ключи вместо паролей:**
   ```bash
   # Локально
   ssh-keygen -t ed25519
   ssh-copy-id root@IP
   ```

2. **GitHub Actions** для автодеплоя при push:
   - На push → SSH на сервер → git pull → restart service

3. **Деплой скрипт на сервере:**
   ```bash
   #!/bin/bash
   cd /opt/my-bot
   git pull
   source .venv/bin/activate
   pip install -r requirements.txt
   systemctl restart my-bot
   ```
