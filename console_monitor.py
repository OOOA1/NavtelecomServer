"""Консольный монитор для отображения данных сервера."""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from test_server_simple import server


class ConsoleMonitor:
    """Консольный монитор сервера."""
    
    def __init__(self):
        """Инициализация монитора."""
        self.running = True
    
    def clear_screen(self):
        """Очистка экрана."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self):
        """Вывод заголовка."""
        print("=" * 80)
        print("🚀 NAVTELECOM SERVER - КОНСОЛЬНЫЙ МОНИТОР")
        print("=" * 80)
        print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    
    def print_server_stats(self):
        """Вывод статистики сервера."""
        print("📊 СТАТИСТИКА СЕРВЕРА")
        print("-" * 40)
        
        stats = server.stats
        all_devices = server.get_all_devices()
        
        print(f"🔗 Всего соединений: {stats['connections_total']}")
        print(f"📡 Обработано кадров: {stats['frames_processed']}")
        print(f"❌ Ошибок: {stats['errors']}")
        print(f"📱 Активных устройств: {len(all_devices)}")
        print()
    
    def print_devices(self):
        """Вывод информации об устройствах."""
        all_devices = server.get_all_devices()
        
        if not all_devices:
            print("📱 УСТРОЙСТВА")
            print("-" * 40)
            print("❌ Нет данных об устройствах")
            print()
            return
        
        print("📱 УСТРОЙСТВА")
        print("-" * 40)
        
        for i, (unique_id, device_data) in enumerate(all_devices.items(), 1):
            print(f"{i}. 📱 {unique_id}")
            print(f"   🕐 Последняя активность: {device_data['last_seen'].strftime('%H:%M:%S')}")
            
            # GPS позиции
            positions = device_data.get('positions', [])
            print(f"   📍 GPS позиций: {len(positions)}")
            
            if positions:
                last_pos = positions[-1]
                print(f"   📍 Последняя позиция:")
                print(f"      🕐 Время: {last_pos['fix_time'].strftime('%H:%M:%S')}")
                print(f"      📍 Координаты: ({last_pos['latitude']:.6f}, {last_pos['longitude']:.6f})")
                print(f"      🚗 Скорость: {last_pos['speed']:.1f} км/ч")
                print(f"      🧭 Курс: {last_pos['course']:.1f}°")
                print(f"      🛰️ Спутники: {last_pos['satellites']}")
            
            # CAN данные
            can_data = device_data.get('can_data', [])
            print(f"   🔧 CAN записей: {len(can_data)}")
            
            if can_data:
                print(f"   🔧 Последние CAN данные:")
                for can in can_data[-2:]:  # Последние 2
                    print(f"      CAN ID: {can['can_id']}, Данные: {can['can_data_hex']}")
            
            # События
            events = device_data.get('events', [])
            print(f"   📢 Событий: {len(events)}")
            
            if events:
                print(f"   📢 Последние события:")
                for event in events[-2:]:  # Последние 2
                    print(f"      Тип: {event['event_type']}, Данные: {event['event_data']}")
            
            print()
    
    def print_recent_activity(self):
        """Вывод недавней активности."""
        print("🔄 НЕДАВНЯЯ АКТИВНОСТЬ")
        print("-" * 40)
        
        all_devices = server.get_all_devices()
        current_time = datetime.now()
        
        recent_activity = []
        
        for unique_id, device_data in all_devices.items():
            last_seen = device_data['last_seen']
            time_diff = (current_time - last_seen.replace(tzinfo=None)).seconds
            
            if time_diff < 300:  # Последние 5 минут
                recent_activity.append({
                    'device': unique_id,
                    'last_seen': last_seen,
                    'time_diff': time_diff,
                    'positions': len(device_data.get('positions', [])),
                    'can_data': len(device_data.get('can_data', [])),
                    'events': len(device_data.get('events', []))
                })
        
        if recent_activity:
            # Сортировка по времени последней активности
            recent_activity.sort(key=lambda x: x['last_seen'], reverse=True)
            
            for activity in recent_activity[:5]:  # Топ 5
                time_str = f"{activity['time_diff']}с назад"
                print(f"📱 {activity['device']} - {time_str}")
                print(f"   📍 {activity['positions']} позиций, 🔧 {activity['can_data']} CAN, 📢 {activity['events']} событий")
        else:
            print("❌ Нет активности за последние 5 минут")
        
        print()
    
    def print_instructions(self):
        """Вывод инструкций."""
        print("💡 УПРАВЛЕНИЕ")
        print("-" * 40)
        print("🔄 Автообновление каждые 5 секунд")
        print("⏹️  Для остановки нажмите Ctrl+C")
        print("📊 Данные обновляются в реальном времени")
        print()
    
    def display_data(self):
        """Отображение всех данных."""
        self.clear_screen()
        self.print_header()
        self.print_server_stats()
        self.print_devices()
        self.print_recent_activity()
        self.print_instructions()
    
    async def run_monitor(self, interval=5):
        """Запуск монитора."""
        print("🚀 Запуск консольного монитора...")
        print("⏳ Ожидание данных от сервера...")
        
        try:
            while self.running:
                self.display_data()
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Мониторинг остановлен пользователем")
            self.running = False
        except Exception as e:
            print(f"\n❌ Ошибка мониторинга: {e}")
            self.running = False


async def main():
    """Главная функция."""
    monitor = ConsoleMonitor()
    await monitor.run_monitor(interval=3)  # Обновление каждые 3 секунды


if __name__ == "__main__":
    asyncio.run(main())

