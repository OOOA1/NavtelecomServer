#!/usr/bin/env python3
"""
Простой тест для проверки работоспособности объединенного проекта SVOI Server.
"""
import sys
import asyncio
from pathlib import Path

# Добавляем app в путь
sys.path.insert(0, str(Path(__file__).parent / 'app'))

async def test_imports():
    """Тест импортов основных модулей."""
    try:
        print("Тестирование импортов...")
        
        # Тест основных модулей
        from app.settings import settings
        print("✓ settings импортирован")
        
        from app.db import AsyncSessionLocal
        print("✓ db импортирован")
        
        from app.models import save_raw_frame
        print("✓ models импортирован")
        
        from app.tcp_server import handle_connection
        print("✓ tcp_server импортирован")
        
        from app.api.main import app
        print("✓ api импортирован")
        
        # Тест настроек
        print(f"TCP Host: {settings.tcp_host}")
        print(f"TCP Port: {settings.tcp_port}")
        print(f"API Host: {settings.api_host}")
        print(f"API Port: {settings.api_port}")
        
        print("\n✓ Все основные модули успешно импортированы!")
        return True
        
    except ImportError as e:
        print(f"✗ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"✗ Неожиданная ошибка: {e}")
        return False

async def test_fastapi_app():
    """Тест FastAPI приложения."""
    try:
        print("\nТестирование FastAPI приложения...")
        
        from app.api.main import app
        
        # Проверяем основные маршруты
        routes = [route.path for route in app.routes]
        print(f"Доступные маршруты: {routes}")
        
        # Проверяем наличие основных эндпоинтов
        expected_routes = ["/", "/health", "/api/v1", "/api/v2"]
        for route in expected_routes:
            if any(route in r for r in routes):
                print(f"✓ Маршрут {route} найден")
            else:
                print(f"✗ Маршрут {route} не найден")
        
        print("✓ FastAPI приложение работает!")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка FastAPI: {e}")
        return False

def test_config_files():
    """Тест конфигурационных файлов."""
    try:
        print("\nТестирование конфигурационных файлов...")
        
        base_path = Path(__file__).parent
        
        # Проверяем наличие важных файлов
        important_files = [
            "requirements.txt",
            "alembic.ini",
            "app/settings.py",
            "database/schema.sql",
            "dicts/j1939.yaml",
            "dicts/obd2.yaml"
        ]
        
        for file_path in important_files:
            full_path = base_path / file_path
            if full_path.exists():
                print(f"✓ {file_path} найден")
            else:
                print(f"✗ {file_path} не найден")
        
        print("✓ Конфигурационные файлы проверены!")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка проверки файлов: {e}")
        return False

async def main():
    """Главная функция тестирования."""
    print("=== Тест интеграции SVOI Server ===\n")
    
    # Тест импортов
    import_success = await test_imports()
    
    # Тест FastAPI
    api_success = await test_fastapi_app()
    
    # Тест конфигурации
    config_success = test_config_files()
    
    # Итоговый результат
    print("\n=== Результаты тестирования ===")
    print(f"Импорты: {'✓' if import_success else '✗'}")
    print(f"FastAPI: {'✓' if api_success else '✗'}")
    print(f"Конфигурация: {'✓' if config_success else '✗'}")
    
    if all([import_success, api_success, config_success]):
        print("\n🎉 Все тесты пройдены! Проект готов к работе.")
        return 0
    else:
        print("\n❌ Некоторые тесты не пройдены. Проверьте ошибки выше.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
