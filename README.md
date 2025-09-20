# SVOI Server

Современный высокопроизводительный сервер для приема и обработки пакетов протокола Navtelecom. Основан на архитектуре navtel-server с улучшениями и дополнительными возможностями. Сервер принимает TCP-соединения от устройств, парсит кадры протокола, сохраняет данные в PostgreSQL и предоставляет REST API для доступа к данным.

## Возможности

### Основные функции
- **TCP-сервер** для приема данных от устройств Navtelecom
- **Парсинг протокола** с поддержкой кадров ~A (GPS), ~T/~X (CAN), ~E (события)
- **Автоматические ACK ответы** для корректной работы с устройствами
- **PostgreSQL** для хранения данных
- **FastAPI REST API** с версионированием (v1/v2)
- **Структурированное логирование** (JSON)
- **Мониторинг соединений** и статистика
- **CAN парсинг** с поддержкой J1939, OBD2, Scania, Volvo
- **Batch обработка** для высокой производительности
- **Backpressure управление** для предотвращения перегрузок
- **Canary deployments** для безопасных обновлений
- **Feature flags** для управления функциональностью
- **SLO мониторинг** и алерты
- **Hot reload** для обновлений без перезапуска

### Операционные возможности
- **Runbooks (SOP)** - детальные процедуры для решения инцидентов
- **Мониторинг и алерты** - Prometheus правила для автоматического обнаружения проблем
- **Smoke tests** - автоматические проверки здоровья системы
- **Backup и восстановление** - процедуры резервного копирования
- **Безопасность** - мониторинг безопасности и инцидентов
- **Операционные скрипты** - автоматизация рутинных задач

## Установка

### Требования

- Python 3.9+
- PostgreSQL 12+
- pip
- uvloop (для лучшей производительности)
- FastAPI и Uvicorn

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

Сервер автоматически запускает:
- TCP сервер на порту 5221 (по умолчанию)
- API сервер на порту 8080 (по умолчанию)

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

#### Версия 1 (Deprecated)
- `GET /api/v1/health` - Проверка состояния сервера
- `GET /api/v1/devices` - Список устройств
- `GET /api/v1/devices/{device_id}/telemetry` - Телеметрия устройства
- `GET /api/v1/devices/{device_id}/raw-frames` - Сырые кадры

#### Версия 2 (Current)
- `GET /api/v2/health` - Проверка состояния сервера
- `GET /api/v2/stats` - Статистика сервера
- `GET /api/v2/devices` - Список устройств
- `GET /api/v2/devices/{device_id}/telemetry` - Телеметрия устройства
- `GET /api/v2/devices/{device_id}/can-data` - CAN данные
- `GET /api/v2/devices/{device_id}/raw-frames` - Сырые кадры
- `GET /api/v2/raw-frames` - Все сырые кадры

#### Общие
- `GET /health` - Проверка состояния сервера
- `GET /docs` - Swagger документация
- `GET /redoc` - ReDoc документация

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

## Операционные процедуры

### Runbooks (SOP)
Детальные процедуры для решения инцидентов находятся в папке `runbooks/`:

- `01-no-frames.md` - Нет кадров от устройств
- `02-queue-spike.md` - Перегрузка системы
- `03-decode-errors-spike.md` - Ошибки декодирования
- `04-db-slow.md` - Медленная работа БД
- `05-api-5xx-spike.md` - Ошибки API

### Мониторинг и алерты
- **Prometheus правила**: `alerts/prometheus-rules.yml`
- **Smoke tests**: `playbooks/smoke.sh`
- **Операционные команды**: `make help`

### Быстрые команды
```bash
# Проверка здоровья системы
make health-check

# Smoke test
make smoke-test

# Просмотр runbook
make runbook-no-frames

# Экстренный перезапуск
make emergency-restart

# Сбор логов
make emergency-logs
```

### Ежедневные операции
```bash
# Ежедневная проверка
make daily-ops

# Проверка безопасности
make security-check

# Проверка производительности
make perf-check

# Техническое обслуживание
make maintenance
```

## Поддержка

При возникновении проблем:
1. **Используйте runbooks** - детальные процедуры в папке `runbooks/`
2. **Запустите smoke test** - `make smoke-test`
3. **Проверьте логи сервера** - `make logs`
4. **Используйте операционные команды** - `make help`
5. **Проверьте мониторинг** - `make monitor`

