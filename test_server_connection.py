"""Простой тест подключения к серверу."""
import socket
import time
import random


def test_server_connection():
    """Тест подключения к серверу."""
    print("🔍 Тест подключения к серверу")
    print("=" * 40)
    
    try:
        # Подключение к серверу
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 5221))
        print("✓ Подключение к серверу успешно")
        
        # Отправка тестового GPS кадра
        test_imei = "123456789012345"
        timestamp = int(time.time())
        lat = 55.7558 + random.uniform(-0.01, 0.01)
        lon = 37.6176 + random.uniform(-0.01, 0.01)
        speed = random.uniform(0, 60)
        satellites = random.randint(4, 12)
        hdop = round(random.uniform(1.0, 3.0), 1)
        
        gps_frame = f"~A{test_imei},{timestamp},{lat},{lon},{speed},90.0,{satellites},{hdop}~"
        
        print(f"📤 Отправка GPS кадра: {gps_frame}")
        sock.send(gps_frame.encode('utf-8'))
        
        # Ожидание ответа
        time.sleep(1)
        
        # Попытка получить ответ
        try:
            sock.settimeout(2)
            response = sock.recv(1024)
            if response:
                print(f"📥 Получен ответ: {response.decode('utf-8')}")
            else:
                print("📥 Ответ не получен")
        except socket.timeout:
            print("📥 Таймаут ожидания ответа")
        
        # Отправка CAN кадра
        can_id = "180"
        can_data = [f"{random.randint(0, 255):02X}" for _ in range(8)]
        can_data_str = ",".join(can_data)
        can_frame = f"~T{test_imei},{can_id},{can_data_str}~"
        
        print(f"📤 Отправка CAN кадра: {can_frame}")
        sock.send(can_frame.encode('utf-8'))
        
        time.sleep(1)
        
        # Попытка получить ответ
        try:
            response = sock.recv(1024)
            if response:
                print(f"📥 Получен ответ: {response.decode('utf-8')}")
            else:
                print("📥 Ответ не получен")
        except socket.timeout:
            print("📥 Таймаут ожидания ответа")
        
        print("✓ Тест завершен успешно")
        
    except ConnectionRefusedError:
        print("✗ Ошибка: Сервер не запущен или недоступен")
        print("   Убедитесь, что сервер запущен на порту 5221")
    except Exception as e:
        print(f"✗ Ошибка: {e}")
    finally:
        try:
            sock.close()
            print("✓ Соединение закрыто")
        except:
            pass


def test_multiple_connections():
    """Тест множественных подключений."""
    print("\n🔍 Тест множественных подключений")
    print("=" * 40)
    
    connections = []
    
    try:
        # Создание нескольких подключений
        for i in range(3):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', 5221))
            connections.append(sock)
            print(f"✓ Подключение {i+1} установлено")
        
        print(f"✓ Всего подключений: {len(connections)}")
        
        # Отправка данных от каждого подключения
        for i, sock in enumerate(connections):
            test_imei = f"12345678901234{i}"
            timestamp = int(time.time())
            lat = 55.7558 + random.uniform(-0.01, 0.01)
            lon = 37.6176 + random.uniform(-0.01, 0.01)
            speed = random.uniform(0, 60)
            satellites = random.randint(4, 12)
            hdop = round(random.uniform(1.0, 3.0), 1)
            
            gps_frame = f"~A{test_imei},{timestamp},{lat},{lon},{speed},90.0,{satellites},{hdop}~"
            
            print(f"📤 Отправка от подключения {i+1}: {gps_frame}")
            sock.send(gps_frame.encode('utf-8'))
            
            time.sleep(0.5)
        
        print("✓ Все данные отправлены")
        
    except Exception as e:
        print(f"✗ Ошибка: {e}")
    finally:
        # Закрытие всех подключений
        for i, sock in enumerate(connections):
            try:
                sock.close()
                print(f"✓ Подключение {i+1} закрыто")
            except:
                pass


def main():
    """Главная функция."""
    print("🚀 Тестирование Navtelecom сервера")
    print("=" * 50)
    
    # Тест базового подключения
    test_server_connection()
    
    # Тест множественных подключений
    test_multiple_connections()
    
    print("\n📋 Инструкции:")
    print("1. Если тесты прошли успешно, сервер работает корректно")
    print("2. Для мониторинга данных запустите: python simple_web_monitor.py")
    print("3. Откройте браузер и перейдите на http://localhost:8080")
    print("4. Для остановки сервера нажмите Ctrl+C в окне сервера")


if __name__ == "__main__":
    main()

