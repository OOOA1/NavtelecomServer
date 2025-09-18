"""Тестовый скрипт для проверки API."""
import asyncio
import aiohttp
import json


class APITester:
    """Класс для тестирования API."""
    
    def __init__(self, base_url='http://localhost:8080', api_key='your-secret-api-key'):
        """Инициализация тестера."""
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    async def test_health(self):
        """Тест проверки здоровья."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.base_url}/api/health') as response:
                data = await response.json()
                print(f"Health check: {response.status} - {data}")
                return response.status == 200
    
    async def test_devices(self):
        """Тест получения устройств."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices',
                headers=self.headers
            ) as response:
                data = await response.json()
                print(f"Devices: {response.status} - {data}")
                return response.status == 200
    
    async def test_device_positions(self, unique_id='123456789012345'):
        """Тест получения позиций устройства."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/positions',
                headers=self.headers
            ) as response:
                data = await response.json()
                print(f"Positions: {response.status} - {data}")
                return response.status == 200
    
    async def test_last_position(self, unique_id='123456789012345'):
        """Тест получения последней позиции."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/last',
                headers=self.headers
            ) as response:
                data = await response.json()
                print(f"Last position: {response.status} - {data}")
                return response.status == 200
    
    async def test_can_data(self, unique_id='123456789012345'):
        """Тест получения CAN данных."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/can',
                headers=self.headers
            ) as response:
                data = await response.json()
                print(f"CAN data: {response.status} - {data}")
                return response.status == 200
    
    async def test_raw_frames(self, unique_id='123456789012345'):
        """Тест получения сырых кадров."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/api/devices/{unique_id}/frames',
                headers=self.headers
            ) as response:
                data = await response.json()
                print(f"Raw frames: {response.status} - {data}")
                return response.status == 200


async def run_tests():
    """Запуск всех тестов."""
    tester = APITester()
    
    print("Запуск тестов API...")
    
    tests = [
        ("Health Check", tester.test_health()),
        ("Devices", tester.test_devices()),
        ("Positions", tester.test_device_positions()),
        ("Last Position", tester.test_last_position()),
        ("CAN Data", tester.test_can_data()),
        ("Raw Frames", tester.test_raw_frames()),
    ]
    
    results = []
    for test_name, test_coro in tests:
        try:
            result = await test_coro
            results.append((test_name, result))
            print(f"✓ {test_name}: {'PASS' if result else 'FAIL'}")
        except Exception as e:
            results.append((test_name, False))
            print(f"✗ {test_name}: ERROR - {e}")
    
    print(f"\nРезультаты: {sum(1 for _, result in results if result)}/{len(results)} тестов прошли")


if __name__ == "__main__":
    asyncio.run(run_tests())

