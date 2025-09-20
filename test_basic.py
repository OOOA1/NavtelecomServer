#!/usr/bin/env python3
"""
Базовый тест для проверки структуры проекта SVOI Server.
"""
import sys
from pathlib import Path

def test_project_structure():
    """Тест структуры проекта."""
    try:
        print("Проверка структуры проекта...")
        
        base_path = Path(__file__).parent
        
        # Проверяем наличие важных файлов и папок
        important_items = [
            "main.py",
            "requirements.txt",
            "README.md",
            "alembic.ini",
            "app/",
            "app/__init__.py",
            "app/settings.py",
            "app/api/",
            "app/api/main.py",
            "app/tcp_server.py",
            "app/models.py",
            "app/db.py",
            "database/",
            "dicts/",
            "runbooks/",
            "scripts/"
        ]
        
        missing_items = []
        
        for item in important_items:
            full_path = base_path / item
            if full_path.exists():
                print(f"✓ {item}")
            else:
                print(f"✗ {item} - НЕ НАЙДЕН")
                missing_items.append(item)
        
        if missing_items:
            print(f"\nОтсутствуют файлы/папки: {missing_items}")
            return False
        else:
            print("\n✓ Все важные файлы и папки найдены!")
            return True
            
    except Exception as e:
        print(f"✗ Ошибка проверки структуры: {e}")
        return False

def test_file_contents():
    """Тест содержимого ключевых файлов."""
    try:
        print("\nПроверка содержимого файлов...")
        
        base_path = Path(__file__).parent
        
        # Проверяем main.py
        main_py = base_path / "main.py"
        if main_py.exists():
            content = main_py.read_text(encoding='utf-8')
            if "SVOIServerApp" in content and "uvloop" in content:
                print("✓ main.py содержит правильную структуру")
            else:
                print("✗ main.py не содержит ожидаемую структуру")
                return False
        
        # Проверяем requirements.txt
        req_txt = base_path / "requirements.txt"
        if req_txt.exists():
            content = req_txt.read_text(encoding='utf-8')
            required_packages = ["fastapi", "uvicorn", "sqlalchemy", "asyncpg"]
            missing_packages = []
            for package in required_packages:
                if package not in content.lower():
                    missing_packages.append(package)
            
            if missing_packages:
                print(f"✗ requirements.txt не содержит пакеты: {missing_packages}")
                return False
            else:
                print("✓ requirements.txt содержит все необходимые пакеты")
        
        # Проверяем README.md
        readme = base_path / "README.md"
        if readme.exists():
            content = readme.read_text(encoding='utf-8')
            if "SVOI Server" in content and "FastAPI" in content:
                print("✓ README.md содержит правильную информацию")
            else:
                print("✗ README.md не содержит ожидаемую информацию")
                return False
        
        print("✓ Содержимое файлов проверено!")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка проверки содержимого: {e}")
        return False

def test_backup_exists():
    """Проверяем наличие резервной копии."""
    try:
        print("\nПроверка резервной копии...")
        
        base_path = Path(__file__).parent.parent
        backup_path = base_path / "Svoi Server_backup"
        
        if backup_path.exists():
            print("✓ Резервная копия найдена")
            return True
        else:
            print("✗ Резервная копия не найдена")
            return False
            
    except Exception as e:
        print(f"✗ Ошибка проверки резервной копии: {e}")
        return False

def main():
    """Главная функция тестирования."""
    print("=== Базовый тест SVOI Server ===\n")
    
    # Тест структуры
    structure_success = test_project_structure()
    
    # Тест содержимого
    content_success = test_file_contents()
    
    # Тест резервной копии
    backup_success = test_backup_exists()
    
    # Итоговый результат
    print("\n=== Результаты тестирования ===")
    print(f"Структура проекта: {'✓' if structure_success else '✗'}")
    print(f"Содержимое файлов: {'✓' if content_success else '✗'}")
    print(f"Резервная копия: {'✓' if backup_success else '✗'}")
    
    if all([structure_success, content_success, backup_success]):
        print("\n🎉 Все базовые тесты пройдены!")
        print("Проект успешно перенесен из navtel-server в Svoi Server.")
        print("\nСледующие шаги:")
        print("1. Установите зависимости: pip install -r requirements.txt")
        print("2. Настройте базу данных PostgreSQL")
        print("3. Запустите сервер: python main.py")
        return 0
    else:
        print("\n❌ Некоторые тесты не пройдены. Проверьте ошибки выше.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
