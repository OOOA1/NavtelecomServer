"""Быстрый просмотр данных сервера."""
import json
import sys
from datetime import datetime
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from test_server_simple import server


def show_server_data():
    """Показать данные сервера."""
    print("🚀 NAVTELECOM SERVER - ДАННЫЕ")
    print("=" * 50)
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Статистика сервера
    stats = server.stats
    all_devices = server.get_all_devices()
    
    print("📊 СТАТИСТИКА:")
    print(f"   🔗 Соединений: {stats['connections_total']}")
    print(f"   📡 Кадров: {stats['frames_processed']}")
    print(f"   ❌ Ошибок: {stats['errors']}")
    print(f"   📱 Устройств: {len(all_devices)}")
    print()
    
    if not all_devices:
        print("❌ Нет данных об устройствах")
        return
    
    # Данные устройств
    print("📱 УСТРОЙСТВА:")
    print("-" * 30)
    
    for i, (unique_id, device_data) in enumerate(all_devices.items(), 1):
        print(f"{i}. 📱 {unique_id}")
        print(f"   🕐 Активность: {device_data['last_seen'].strftime('%H:%M:%S')}")
        
        # GPS позиции
        positions = device_data.get('positions', [])
        print(f"   📍 GPS: {len(positions)} позиций")
        
        if positions:
            last_pos = positions[-1]
            print(f"   📍 Последняя: ({last_pos['latitude']:.6f}, {last_pos['longitude']:.6f})")
            print(f"   🚗 Скорость: {last_pos['speed']:.1f} км/ч")
        
        # CAN данные
        can_data = device_data.get('can_data', [])
        print(f"   🔧 CAN: {len(can_data)} записей")
        
        if can_data:
            last_can = can_data[-1]
            print(f"   🔧 Последний CAN ID: {last_can['can_id']}")
        
        # События
        events = device_data.get('events', [])
        print(f"   📢 События: {len(events)}")
        
        print()


def export_data():
    """Экспорт данных в JSON."""
    all_devices = server.get_all_devices()
    
    if not all_devices:
        print("❌ Нет данных для экспорта")
        return
    
    # Подготовка данных для экспорта
    export_data = {}
    for unique_id, device_data in all_devices.items():
        export_data[unique_id] = {
            'last_seen': device_data['last_seen'].isoformat(),
            'positions': [
                {
                    **pos,
                    'fix_time': pos['fix_time'].isoformat()
                }
                for pos in device_data.get('positions', [])
            ],
            'can_data': device_data.get('can_data', []),
            'events': [
                {
                    **event,
                    'event_time': event['event_time'].isoformat()
                }
                for event in device_data.get('events', [])
            ]
        }
    
    # Сохранение в файл
    filename = f"server_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Данные экспортированы в {filename}")


def main():
    """Главная функция."""
    try:
        show_server_data()
        
        # Спрашиваем об экспорте
        if server.get_all_devices():
            print("💾 Экспортировать данные в JSON? (y/n): ", end="")
            try:
                choice = input().lower().strip()
                if choice in ['y', 'yes', 'да', 'д']:
                    export_data()
            except KeyboardInterrupt:
                print("\n👋 До свидания!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    main()

