"""Тестовый клиент для FLEX протокола."""
import asyncio
import socket
import time
import random


async def test_flex_connection():
    """Тест подключения с FLEX протоколом."""
    try:
        # Подключение к серверу
        reader, writer = await asyncio.open_connection('localhost', 5221)
        print("✅ Подключение к серверу установлено")
        
        # Тестовые FLEX сообщения
        flex_messages = [
            "123456789012345,55.7558,37.6176,30.0,90.0,8,2.0",
            "123456789012345,55.7599,37.6152,32.7,90.0,8,2.2",
            "123456789012345,55.7500,37.6200,25.5,180.0,10,1.8",
            "987654321098765,55.8000,37.7000,45.0,270.0,12,2.5"
        ]
        
        for i, message in enumerate(flex_messages, 1):
            print(f"📤 Отправка FLEX сообщения {i}: {message}")
            
            # Отправка сообщения
            writer.write(message.encode('utf-8'))
            await writer.drain()
            
            # Ожидание ответа
            try:
                response = await asyncio.wait_for(reader.read(1024), timeout=5)
                response_text = response.decode('utf-8', errors='ignore')
                print(f"✅ Получен ответ: {response_text}")
            except asyncio.TimeoutError:
                print("⏰ Таймаут ожидания ответа")
            
            # Пауза между сообщениями
            await asyncio.sleep(2)
        
        # Закрытие соединения
        writer.close()
        await writer.wait_closed()
        print("🔌 Соединение закрыто")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def test_mixed_protocols():
    """Тест смешанных протоколов."""
    try:
        # Подключение к серверу
        reader, writer = await asyncio.open_connection('localhost', 5221)
        print("✅ Подключение к серверу установлено")
        
        # Смешанные сообщения
        messages = [
            # Navtelecom протокол
            "~A123456789012345,1758122293,55.7558,37.6176,30.0,90.0,8,2.0~",
            # FLEX протокол
            "123456789012345,55.7599,37.6152,32.7,90.0,8,2.2",
            # Navtelecom CAN
            "~T123456789012345,180,01,E9,41,B2,35,90,CF,DF~",
            # FLEX с другими данными
            "987654321098765,55.8000,37.7000,45.0,270.0,12,2.5"
        ]
        
        for i, message in enumerate(messages, 1):
            protocol = "Navtelecom" if "~" in message else "FLEX"
            print(f"📤 Отправка {protocol} сообщения {i}: {message}")
            
            # Отправка сообщения
            writer.write(message.encode('utf-8'))
            await writer.drain()
            
            # Ожидание ответа
            try:
                response = await asyncio.wait_for(reader.read(1024), timeout=5)
                response_text = response.decode('utf-8', errors='ignore')
                print(f"✅ Получен ответ: {response_text}")
            except asyncio.TimeoutError:
                print("⏰ Таймаут ожидания ответа")
            
            # Пауза между сообщениями
            await asyncio.sleep(2)
        
        # Закрытие соединения
        writer.close()
        await writer.wait_closed()
        print("🔌 Соединение закрыто")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def main():
    """Главная функция."""
    print("🚀 ТЕСТИРОВАНИЕ УНИВЕРСАЛЬНОГО СЕРВЕРА")
    print("=" * 50)
    
    print("\n🔍 Тест 1: FLEX протокол")
    print("-" * 30)
    await test_flex_connection()
    
    await asyncio.sleep(3)
    
    print("\n🔍 Тест 2: Смешанные протоколы")
    print("-" * 30)
    await test_mixed_protocols()
    
    print("\n🎉 Тестирование завершено!")


if __name__ == "__main__":
    asyncio.run(main())
