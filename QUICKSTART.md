# Быстрый старт Navtelecom Server

## 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

## 2. Настройка PostgreSQL

### Вариант A: Локальная установка
```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# Создание БД
sudo -u postgres psql
CREATE DATABASE navtelecom_server;
CREATE USER navtelecom WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE navtelecom_server TO navtelecom;
\q

# Настройка схемы
python scripts/setup_database.py
```

### Вариант B: Docker
```bash
docker-compose up -d postgres
# Подождите 30 секунд для инициализации
```

## 3. Запуск сервера

```bash
python main.py
```

Сервер запустится на:
- **TCP порт 5221** - для устройств Navtelecom
- **HTTP порт 8080** - для REST API

## 4. Тестирование

### Отправка тестовых данных
```bash
python scripts/test_client.py
```

### Проверка API
```bash
python scripts/test_api.py
```

### Ручная проверка API
```bash
# Проверка здоровья
curl http://localhost:8080/api/health

# Список устройств (требует API ключ)
curl -H "Authorization: Bearer your-secret-api-key" \
     http://localhost:8080/api/devices
```

## 5. Настройка устройств

В NTC Configurator укажите:
- **IP адрес**: адрес вашего сервера
- **Порт**: 5221
- **Протокол**: TCP

## 6. Мониторинг

- **Логи**: `logs/server.log`
- **Консоль**: статистика каждую минуту
- **API**: `/api/health` для проверки состояния

## Структура проекта

```
├── main.py                 # Главный файл
├── config.yaml            # Конфигурация
├── requirements.txt       # Зависимости
├── src/                   # Исходный код
│   ├── config.py         # Управление конфигурацией
│   ├── database.py       # Работа с БД
│   ├── protocol.py       # Парсинг протокола
│   ├── server.py         # TCP сервер
│   └── api.py            # REST API
├── database/              # Схема БД
│   └── schema.sql
├── scripts/               # Утилиты
│   ├── setup_database.py # Настройка БД
│   ├── test_client.py    # Тестовый клиент
│   └── test_api.py       # Тест API
└── logs/                  # Логи
```

## Основные команды

```bash
# Запуск сервера
python main.py

# Настройка БД
python scripts/setup_database.py

# Тест отправки данных
python scripts/test_client.py

# Тест API
python scripts/test_api.py

# Docker (полная установка)
docker-compose up -d
```

## Решение проблем

### Сервер не запускается
1. Проверьте, что порты 5221 и 8080 свободны
2. Убедитесь, что PostgreSQL запущен
3. Проверьте конфигурацию в `config.yaml`

### Нет данных в БД
1. Проверьте подключение устройств к порту 5221
2. Посмотрите логи сервера
3. Запустите тестовый клиент для проверки

### API не отвечает
1. Проверьте API ключ в заголовке Authorization
2. Убедитесь, что сервер запущен на порту 8080
3. Проверьте логи на ошибки

## Конфигурация

Основные параметры в `config.yaml`:

```yaml
server:
  port: 5221        # Порт для устройств

database:
  host: localhost   # Хост БД
  port: 5432        # Порт БД

api:
  port: 8080        # Порт API
  api_key: "..."    # Ключ для API
```

## Безопасность

1. **Смените API ключ** в `config.yaml`
2. **Настройте firewall** для ограничения доступа
3. **Используйте HTTPS** в продакшене (требует дополнительной настройки)
4. **Регулярно обновляйте** зависимости

## Производительность

- **Максимум соединений**: 1000 (настраивается)
- **Размер пула БД**: 10 (настраивается)
- **Таймаут соединения**: 30 секунд
- **Keepalive**: каждые 60 секунд

Для высоких нагрузок рекомендуется:
- Увеличить размер пула БД
- Настроить индексы в PostgreSQL
- Использовать SSD для БД
- Мониторить использование ресурсов

