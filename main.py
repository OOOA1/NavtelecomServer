"""
Главный файл для запуска SVOI Server - объединенный проект на базе navtel-server.
Современный сервер для приема и обработки пакетов протокола Navtelecom с поддержкой FastAPI.
"""
import asyncio
import signal
import sys
import logging
from pathlib import Path
import uvloop
import structlog

# Добавляем app в путь
sys.path.insert(0, str(Path(__file__).parent / 'app'))

from app.tcp_server import main as tcp_main
from app.api.main import app as api_app
import uvicorn
from app.settings import settings

# Настройка структурированного логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Настройка обычного логирования для совместимости
logging.basicConfig(
    level=getattr(logging, 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)


class SVOIServerApp:
    """Главный класс приложения SVOI Server."""
    
    def __init__(self):
        """Инициализация приложения."""
        self.api_server = None
        self.tcp_task = None
        self.shutdown_event = asyncio.Event()
    
    async def start(self):
        """Запуск приложения."""
        try:
            logger.info("Запуск SVOI Server...")
            
            # Устанавливаем uvloop для лучшей производительности
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            
            # Запускаем TCP сервер в фоновой задаче
            self.tcp_task = asyncio.create_task(tcp_main())
            
            # Запускаем API сервер
            config = uvicorn.Config(
                api_app,
                host=settings.api_host,
                port=settings.api_port,
                log_level="info"
            )
            self.api_server = uvicorn.Server(config)
            await self.api_server.serve()
            
        except Exception as e:
            logger.error("Ошибка запуска приложения", error=str(e))
            raise
    
    async def stop(self):
        """Остановка приложения."""
        try:
            logger.info("Остановка SVOI Server...")
            
            # Остановка API сервера
            if self.api_server:
                self.api_server.should_exit = True
            
            # Отмена TCP задачи
            if self.tcp_task:
                self.tcp_task.cancel()
                try:
                    await self.tcp_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("Сервер остановлен")
            
        except Exception as e:
            logger.error("Ошибка остановки приложения", error=str(e))
    
    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов."""
        def signal_handler(signum, frame):
            logger.info("Получен сигнал остановки", signal=signum)
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Главная функция."""
    app = SVOIServerApp()
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
        logger.error("Критическая ошибка", error=str(e))
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