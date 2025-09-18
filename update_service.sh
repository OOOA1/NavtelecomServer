#!/bin/bash

# Скрипт для обновления systemd сервиса

echo "🔄 Обновление systemd сервиса..."

# Остановка сервиса
sudo systemctl stop navtelecom-server

# Обновление файла сервиса
sudo tee /etc/systemd/system/navtelecom-server.service > /dev/null <<EOF
[Unit]
Description=Universal Navtelecom Server (Navtelecom + FLEX)
After=network.target

[Service]
Type=simple
User=navtelecom
WorkingDirectory=/home/navtelecom/navtelecom-server
Environment=PATH=/home/navtelecom/navtelecom-server/venv/bin
ExecStart=/home/navtelecom/navtelecom-server/venv/bin/python test_server_simple.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd
sudo systemctl daemon-reload

# Запуск сервиса
sudo systemctl start navtelecom-server

# Проверка статуса
echo "📊 Статус сервиса:"
sudo systemctl status navtelecom-server --no-pager

echo "✅ Сервис обновлен и запущен!"
echo "🔍 Для мониторинга логов используйте:"
echo "   sudo journalctl -u navtelecom-server -f"
