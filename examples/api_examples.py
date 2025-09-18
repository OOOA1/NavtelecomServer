"""Примеры использования API."""
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta


class APIExamples:
    """Примеры работы с API."""
    
    def __init__(self, base_url='http://localhost:8080', api_key='your-secret-api-key'):
        """Инициализация."""
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    async def example_get_all_devices(self):
        """Пример получения всех устройств."""
        print("=== Получение всех устройств ===")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices',
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Найдено устройств: {data['count']}")
                    
                    for device in data['data']:
                        print(f"  - {device['unique_id']}: {device.get('name', 'Без имени')}")
                        if device.get('last_seen'):
                            print(f"    Последняя активность: {device['last_seen']}")
                else:
                    print(f"Ошибка: {response.status}")
    
    async def example_get_device_positions(self, unique_id='123456789012345'):
        """Пример получения позиций устройства."""
        print(f"=== Позиции устройства {unique_id} ===")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/positions?limit=5',
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Найдено позиций: {data['count']}")
                    
                    for pos in data['data']:
                        print(f"  - {pos['fix_time']}: "
                              f"({pos['latitude']:.6f}, {pos['longitude']:.6f}) "
                              f"скорость: {pos.get('speed', 0):.1f} км/ч")
                else:
                    print(f"Ошибка: {response.status}")
    
    async def example_get_last_position(self, unique_id='123456789012345'):
        """Пример получения последней позиции."""
        print(f"=== Последняя позиция устройства {unique_id} ===")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/last',
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['data']:
                        pos = data['data']
                        print(f"Последняя позиция:")
                        print(f"  Время: {pos['fix_time']}")
                        print(f"  Координаты: ({pos['latitude']:.6f}, {pos['longitude']:.6f})")
                        print(f"  Скорость: {pos.get('speed', 0):.1f} км/ч")
                        print(f"  Курс: {pos.get('course', 0):.1f}°")
                        print(f"  Спутники: {pos.get('satellites', 0)}")
                    else:
                        print("Позиции не найдены")
                else:
                    print(f"Ошибка: {response.status}")
    
    async def example_get_can_data(self, unique_id='123456789012345'):
        """Пример получения CAN данных."""
        print(f"=== CAN данные устройства {unique_id} ===")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/can?limit=5',
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Найдено CAN записей: {data['count']}")
                    
                    for can in data['data']:
                        print(f"  - {can['received_at']}: CAN ID {can['can_id']}")
                        can_data = json.loads(can['can_data'])
                        print(f"    Данные: {can_data.get('hex_data', 'N/A')}")
                        if can.get('latitude') and can.get('longitude'):
                            print(f"    Позиция: ({can['latitude']:.6f}, {can['longitude']:.6f})")
                else:
                    print(f"Ошибка: {response.status}")
    
    async def example_get_raw_frames(self, unique_id='123456789012345'):
        """Пример получения сырых кадров."""
        print(f"=== Сырые кадры устройства {unique_id} ===")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/frames?limit=3',
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Найдено кадров: {data['count']}")
                    
                    for frame in data['data']:
                        print(f"  - {frame['received_at']}: {frame['frame_type']} кадр")
                        print(f"    Сырые данные: {frame['raw_data']}")
                        if frame.get('parsed_data'):
                            parsed = json.loads(frame['parsed_data'])
                            print(f"    Распарсенные данные: {parsed}")
                else:
                    print(f"Ошибка: {response.status}")
    
    async def example_filter_by_type(self, unique_id='123456789012345', frame_type='A'):
        """Пример фильтрации кадров по типу."""
        print(f"=== {frame_type} кадры устройства {unique_id} ===")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/frames?type={frame_type}&limit=3',
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Найдено {frame_type} кадров: {data['count']}")
                    
                    for frame in data['data']:
                        print(f"  - {frame['received_at']}: {frame['raw_data']}")
                else:
                    print(f"Ошибка: {response.status}")
    
    async def run_all_examples(self):
        """Запуск всех примеров."""
        print("🚀 Запуск примеров использования API")
        print("=" * 50)
        
        # Проверка здоровья
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.base_url}/api/health') as response:
                if response.status == 200:
                    print("✓ Сервер доступен")
                else:
                    print("✗ Сервер недоступен")
                    return
        
        # Примеры
        await self.example_get_all_devices()
        print()
        
        await self.example_get_last_position()
        print()
        
        await self.example_get_device_positions()
        print()
        
        await self.example_get_can_data()
        print()
        
        await self.example_get_raw_frames()
        print()
        
        await self.example_filter_by_type(frame_type='A')
        print()
        
        await self.example_filter_by_type(frame_type='T')
        print()
        
        print("✅ Все примеры выполнены")


async def main():
    """Главная функция."""
    examples = APIExamples()
    await examples.run_all_examples()


if __name__ == "__main__":
    asyncio.run(main())

