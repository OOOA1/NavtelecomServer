# 🚀 НАЧНИТЕ ЗДЕСЬ - Navtelecom Server

## Быстрый запуск за 5 минут

### 1️⃣ Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2️⃣ Настройка базы данных
```bash
# Установите PostgreSQL и создайте БД
python scripts/setup_database.py
```

### 3️⃣ Запуск сервера
```bash
python main.py
```

### 4️⃣ Тестирование
```bash
# В другом терминале
python scripts/test_client.py
```

## ✅ Готово!

Сервер работает на:
- **TCP порт 5221** - для устройств Navtelecom
- **HTTP порт 8080** - для REST API

## 📋 Что дальше?

1. **Настройте устройства** в NTC Configurator:
   - IP: адрес вашего сервера
   - Порт: 5221
   - Протокол: TCP

2. **Проверьте API**:
   ```bash
   curl http://localhost:8080/api/health
   ```

3. **Мониторинг**:
   ```bash
   python scripts/monitor.py
   ```

## 📚 Документация

- **QUICKSTART.md** - подробная инструкция
- **README.md** - полная документация
- **PROJECT_INFO.md** - информация о проекте
- **examples/** - примеры использования API

## 🔧 Конфигурация

Отредактируйте `config.yaml` для настройки:
- Порты сервера
- Параметры БД
- API ключи
- Логирование

## 🐳 Docker (альтернатива)

```bash
docker-compose up -d
```

## ❓ Проблемы?

1. Проверьте логи в `logs/server.log`
2. Убедитесь, что порты свободны
3. Проверьте подключение к PostgreSQL
4. Запустите тестовые скрипты

---

**Удачного использования! 🎉**

