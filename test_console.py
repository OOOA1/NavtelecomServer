"""Тест сервера с консольным выводом."""
import asyncio
import socket
import time
import random
from datetime import datetime


class ConsoleTest:
    """Тест с консольным выводом."""
    
    def __init__(self):
        """Инициализация теста."""
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Логирование результата теста."""
        status = "✅" if success else "❌"
        self.test_results.append((test_name, success, details))
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
    
    def test_connection(self):
        """Тест подключения."""
        print("🔍 Тест подключения к серверу...")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', 5221))
            sock.close()
            self.log_test("Подключение", True, "Сервер доступен")
            return True
        except Exception as e:
            self.log_test("Подключение", False, str(e))
            return False
    
    def test_gps_data(self):
        """Тест отправки GPS данных."""
        print("\n🔍 Тест отправки GPS данных...")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', 5221))
            
            # Отправка GPS кадра
            test_imei = "123456789012345"
            timestamp = int(time.time())
            lat = 55.7558 + random.uniform(-0.01, 0.01)
            lon = 37.6176 + random.uniform(-0.01, 0.01)
            speed = random.uniform(0, 60)
            satellites = random.randint(4, 12)
            hdop = round(random.uniform(1.0, 3.0), 1)
            
            gps_frame = f"~A{test_imei},{timestamp},{lat},{lon},{speed},90.0,{satellites},{hdop}~"
            
            print(f"📤 Отправка: {gps_frame}")
            sock.send(gps_frame.encode('utf-8'))
            
            # Получение ответа
            time.sleep(0.5)
            sock.settimeout(2)
            response = sock.recv(1024)
            
            if response and b'ACK' in response:
                self.log_test("GPS данные", True, f"Получен ACK: {response.decode('utf-8')}")
                success = True
            else:
                self.log_test("GPS данные", False, "ACK не получен")
                success = False
            
            sock.close()
            return success
            
        except Exception as e:
            self.log_test("GPS данные", False, str(e))
            return False
    
    def test_can_data(self):
        """Тест отправки CAN данных."""
        print("\n🔍 Тест отправки CAN данных...")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', 5221))
            
            # Отправка CAN кадра
            test_imei = "123456789012345"
            can_id = "180"
            can_data = [f"{random.randint(0, 255):02X}" for _ in range(8)]
            can_data_str = ",".join(can_data)
            
            can_frame = f"~T{test_imei},{can_id},{can_data_str}~"
            
            print(f"📤 Отправка: {can_frame}")
            sock.send(can_frame.encode('utf-8'))
            
            # Получение ответа
            time.sleep(0.5)
            sock.settimeout(2)
            response = sock.recv(1024)
            
            if response and b'ACK' in response:
                self.log_test("CAN данные", True, f"Получен ACK: {response.decode('utf-8')}")
                success = True
            else:
                self.log_test("CAN данные", False, "ACK не получен")
                success = False
            
            sock.close()
            return success
            
        except Exception as e:
            self.log_test("CAN данные", False, str(e))
            return False
    
    def test_event_data(self):
        """Тест отправки данных событий."""
        print("\n🔍 Тест отправки данных событий...")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', 5221))
            
            # Отправка кадра события
            test_imei = "123456789012345"
            event_type = 1
            timestamp = int(time.time())
            event_data = "Test event"
            
            event_frame = f"~E{test_imei},{event_type},{timestamp},{event_data}~"
            
            print(f"📤 Отправка: {event_frame}")
            sock.send(event_frame.encode('utf-8'))
            
            # Получение ответа
            time.sleep(0.5)
            sock.settimeout(2)
            response = sock.recv(1024)
            
            if response and b'ACK' in response:
                self.log_test("События", True, f"Получен ACK: {response.decode('utf-8')}")
                success = True
            else:
                self.log_test("События", False, "ACK не получен")
                success = False
            
            sock.close()
            return success
            
        except Exception as e:
            self.log_test("События", False, str(e))
            return False
    
    def run_all_tests(self):
        """Запуск всех тестов."""
        print("🚀 ТЕСТИРОВАНИЕ NAVTELECOM СЕРВЕРА")
        print("=" * 50)
        print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Запуск тестов
        self.test_connection()
        self.test_gps_data()
        self.test_can_data()
        self.test_event_data()
        
        # Подсчет результатов
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, success, _ in self.test_results if success)
        
        print("\n" + "=" * 50)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        print("=" * 50)
        
        for test_name, success, details in self.test_results:
            status = "✅" if success else "❌"
            print(f"{status} {test_name}")
            if details:
                print(f"    {details}")
        
        print(f"\n📈 Итого: {passed_tests}/{total_tests} тестов прошли")
        
        if passed_tests == total_tests:
            print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        elif passed_tests >= total_tests * 0.75:
            print("⚠️ Большинство тестов прошли")
        else:
            print("❌ Много тестов не прошли")
        
        print("\n💡 Для просмотра данных запустите:")
        print("   python show_data.py")
        print("   python console_monitor.py")


def main():
    """Главная функция."""
    test = ConsoleTest()
    test.run_all_tests()


if __name__ == "__main__":
    main()

