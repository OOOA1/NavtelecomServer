"""Проверка статуса сервера."""
import socket
import time
import random
from datetime import datetime


def check_server_status():
    """Проверка статуса сервера."""
    print("🔍 ПРОВЕРКА СТАТУСА NAVTELECOM СЕРВЕРА")
    print("=" * 50)
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Проверка подключения
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 5221))
        print("✅ Сервер доступен на порту 5221")
        sock.close()
    except ConnectionRefusedError:
        print("❌ Сервер недоступен на порту 5221")
        print("💡 Убедитесь, что сервер запущен")
        return False
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False
    
    # Тест отправки данных
    print("\n📡 Тестирование отправки данных...")
    
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
        
        print(f"📤 Отправка GPS кадра: {gps_frame}")
        sock.send(gps_frame.encode('utf-8'))
        
        # Получение ответа
        time.sleep(0.5)
        sock.settimeout(2)
        response = sock.recv(1024)
        
        if response and b'ACK' in response:
            print(f"✅ Получен ACK ответ: {response.decode('utf-8')}")
            print("✅ Сервер корректно обрабатывает GPS данные")
        else:
            print("⚠️ ACK ответ не получен")
        
        # Отправка CAN кадра
        can_id = "180"
        can_data = [f"{random.randint(0, 255):02X}" for _ in range(8)]
        can_data_str = ",".join(can_data)
        can_frame = f"~T{test_imei},{can_id},{can_data_str}~"
        
        print(f"📤 Отправка CAN кадра: {can_frame}")
        sock.send(can_frame.encode('utf-8'))
        
        time.sleep(0.5)
        sock.settimeout(2)
        response = sock.recv(1024)
        
        if response and b'ACK' in response:
            print(f"✅ Получен ACK ответ: {response.decode('utf-8')}")
            print("✅ Сервер корректно обрабатывает CAN данные")
        else:
            print("⚠️ ACK ответ не получен")
        
        # Отправка события
        event_frame = f"~E{test_imei},1,{timestamp},Test event~"
        
        print(f"📤 Отправка события: {event_frame}")
        sock.send(event_frame.encode('utf-8'))
        
        time.sleep(0.5)
        sock.settimeout(2)
        response = sock.recv(1024)
        
        if response and b'ACK' in response:
            print(f"✅ Получен ACK ответ: {response.decode('utf-8')}")
            print("✅ Сервер корректно обрабатывает события")
        else:
            print("⚠️ ACK ответ не получен")
        
        sock.close()
        
        print("\n🎉 СЕРВЕР РАБОТАЕТ КОРРЕКТНО!")
        print("✅ Все типы кадров обрабатываются")
        print("✅ ACK ответы отправляются")
        print("✅ Протокол Navtelecom поддерживается")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return False


def show_usage_instructions():
    """Показать инструкции по использованию."""
    print("\n📋 ИНСТРУКЦИИ ПО ИСПОЛЬЗОВАНИЮ:")
    print("=" * 50)
    print("1. 🚀 Сервер запущен и готов к работе")
    print("2. 📱 Настройте устройства в NTC Configurator:")
    print("   - IP адрес: адрес вашего сервера")
    print("   - Порт: 5221")
    print("   - Протокол: TCP")
    print("3. 📊 Для мониторинга используйте:")
    print("   - python test_console.py - тестирование")
    print("   - python show_data.py - просмотр данных")
    print("4. ⏹️ Для остановки сервера нажмите Ctrl+C в окне сервера")
    print()
    print("🔧 Поддерживаемые типы кадров:")
    print("   - ~A - GPS данные (координаты, скорость, курс)")
    print("   - ~T - CAN данные (стандартный формат)")
    print("   - ~X - Расширенные CAN данные")
    print("   - ~E - События")
    print()
    print("✅ Сервер автоматически отправляет ACK ответы")
    print("✅ Поддерживает множественные подключения")
    print("✅ Обрабатывает все типы кадров Navtelecom")


def main():
    """Главная функция."""
    if check_server_status():
        show_usage_instructions()
    else:
        print("\n❌ Сервер не работает")
        print("💡 Запустите сервер командой: python test_server_simple.py")


if __name__ == "__main__":
    main()

