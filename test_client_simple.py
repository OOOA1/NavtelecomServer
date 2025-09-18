"""Упрощенный тестовый клиент."""
import asyncio
import socket
import time
import random
import json


class SimpleTestClient:
    """Упрощенный тестовый клиент."""
    
    def __init__(self, host='localhost', port=5221):
        """Инициализация клиента."""
        self.host = host
        self.port = port
        self.socket = None
    
    def connect(self):
        """Подключение к серверу."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        print(f"✓ Подключен к {self.host}:{self.port}")
    
    def disconnect(self):
        """Отключение от сервера."""
        if self.socket:
            self.socket.close()
            print("✓ Отключен от сервера")
    
    def send_frame(self, frame: str):
        """Отправка кадра."""
        if self.socket:
            self.socket.send(frame.encode('utf-8'))
            print(f"📤 Отправлен: {frame}")
    
    def generate_gps_frame(self, imei: str, lat: float, lon: float, speed: float = 0.0) -> str:
        """Генерация GPS кадра."""
        timestamp = int(time.time())
        satellites = random.randint(4, 12)
        hdop = round(random.uniform(1.0, 3.0), 1)
        
        return f"~A{imei},{timestamp},{lat},{lon},{speed},90.0,{satellites},{hdop}~"
    
    def generate_can_frame(self, imei: str, can_id: str) -> str:
        """Генерация CAN кадра."""
        can_data = [f"{random.randint(0, 255):02X}" for _ in range(8)]
        can_data_str = ",".join(can_data)
        
        return f"~T{imei},{can_id},{can_data_str}~"
    
    def generate_event_frame(self, imei: str, event_type: int = 1) -> str:
        """Генерация кадра события."""
        timestamp = int(time.time())
        return f"~E{imei},{event_type},{timestamp},Test event~"


def test_basic_connection():
    """Тест базового подключения."""
    print("🔍 Тест 1: Базовое подключение")
    
    client = SimpleTestClient()
    
    try:
        client.connect()
        print("✓ Подключение успешно")
        return True
    except Exception as e:
        print(f"✗ Ошибка подключения: {e}")
        return False
    finally:
        client.disconnect()


def test_gps_frames():
    """Тест отправки GPS кадров."""
    print("\n🔍 Тест 2: GPS кадры")
    
    client = SimpleTestClient()
    
    try:
        client.connect()
        
        test_imei = "123456789012345"
        base_lat = 55.7558  # Москва
        base_lon = 37.6176
        
        for i in range(3):
            lat = base_lat + random.uniform(-0.01, 0.01)
            lon = base_lon + random.uniform(-0.01, 0.01)
            speed = random.uniform(0, 60)
            
            gps_frame = client.generate_gps_frame(test_imei, lat, lon, speed)
            client.send_frame(gps_frame)
            
            time.sleep(1)
        
        print("✓ GPS кадры отправлены")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка отправки GPS: {e}")
        return False
    finally:
        client.disconnect()


def test_can_frames():
    """Тест отправки CAN кадров."""
    print("\n🔍 Тест 3: CAN кадры")
    
    client = SimpleTestClient()
    
    try:
        client.connect()
        
        test_imei = "123456789012345"
        
        for i in range(3):
            can_id = f"18{i:02X}"
            can_frame = client.generate_can_frame(test_imei, can_id)
            client.send_frame(can_frame)
            
            time.sleep(1)
        
        print("✓ CAN кадры отправлены")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка отправки CAN: {e}")
        return False
    finally:
        client.disconnect()


def test_event_frames():
    """Тест отправки кадров событий."""
    print("\n🔍 Тест 4: Кадры событий")
    
    client = SimpleTestClient()
    
    try:
        client.connect()
        
        test_imei = "123456789012345"
        
        for event_type in [1, 2, 3]:
            event_frame = client.generate_event_frame(test_imei, event_type)
            client.send_frame(event_frame)
            
            time.sleep(1)
        
        print("✓ Кадры событий отправлены")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка отправки событий: {e}")
        return False
    finally:
        client.disconnect()


def test_mixed_frames():
    """Тест отправки смешанных кадров."""
    print("\n🔍 Тест 5: Смешанные кадры")
    
    client = SimpleTestClient()
    
    try:
        client.connect()
        
        test_imei = "123456789012345"
        base_lat = 55.7558
        base_lon = 37.6176
        
        # GPS кадр
        gps_frame = client.generate_gps_frame(test_imei, base_lat, base_lon, 30.0)
        client.send_frame(gps_frame)
        time.sleep(1)
        
        # CAN кадр
        can_frame = client.generate_can_frame(test_imei, "180")
        client.send_frame(can_frame)
        time.sleep(1)
        
        # Событие
        event_frame = client.generate_event_frame(test_imei, 1)
        client.send_frame(event_frame)
        time.sleep(1)
        
        print("✓ Смешанные кадры отправлены")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка отправки смешанных кадров: {e}")
        return False
    finally:
        client.disconnect()


def run_all_tests():
    """Запуск всех тестов."""
    print("🚀 Запуск тестов Navtelecom сервера")
    print("=" * 50)
    
    tests = [
        ("Базовое подключение", test_basic_connection),
        ("GPS кадры", test_gps_frames),
        ("CAN кадры", test_can_frames),
        ("Кадры событий", test_event_frames),
        ("Смешанные кадры", test_mixed_frames),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"✓ {test_name}: {'PASS' if result else 'FAIL'}")
        except Exception as e:
            results.append((test_name, False))
            print(f"✗ {test_name}: ERROR - {e}")
    
    print(f"\n📊 Результаты: {sum(1 for _, result in results if result)}/{len(results)} тестов прошли")
    
    if all(result for _, result in results):
        print("🎉 Все тесты прошли успешно!")
    else:
        print("⚠️ Некоторые тесты не прошли. Проверьте логи сервера.")


if __name__ == "__main__":
    run_all_tests()

