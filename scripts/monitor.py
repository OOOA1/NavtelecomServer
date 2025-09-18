"""Скрипт для мониторинга сервера."""
import asyncio
import aiohttp
import json
import time
from datetime import datetime
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.config import config


class ServerMonitor:
    """Класс для мониторинга сервера."""
    
    def __init__(self, api_url='http://localhost:8080', api_key='your-secret-api-key'):
        """Инициализация монитора."""
        self.api_url = api_url
        self.headers = {'Authorization': f'Bearer {api_key}'}
        self.stats = {
            'requests': 0,
            'errors': 0,
            'last_check': None
        }
    
    async def check_health(self):
        """Проверка здоровья сервера."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{self.api_url}/api/health') as response:
                    data = await response.json()
                    self.stats['requests'] += 1
                    self.stats['last_check'] = datetime.now()
                    
                    if response.status == 200:
                        print(f"✓ Сервер здоров: {data['status']}")
                        return True
                    else:
                        print(f"✗ Сервер нездоров: {data}")
                        self.stats['errors'] += 1
                        return False
        except Exception as e:
            print(f"✗ Ошибка проверки здоровья: {e}")
            self.stats['errors'] += 1
            return False
    
    async def get_devices_count(self):
        """Получение количества устройств."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{self.api_url}/api/devices',
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        count = data.get('count', 0)
                        print(f"📱 Активных устройств: {count}")
                        return count
                    else:
                        print(f"✗ Ошибка получения устройств: {response.status}")
                        return 0
        except Exception as e:
            print(f"✗ Ошибка получения устройств: {e}")
            return 0
    
    async def get_recent_activity(self):
        """Получение недавней активности."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{self.api_url}/api/devices',
                    headers=self.headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        devices = data.get('data', [])
                        
                        recent_devices = []
                        for device in devices:
                            if device.get('last_seen'):
                                last_seen = datetime.fromisoformat(
                                    device['last_seen'].replace('Z', '+00:00')
                                )
                                if (datetime.now() - last_seen.replace(tzinfo=None)).seconds < 300:  # 5 минут
                                    recent_devices.append(device)
                        
                        print(f"🔄 Недавняя активность: {len(recent_devices)} устройств")
                        return recent_devices
                    else:
                        return []
        except Exception as e:
            print(f"✗ Ошибка получения активности: {e}")
            return []
    
    def print_stats(self):
        """Вывод статистики."""
        print(f"\n📊 Статистика мониторинга:")
        print(f"   Запросов: {self.stats['requests']}")
        print(f"   Ошибок: {self.stats['errors']}")
        if self.stats['last_check']:
            print(f"   Последняя проверка: {self.stats['last_check'].strftime('%H:%M:%S')}")
    
    async def run_monitoring(self, interval=60):
        """Запуск мониторинга."""
        print(f"🔍 Запуск мониторинга сервера (интервал: {interval}с)")
        print(f"🌐 API URL: {self.api_url}")
        print("-" * 50)
        
        while True:
            try:
                print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Проверка здоровья
                health_ok = await self.check_health()
                
                if health_ok:
                    # Получение статистики
                    await self.get_devices_count()
                    await self.get_recent_activity()
                
                self.print_stats()
                
                # Ожидание следующей проверки
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n🛑 Мониторинг остановлен пользователем")
                break
            except Exception as e:
                print(f"✗ Ошибка мониторинга: {e}")
                await asyncio.sleep(interval)


async def main():
    """Главная функция."""
    monitor = ServerMonitor()
    await monitor.run_monitoring(interval=30)  # Проверка каждые 30 секунд


if __name__ == "__main__":
    asyncio.run(main())

