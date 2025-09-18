# Navtelecom Server

Самописный сервер для приема и обработки пакетов протокола Navtelecom. Сервер принимает TCP-соединения от устройств, парсит кадры ~A/~T/~X/~E, сохраняет данные в PostgreSQL и предоставляет REST API для доступа к данным.

## Возможности

- **TCP-сервер** для приема данных от устройств Navtelecom
- **Парсинг протокола** с поддержкой кадров ~A (GPS), ~T/~X (CAN), ~E (события)
- **Автоматические ACK ответы** для корректной работы с устройствами
- **PostgreSQL** для хранения данных
- **REST API** для доступа к данным
- **Структурированное логирование**
- **Мониторинг соединений** и статистика

## Установка

### Требования

- Python 3.8+
- PostgreSQL 12+
- pip

### Установка зависимостей

```bash
pip install -r requirements.txt
```

### Настройка базы данных

1. Установите PostgreSQL
2. Создайте базу данных и пользователя:

```sql
CREATE DATABASE navtelecom_server;
CREATE USER navtelecom WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE navtelecom_server TO navtelecom;
```

3. Запустите скрипт настройки:

```bash
python scripts/setup_database.py
```

### Конфигурация

Отредактируйте файл `config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 5221

database:
  host: "localhost"
  port: 5432
  name: "navtelecom_server"
  user: "navtelecom"
  password: "password"

api:
  host: "0.0.0.0"
  port: 8080
  api_key: "your-secret-api-key"
```

## Запуск

### Основной сервер

```bash
python main.py
```

### Тестирование

1. **Тестовый клиент** (отправка данных):
```bash
python scripts/test_client.py
```

2. **Тест API**:
```bash
python scripts/test_api.py
```

## API

### Аутентификация

Все API запросы требуют Bearer токен в заголовке:
```
Authorization: Bearer your-secret-api-key
```

### Эндпоинты

- `GET /api/health` - Проверка состояния сервера
- `GET /api/devices` - Список устройств
- `GET /api/devices/{unique_id}/positions` - Позиции устройства
- `GET /api/devices/{unique_id}/last` - Последняя позиция
- `GET /api/devices/{unique_id}/can` - CAN данные
- `GET /api/devices/{unique_id}/frames` - Сырые кадры

### Примеры запросов

```bash
# Получение списка устройств
curl -H "Authorization: Bearer your-secret-api-key" \
     http://localhost:8080/api/devices

# Получение последней позиции
curl -H "Authorization: Bearer your-secret-api-key" \
     http://localhost:8080/api/devices/123456789012345/last

# Получение CAN данных
curl -H "Authorization: Bearer your-secret-api-key" \
     http://localhost:8080/api/devices/123456789012345/can
```

## Протокол

### Поддерживаемые кадры

- **~A** - GPS данные (координаты, скорость, курс, спутники)
- **~T** - CAN данные (стандартный формат)
- **~X** - Расширенные CAN данные
- **~E** - События

### Формат кадров

#### GPS кадр (~A)
```
~A{IMEI},{timestamp},{lat},{lon},{speed},{course},{satellites},{hdop}~
```

#### CAN кадр (~T/~X)
```
~T{IMEI},{can_id},{byte1},{byte2},...,{byte8}~
```

#### Событие (~E)
```
~E{IMEI},{event_type},{timestamp},{description}~
```

## Структура базы данных

### Таблицы

- **devices** - Устройства (IMEI, имя, статус)
- **positions** - GPS позиции (координаты, время, скорость)
- **raw_frames** - Сырые кадры (оригинальные данные)
- **can_data** - CAN данные (с привязкой к позициям)

## Логирование

Логи сохраняются в файл `logs/server.log` и выводятся в консоль. Используется структурированное логирование в формате JSON.

## Мониторинг

Сервер ведет статистику:
- Количество активных соединений
- Обработанные кадры
- Ошибки
- Активные устройства

## Развертывание

### systemd сервис

Создайте файл `/etc/systemd/system/navtelecom-server.service`:

```ini
[Unit]
Description=Navtelecom Server
After=network.target postgresql.service

[Service]
Type=simple
User=navtelecom
WorkingDirectory=/opt/navtelecom-server
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Docker

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5221 8080

CMD ["python", "main.py"]
```

## Безопасность

- Используйте сильные API ключи
- Настройте firewall для ограничения доступа
- Регулярно обновляйте зависимости
- Мониторьте логи на предмет подозрительной активности

## Поддержка

При возникновении проблем:
1. Проверьте логи сервера
2. Убедитесь в корректности конфигурации
3. Проверьте подключение к базе данных
4. Используйте тестовые скрипты для диагностики

