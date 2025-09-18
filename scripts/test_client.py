"""Тестовый клиент для проверки сервера."""
import asyncio
import socket
import time
import random


class TestClient:
    """Тестовый клиент для отправки данных Navtelecom."""
    
    def __init__(self, host='localhost', port=5221):
        """Инициализация клиента."""
        self.host = host
        self.port = port
        self.socket = None
    
    async def connect(self):
        """Подключение к серверу."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        print(f"Подключен к {self.host}:{self.port}")
    
    def disconnect(self):
        """Отключение от сервера."""
        if self.socket:
            self.socket.close()
            print("Отключен от сервера")
    
    def send_frame(self, frame: str):
        """Отправка кадра."""
        if self.socket:
            self.socket.send(frame.encode('utf-8'))
            print(f"Отправлен кадр: {frame}")
    
    def generate_gps_frame(self, imei: str, lat: float, lon: float, speed: float = 0.0) -> str:
        """Генерация GPS кадра."""
        timestamp = int(time.time())
        satellites = random.randint(4, 12)
        hdop = round(random.uniform(1.0, 3.0), 1)
        
        return f"~A{imei},{timestamp},{lat},{lon},{speed},90.0,{satellites},{hdop}~"
    
    def generate_can_frame(self, imei: str, can_id: str) -> str:
        """Генерация CAN кадра."""
        # Генерируем случайные CAN данные
        can_data = [f"{random.randint(0, 255):02X}" for _ in range(8)]
        can_data_str = ",".join(can_data)
        
        return f"~T{imei},{can_id},{can_data_str}~"
    
    def generate_event_frame(self, imei: str, event_type: int = 1) -> str:
        """Генерация кадра события."""
        timestamp = int(time.time())
        return f"~E{imei},{event_type},{timestamp},Test event~"


async def test_server():
    """Тестирование сервера."""
    client = TestClient()
    
    try:
        await client.connect()
        
        # Тестовые данные
        test_imei = "123456789012345"
        base_lat = 55.7558  # Москва
        base_lon = 37.6176
        
        print("Начинаем тестирование...")
        
        # Отправляем GPS кадры
        for i in range(5):
            lat = base_lat + random.uniform(-0.01, 0.01)
            lon = base_lon + random.uniform(-0.01, 0.01)
            speed = random.uniform(0, 60)
            
            gps_frame = client.generate_gps_frame(test_imei, lat, lon, speed)
            client.send_frame(gps_frame)
            
            await asyncio.sleep(1)
        
        # Отправляем CAN кадры
        for i in range(3):
            can_id = f"18{i:02X}"
            can_frame = client.generate_can_frame(test_imei, can_id)
            client.send_frame(can_frame)
            
            await asyncio.sleep(1)
        
        # Отправляем событие
        event_frame = client.generate_event_frame(test_imei, 1)
        client.send_frame(event_frame)
        
        print("Тестирование завершено")
        
    except Exception as e:
        print(f"Ошибка тестирования: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_server())

