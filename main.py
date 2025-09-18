"""Главный файл для запуска Navtelecom сервера."""
import asyncio
import signal
import sys
import logging
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.config import config
from src.server import server
from src.api import start_api_server
from src.database import db

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.logging.get('level', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.logging.get('file', 'server.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class NavtelecomServerApp:
    """Главный класс приложения."""
    
    def __init__(self):
        """Инициализация приложения."""
        self.api_runner = None
        self.shutdown_event = asyncio.Event()
    
    async def start(self):
        """Запуск приложения."""
        try:
            logger.info("Запуск Navtelecom сервера...")
            
            # Подключение к базе данных
            await db.connect()
            
            # Запуск API сервера
            self.api_runner = await start_api_server()
            
            # Запуск основного TCP сервера
            await server.start()
            
        except Exception as e:
            logger.error(f"Ошибка запуска приложения: {e}")
            raise
    
    async def stop(self):
        """Остановка приложения."""
        try:
            logger.info("Остановка Navtelecom сервера...")
            
            # Остановка API сервера
            if self.api_runner:
                await self.api_runner.cleanup()
            
            # Остановка TCP сервера
            await server.stop()
            
            # Отключение от базы данных
            await db.disconnect()
            
            logger.info("Сервер остановлен")
            
        except Exception as e:
            logger.error(f"Ошибка остановки приложения: {e}")
    
    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов."""
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}, инициируется остановка...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Главная функция."""
    app = NavtelecomServerApp()
    app.setup_signal_handlers()
    
    try:
        # Запуск приложения в фоновой задаче
        server_task = asyncio.create_task(app.start())
        
        # Ожидание сигнала остановки
        await app.shutdown_event.wait()
        
        # Отмена задачи сервера
        server_task.cancel()
        
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСервер остановлен пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)

