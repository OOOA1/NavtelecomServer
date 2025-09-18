"""Основной TCP-сервер для приема данных Navtelecom."""
import asyncio
import logging
import structlog
from typing import Dict, Set, Any
from datetime import datetime, timezone
import json
import os

from .config import config
from .database import db
from .protocol import protocol

# Глобальный флаг пассивного режима
RESPOND_ENABLED = False

# Глобальный флаг готовности БД
DB_READY = False

# Константы для переговоров
SERVER_FLEX_STRUCT_VERSION = 0x1E
SERVER_FLEX_DATAMASK = bytes.fromhex("00000000")  # подставь реальную маску и длину


class FrameExtractor:
    """Извлекатель фреймов из потока байтов."""
    
    def __init__(self):
        self.buf = bytearray()
    
    def feed(self, chunk: bytes):
        """Добавляет новые данные и возвращает извлеченные фреймы."""
        out = []
        self.buf += chunk

        # 1) вытащить все 0x7E...0x7E бинарные кадры
        while True:
            s = self.buf.find(0x7E)
            if s < 0:
                break
            e = self.buf.find(0x7E, s+1)
            if e < 0:
                break
            out.append(bytes(self.buf[s:e+1]))
            del self.buf[:e+1]

        # 2) вытащить законченные ASCII-строки (заканчивающиеся \n / \r\n)
        while True:
            nl = self.buf.find(b'\n')
            if nl < 0:
                break
            line = bytes(self.buf[:nl+1]).strip(b"\r\n")
            if line:
                out.append(line)
            del self.buf[:nl+1]
        return out


def build_negotiation_response(request: bytes) -> bytes:
    """Строит ответ на запрос переговоров *?A."""
    # если запрос ASCII
    if request.startswith(b'*?A'):
        return b'*#A' + bytes([SERVER_FLEX_STRUCT_VERSION]) + SERVER_FLEX_DATAMASK + b'\r\n'
    # если *?A внутри 0x7E-кадра, попробуй сохранить "голову" перед *?A (эвристика)
    idx = request.find(b'*?A')
    if idx >= 16:
        head = request[idx-16:idx]
        return head + b'*#A' + bytes([SERVER_FLEX_STRUCT_VERSION]) + SERVER_FLEX_DATAMASK
    return b''

# Настройка структурированного логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class NavtelecomServer:
    """Основной класс TCP-сервера."""
    
    def __init__(self):
        """Инициализация сервера."""
        self.server = None
        self.connections: Dict[str, asyncio.StreamReader] = {}
        self.device_positions: Dict[str, Dict] = {}  # Кэш последних позиций
        self.stats = {
            'connections_total': 0,
            'frames_processed': 0,
            'errors': 0,
            'devices_active': 0
        }
    
    async def start(self):
        """Запуск сервера."""
        global DB_READY
        try:
            # Подключение к базе данных
            try:
                await db.connect()
                DB_READY = True
                logger.info("База данных подключена")
            except Exception as e:
                logger.warning("DB недоступна, работаем без БД", error=str(e))
                DB_READY = False
                # Создаем директорию для логов если БД недоступна
                os.makedirs("logs", exist_ok=True)
            
            # Запуск TCP-сервера
            self.server = await asyncio.start_server(
                self.handle_client,
                config.server['host'],
                config.server['port']
            )
            
            logger.info(
                "Сервер запущен",
                host=config.server['host'],
                port=config.server['port']
            )
            
            # Запуск задач мониторинга
            asyncio.create_task(self.monitor_connections())
            asyncio.create_task(self.cleanup_old_connections())
            
            # Ожидание завершения
            async with self.server:
                await self.server.serve_forever()
                
        except Exception as e:
            logger.error("Ошибка запуска сервера", error=str(e))
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановка сервера."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        await db.disconnect()
        logger.info("Сервер остановлен")
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Обработка клиентского соединения."""
        client_addr = writer.get_extra_info('peername')
        connection_id = f"{client_addr[0]}:{client_addr[1]}"
        
        self.connections[connection_id] = reader
        self.stats['connections_total'] += 1
        
        logger.info("Новое соединение", client=connection_id)
        
        try:
            extractor = FrameExtractor()
            last_activity = datetime.now()
            
            while True:
                # Чтение данных с таймаутом
                try:
                    data = await asyncio.wait_for(
                        reader.read(4096),
                        timeout=config.protocol.get('timeout', 30)
                    )
                    
                    if not data:
                        break
                    
                    last_activity = datetime.now()
                    
                    # Обработка фреймов из байтов
                    for frame in extractor.feed(data):
                        await self.process_message_bytes(frame, writer, connection_id)
                
                except asyncio.TimeoutError:
                    # Проверяем активность соединения
                    if (datetime.now() - last_activity).seconds > config.protocol.get('keepalive_interval', 60):
                        logger.warning("Таймаут соединения", client=connection_id)
                        break
                    
                    # В пассивном режиме не отправляем keepalive
                    if RESPOND_ENABLED:
                        await self.send_keepalive(writer)
                
                except Exception as e:
                    logger.error("Ошибка чтения данных", client=connection_id, error=str(e))
                    self.stats['errors'] += 1
                    break
        
        except Exception as e:
            logger.error("Ошибка обработки клиента", client=connection_id, error=str(e))
            self.stats['errors'] += 1
        
        finally:
            # Закрытие соединения
            if connection_id in self.connections:
                del self.connections[connection_id]
            
            writer.close()
            await writer.wait_closed()
            
            logger.info("Соединение закрыто", client=connection_id)
    
    async def process_message_bytes(self, frame: bytes, writer: asyncio.StreamWriter, connection_id: str):
        """Обработка фрейма в байтах."""
        try:
            logger.debug("Получен фрейм", client=connection_id, frame_hex=frame.hex())
            
            # Проверяем на запрос переговоров *?A
            if b'*?A' in frame and RESPOND_ENABLED:
                resp = build_negotiation_response(frame)
                if resp:
                    writer.write(resp)
                    await writer.drain()
                    logger.info("Отправлен ответ на переговоры", client=connection_id, response_hex=resp.hex())
                return
            
            # Определяем тип фрейма
            if frame.startswith(b'~'):
                # ASCII фрейм
                try:
                    message = frame.decode('ascii', 'ignore')
                    await self.process_message(message, writer, connection_id)
                except Exception as e:
                    logger.error("Ошибка декодирования ASCII", client=connection_id, error=str(e))
            elif frame[0] == 0x7E:
                # Бинарный NTCB фрейм
                logger.info("Получен бинарный NTCB фрейм", client=connection_id, frame_hex=frame.hex())
                
                # Ищем ASCII-врезки внутри бинарного фрейма
                ascii_commands = [b'*?A', b'~A', b'~T']
                for cmd in ascii_commands:
                    if cmd in frame:
                        logger.info(f"Найдена ASCII команда {cmd.decode()} в бинарном фрейме", client=connection_id)
                        # Можно извлечь и обработать ASCII часть
                        break
                
                # Сохраняем сырой фрейм
                await self.save_raw_frame(frame, connection_id)
            else:
                # Неизвестный формат
                logger.warning("Неизвестный формат фрейма", client=connection_id, frame_hex=frame.hex())
                await self.save_raw_frame(frame, connection_id)
            
            self.stats['frames_processed'] += 1
            
        except Exception as e:
            logger.error("Ошибка обработки фрейма", client=connection_id, error=str(e), frame_hex=frame.hex())
            self.stats['errors'] += 1
    
    async def save_raw_frame(self, frame: bytes, connection_id: str):
        """Сохранение сырого фрейма в БД или файл."""
        try:
            if DB_READY:
                # Сохраняем в БД (упрощенная версия)
                logger.debug("Сохранение в БД", client=connection_id)
            else:
                # Сохраняем в файл
                with open("logs/raw.hex", "ab") as f:
                    f.write(frame + b"\n")
                logger.debug("Сохранение в файл", client=connection_id)
        except Exception as e:
            logger.error("Ошибка сохранения фрейма", client=connection_id, error=str(e))
    
    async def process_message(self, message: str, writer: asyncio.StreamWriter, connection_id: str):
        """Обработка сообщения от устройства."""
        try:
            logger.debug("Получено сообщение", client=connection_id, message=message)
            
            # Парсинг кадра
            parsed_data = protocol.parse_frame(message)
            if not parsed_data:
                logger.warning("Не удалось распарсить кадр", client=connection_id, message=message)
                return
            
            # Обработка может вернуть список кадров
            if isinstance(parsed_data, list):
                for frame in parsed_data:
                    await self.process_frame(frame, writer, connection_id)
            else:
                await self.process_frame(parsed_data, writer, connection_id)
            
            self.stats['frames_processed'] += 1
            
        except Exception as e:
            logger.error("Ошибка обработки сообщения", client=connection_id, error=str(e), message=message)
            self.stats['errors'] += 1
    
    async def process_frame(self, frame: Dict[str, Any], writer: asyncio.StreamWriter, connection_id: str):
        """Обработка отдельного кадра."""
        try:
            unique_id = frame.get('unique_id')
            if not unique_id:
                logger.warning("Отсутствует unique_id в кадре", frame=frame)
                return
            
            # Получение или создание устройства
            device_id = await db.get_or_create_device(unique_id, frame.get('imei'))
            
            # Сохранение сырого кадра
            await db.save_raw_frame(
                device_id, unique_id, frame['frame_type'], 
                frame['raw_data'], frame
            )
            
            # Обработка по типу кадра
            if frame['frame_type'] == 'A':
                await self.handle_gps_frame(frame, device_id, unique_id)
            elif frame['frame_type'] in ['T', 'X']:
                await self.handle_can_frame(frame, device_id, unique_id)
            elif frame['frame_type'] == 'E':
                await self.handle_event_frame(frame, device_id, unique_id)
            
            # Отправка ACK ответа только в активном режиме
            if RESPOND_ENABLED:
                ack_response = protocol.generate_ack_response(frame['frame_type'], unique_id)
                writer.write(ack_response.encode('utf-8'))
                await writer.drain()
                
                logger.debug("Отправлен ACK", client=connection_id, response=ack_response)
            
        except Exception as e:
            logger.error("Ошибка обработки кадра", error=str(e), frame=frame)
            self.stats['errors'] += 1
    
    async def handle_gps_frame(self, frame: Dict[str, Any], device_id: int, unique_id: str):
        """Обработка GPS кадра."""
        try:
            # Сохранение позиции
            position_id = await db.save_position(
                device_id=device_id,
                unique_id=unique_id,
                latitude=frame['latitude'],
                longitude=frame['longitude'],
                speed=frame.get('speed'),
                course=frame.get('course'),
                altitude=frame.get('altitude'),
                satellites=frame.get('satellites'),
                hdop=frame.get('hdop'),
                fix_time=frame.get('fix_time'),
                raw_data=frame['raw_data']
            )
            
            # Обновление кэша последних позиций
            self.device_positions[unique_id] = {
                'latitude': frame['latitude'],
                'longitude': frame['longitude'],
                'speed': frame.get('speed'),
                'course': frame.get('course'),
                'fix_time': frame.get('fix_time'),
                'position_id': position_id
            }
            
            logger.info(
                "GPS позиция сохранена",
                device=unique_id,
                lat=frame['latitude'],
                lon=frame['longitude'],
                speed=frame.get('speed')
            )
            
        except Exception as e:
            logger.error("Ошибка обработки GPS кадра", error=str(e), frame=frame)
    
    async def handle_can_frame(self, frame: Dict[str, Any], device_id: int, unique_id: str):
        """Обработка CAN кадра."""
        try:
            # Получение последней позиции для привязки
            last_position = self.device_positions.get(unique_id)
            position_id = last_position.get('position_id') if last_position else None
            
            # Сохранение CAN данных
            can_data = {
                'raw_bytes': frame.get('can_data', []),
                'hex_data': frame.get('can_data_hex', ''),
                'frame_type': frame['frame_type']
            }
            
            await db.save_can_data(
                device_id=device_id,
                unique_id=unique_id,
                can_id=frame['can_id'],
                can_data=can_data,
                position_id=position_id
            )
            
            logger.info(
                "CAN данные сохранены",
                device=unique_id,
                can_id=frame['can_id'],
                position_id=position_id
            )
            
        except Exception as e:
            logger.error("Ошибка обработки CAN кадра", error=str(e), frame=frame)
    
    async def handle_event_frame(self, frame: Dict[str, Any], device_id: int, unique_id: str):
        """Обработка кадра события."""
        try:
            # Сохранение события (можно расширить логику)
            logger.info(
                "Событие получено",
                device=unique_id,
                event_type=frame.get('event_type'),
                event_data=frame.get('event_data')
            )
            
        except Exception as e:
            logger.error("Ошибка обработки кадра события", error=str(e), frame=frame)
    
    async def send_keepalive(self, writer: asyncio.StreamWriter):
        """Отправка keepalive сообщения (отключено в пассивном режиме)."""
        if not RESPOND_ENABLED:
            return
        try:
            keepalive = "~KEEPALIVE~"
            writer.write(keepalive.encode('utf-8'))
            await writer.drain()
        except Exception as e:
            logger.error("Ошибка отправки keepalive", error=str(e))
    
    async def monitor_connections(self):
        """Мониторинг соединений."""
        while True:
            await asyncio.sleep(60)  # Каждую минуту
            
            active_connections = len(self.connections)
            self.stats['devices_active'] = len(self.device_positions)
            
            logger.info(
                "Статистика сервера",
                active_connections=active_connections,
                total_connections=self.stats['connections_total'],
                frames_processed=self.stats['frames_processed'],
                errors=self.stats['errors'],
                active_devices=self.stats['devices_active']
            )
    
    async def cleanup_old_connections(self):
        """Очистка старых соединений."""
        while True:
            await asyncio.sleep(300)  # Каждые 5 минут
            
            # Очистка старых позиций из кэша (старше 1 часа)
            current_time = datetime.now(timezone.utc)
            old_devices = []
            
            for unique_id, position in self.device_positions.items():
                if (current_time - position['fix_time']).seconds > 3600:
                    old_devices.append(unique_id)
            
            for unique_id in old_devices:
                del self.device_positions[unique_id]
            
            if old_devices:
                logger.info("Очищены старые позиции", devices=old_devices)


# Глобальный экземпляр сервера
server = NavtelecomServer()

