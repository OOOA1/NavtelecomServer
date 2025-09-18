"""Скрипт для настройки базы данных."""
import asyncio
import asyncpg
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.config import config


async def setup_database():
    """Настройка базы данных."""
    try:
        # Подключение к PostgreSQL
        conn = await asyncpg.connect(
            host=config.database['host'],
            port=config.database['port'],
            user=config.database['user'],
            password=config.database['password'],
            database='postgres'  # Подключаемся к системной БД
        )
        
        print("Подключение к PostgreSQL установлено")
        
        # Чтение схемы
        schema_path = Path(__file__).parent.parent / 'database' / 'schema.sql'
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        # Выполнение SQL
        await conn.execute(schema_sql)
        
        print("База данных успешно настроена")
        
        await conn.close()
        
    except Exception as e:
        print(f"Ошибка настройки базы данных: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(setup_database())

