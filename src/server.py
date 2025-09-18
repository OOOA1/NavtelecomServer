"""Основной TCP-сервер для приема данных Navtelecom."""
import asyncio
import logging
import structlog
from typing import Dict, Set, Any
from datetime import datetime, timezone
import json
import os
import socket
from logging.handlers import RotatingFileHandler

from .config import config
from .database import db
from .protocol import protocol, extract_frames, extract_ntcb_frames

# Глобальный флаг пассивного режима
RESPOND_ENABLED = False

# Глобальный флаг готовности БД
DB_READY = False

# Константы для переговоров
SERVER_FLEX_STRUCT_VERSION = 0x1E
SERVER_FLEX_DATAMASK = bytes.fromhex("00000000")  # подставь реальную маску и длину


class FrameExtractor:
    """Извлекатель фреймов из потока байтов."""
    
    def __init__(self, max_buffer_size: int = 2 * 1024 * 1024, max_frame_size: int = 1024 * 1024):
        self.buf = bytearray()
        self.max_buffer_size = max_buffer_size  # Максимальный размер буфера (2MB)
        self.max_frame_size = max_frame_size    # Максимальный размер фрейма (1MB)
        self.total_bytes_processed = 0         # Счетчик обработанных байт
    
    def feed(self, chunk: bytes):
        """Добавляет новые данные и возвращает извлеченные фреймы."""
        out = []
        
        # Проверяем на пустые данные
        if not chunk:
            return out  # Пустой chunk - это нормально, просто возвращаем пустой список
        
        # Обновляем счетчик обработанных байт
        self.total_bytes_processed += len(chunk)
        
        # Проверка размера буфера
        if len(self.buf) + len(chunk) > self.max_buffer_size:
            logger.warning("Буфер переполнен, очищаем", 
                          buffer_size=len(self.buf), chunk_size=len(chunk),
                          max_buffer_size=self.max_buffer_size)
            self.buf.clear()
            return out  # Возвращаем пустой список при переполнении
        
        self.buf += chunk

        # Извлекаем ВСЕ фреймы из буфера в цикле
        while True:
            frames_found = 0
            
            # 1) Извлекаем NTCB бинарные кадры (0x7E...0x7E) - приоритет
            ntcb_frames = extract_ntcb_frames(self.buf, self.max_frame_size)
            if ntcb_frames:
                out.extend(ntcb_frames)
                frames_found += len(ntcb_frames)
                logger.debug(f"Извлечено NTCB кадров: {len(ntcb_frames)}")
            
            # 2) Извлекаем ASCII фреймы с маркерами ~...~
            ascii_frames = extract_frames(self.buf, self.max_frame_size)
            if ascii_frames:
                out.extend(ascii_frames)
                frames_found += len(ascii_frames)
                logger.debug(f"Извлечено ASCII фреймов: {len(ascii_frames)}")
            
            # Если не найдено фреймов - выходим из цикла
            if frames_found == 0:
                break
            
            logger.debug(f"Итерация извлечения: найдено {frames_found} фреймов, буфер: {len(self.buf)} байт")
        
        return out
    
    def get_stats(self):
        """Возвращает статистику экстрактора."""
        return {
            'buffer_size': len(self.buf),
            'max_buffer_size': self.max_buffer_size,
            'total_bytes_processed': self.total_bytes_processed,
            'buffer_usage_percent': (len(self.buf) / self.max_buffer_size) * 100
        }


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
log_file = config.logging.get('file', 'logs/server.log')
max_file_size = config.logging.get('max_file_size', 10 * 1024 * 1024)  # 10MB
backup_count = config.logging.get('backup_count', 5)
log_level = config.logging.get('level', 'INFO')

# Создаем директорию для логов
os.makedirs(os.path.dirname(log_file), exist_ok=True)

# Настройка ротирующего файлового хендлера
file_handler = RotatingFileHandler(
    log_file, 
    maxBytes=max_file_size, 
    backupCount=backup_count
)
file_handler.setLevel(getattr(logging, log_level.upper()))

# Настройка форматирования для файла (JSON)
json_formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(json_formatter)

# Настройка консольного хендлера
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, log_level.upper()))

# Настройка форматирования для консоли (человекочитаемый)
console_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
console_handler.setFormatter(console_formatter)

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

# Добавляем хендлеры к корневому логгеру
root_logger = logging.getLogger()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)
root_logger.setLevel(getattr(logging, log_level.upper()))


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
            'devices_active': 0,
            'buffer_overflows': 0,
            'large_frames_dropped': 0,
            'empty_frames_dropped': 0,
            'garbage_bytes_dropped': 0,
            'multiple_frames_chunks': 0,
            'keepalive_requests': 0,
            'keepalive_responses': 0,
            'total_bytes_processed': 0
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
        
            logger.info("connection_established", client=connection_id)
        
        # Настройка TCP сокета для минимизации задержек
        try:
            sock = writer.get_extra_info('socket')
            if sock:
                # Отключение алгоритма Nagle для минимизации задержек
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # Включение системного TCP keepalive
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                # Настройка параметров keepalive (Linux)
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)    # 30 сек до первого keepalive
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)   # 10 сек между keepalive
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)      # 3 попытки
                except (OSError, AttributeError):
                    # На Windows или старых системах эти опции могут не поддерживаться
                    pass
                
                logger.debug("TCP сокет настроен", client=connection_id)
        except Exception as e:
            logger.warning("Не удалось настроить TCP сокет", client=connection_id, error=str(e))
        
        try:
            # Получаем настройки буфера из конфигурации
            read_buffer_size = config.server.get('read_buffer_size', 8192)
            max_frame_size = config.server.get('max_frame_size', 1048576)
            max_total_buffer = config.server.get('max_total_buffer', 2097152)
            
            # Получаем таймауты из конфигурации
            read_timeout = config.protocol.get('read_timeout', 5)
            idle_timeout = config.protocol.get('idle_timeout', 900)  # 15 минут
            keepalive_interval = config.protocol.get('keepalive_interval', 60)
            
            # Создаем экстрактор с настройками
            extractor = FrameExtractor(max_total_buffer, max_frame_size)
            last_activity = datetime.now()
            last_keepalive_sent = datetime.now()
            
            logger.info("Начало обработки клиента", client=connection_id, 
                       read_timeout=read_timeout, idle_timeout=idle_timeout,
                       read_buffer_size=read_buffer_size, max_frame_size=max_frame_size)
            
            while True:
                try:
                    # Чтение данных с коротким таймаутом
                    data = await asyncio.wait_for(
                        reader.read(read_buffer_size),
                        timeout=read_timeout
                    )
                    
                    if not data:
                        logger.info("connection_closed_by_client", client=connection_id, reason="empty_data")
                        break
                    
                    # Обновляем время последней активности
                    last_activity = datetime.now()
                    
                    # Обработка фреймов из байтов
                    frames = extractor.feed(data)
                    if frames:
                        if len(frames) > 1:
                            self.stats['multiple_frames_chunks'] += 1
                        logger.info("frames_extracted", client=connection_id, count=len(frames), 
                                   chunk_size=len(data), multiple_frames=len(frames) > 1)
                        
                    # Проверяем статистику буфера
                    buffer_stats = extractor.get_stats()
                    self.stats['total_bytes_processed'] += len(data)
                    
                    if buffer_stats['buffer_usage_percent'] > 80:
                        logger.warning("Высокое использование буфера", client=connection_id, **buffer_stats)
                    
                    if buffer_stats['buffer_usage_percent'] > 95:
                        logger.error("КРИТИЧЕСКОЕ использование буфера, разрываем соединение", 
                                    client=connection_id, **buffer_stats)
                        self.stats['buffer_overflows'] += 1
                        break
                    
                    for frame in frames:
                        try:
                            # Проверка на пустой фрейм
                            if not frame or len(frame) == 0:
                                logger.debug("Пропущен пустой фрейм", client=connection_id)
                                self.stats['empty_frames_dropped'] += 1
                                continue
                            
                            # Дополнительная проверка размера фрейма
                            if len(frame) > max_frame_size:
                                logger.warning("Фрейм превышает максимальный размер", 
                                              client=connection_id, frame_size=len(frame), 
                                              max_frame_size=max_frame_size)
                                self.stats['large_frames_dropped'] += 1
                                continue
                            
                            await self.process_message_bytes(frame, writer, connection_id)
                        except Exception as frame_error:
                            logger.exception("Ошибка обработки отдельного фрейма", 
                                            client=connection_id, error=str(frame_error), 
                                            frame_hex=frame.hex())
                            self.stats['errors'] += 1
                            # Продолжаем обработку остальных фреймов
                            continue
                
                except asyncio.TimeoutError:
                    # Таймаут чтения - это нормально, проверяем общую активность
                    current_time = datetime.now()
                    idle_seconds = (current_time - last_activity).total_seconds()
                    
                    # Проверяем общий таймаут простоя
                    if idle_seconds > idle_timeout:
                        logger.warning("Превышен таймаут простоя", client=connection_id, 
                                      idle_seconds=idle_seconds, idle_timeout=idle_timeout)
                        break
                    
                    # Отправляем keepalive если нужно
                    if RESPOND_ENABLED:
                        keepalive_seconds = (current_time - last_keepalive_sent).total_seconds()
                        if keepalive_seconds >= keepalive_interval:
                            try:
                                await self.send_keepalive_fast(writer, connection_id)
                                last_keepalive_sent = current_time
                            except Exception as e:
                                logger.exception("Ошибка отправки keepalive", client=connection_id, error=str(e))
                                break
                    
                    # Продолжаем цикл - таймаут чтения это не критично
                    continue
                
                except Exception as e:
                    logger.exception("КРИТИЧЕСКАЯ ошибка чтения данных", client=connection_id, error=str(e))
                    self.stats['errors'] += 1
                    break
        
        except Exception as e:
            logger.exception("КРИТИЧЕСКАЯ ошибка обработки клиента", client=connection_id, error=str(e))
            self.stats['errors'] += 1
        
        finally:
            # Закрытие соединения
            try:
            if connection_id in self.connections:
                del self.connections[connection_id]
            
            writer.close()
            await writer.wait_closed()
            
                logger.info("connection_closed", client=connection_id)
            except Exception as cleanup_error:
                logger.error("Ошибка при закрытии соединения", client=connection_id, error=str(cleanup_error))
    
    async def process_message_bytes(self, frame: bytes, writer: asyncio.StreamWriter, connection_id: str):
        """Обработка фрейма в байтах."""
        try:
            # Проверка на пустой фрейм
            if not frame or len(frame) == 0:
                logger.debug("Пропущен пустой фрейм в process_message_bytes", client=connection_id)
                return
            
            # Логируем получение фрейма (усеченный hex для INFO)
            frame_hex_truncated = frame.hex()[:64] + "..." if len(frame.hex()) > 64 else frame.hex()
            logger.info("frame_received", client=connection_id, frame_len=len(frame), frame_hex_preview=frame_hex_truncated)
            
            # Полный hex только в DEBUG
            logger.debug("frame_full_hex", client=connection_id, frame_hex=frame.hex())
            
            # ВСЕГДА сохраняем сырой фрейм
            await self.save_raw_frame(frame, connection_id)
            
            # Проверяем на keepalive запросы (приоритетная обработка)
            if protocol.is_keepalive_request(frame):
                self.stats['keepalive_requests'] += 1
                
                if RESPOND_ENABLED:
                    try:
                        # Извлекаем IMEI из keepalive запроса
                        imei = protocol.extract_imei_from_keepalive(frame)
                        if not imei:
                            # Если IMEI не найден, используем дефолтный
                            imei = "UNKNOWN"
                        
                        # Генерируем FLEX 3.0 keepalive ответ
                        response = protocol.generate_keepalive_response(imei)
                        writer.write(response.encode('utf-8'))
                        await asyncio.wait_for(writer.drain(), timeout=0.5)
                        
                        self.stats['keepalive_responses'] += 1
                        logger.info("keepalive_response_sent", client=connection_id, imei=imei, response=response)
                    except asyncio.TimeoutError:
                        logger.warning("Таймаут ответа на keepalive", client=connection_id)
                    except Exception as e:
                        logger.exception("Ошибка ответа на keepalive", client=connection_id, error=str(e))
                else:
                    logger.info("keepalive_request_received_passive", client=connection_id, frame_hex=frame.hex()[:64])
                return
            
            # Проверяем на запрос переговоров *?A
            if b'*?A' in frame and RESPOND_ENABLED:
                resp = build_negotiation_response(frame)
                if resp:
                    writer.write(resp)
                    await writer.drain()
                    resp_hex_truncated = resp.hex()[:64] + "..." if len(resp.hex()) > 64 else resp.hex()
                    logger.info("negotiation_response_sent", client=connection_id, response_hex_preview=resp_hex_truncated)
                    logger.debug("negotiation_response_full_hex", client=connection_id, response_hex=resp.hex())
                return
            
            # Определяем тип фрейма и парсим
            parsed_data = None
            
            # Всегда передаем байты в parse_frame - он сам определит тип
            try:
                parsed_data = protocol.parse_frame(frame)
                if parsed_data:
                    # Логируем тип обработанного фрейма
                    frame_type = parsed_data.get('frame_type', 'UNKNOWN')
                    is_binary = parsed_data.get('is_binary', False)
                    
                    frame_hex_truncated = frame.hex()[:64] + "..." if len(frame.hex()) > 64 else frame.hex()
                    
                    if is_binary:
                        logger.info("binary_frame_processed", client=connection_id, frame_type=frame_type, 
                                   frame_len=len(frame), frame_hex_preview=frame_hex_truncated)
                        logger.debug("binary_frame_full_hex", client=connection_id, frame_hex=frame.hex())
                    else:
                        message = frame.decode('ascii', 'replace')
                        logger.info("ascii_frame_processed", client=connection_id, frame_type=frame_type, 
                                   message=message, frame_len=len(frame))
                    
                    await self.process_parsed_frame(parsed_data, writer, connection_id)
                else:
                    # Не удалось распарсить - сохраняем как неизвестный
                    frame_hex_truncated = frame.hex()[:64] + "..." if len(frame.hex()) > 64 else frame.hex()
                    logger.warning("unparseable_frame", client=connection_id, frame_len=len(frame), 
                                 frame_hex_preview=frame_hex_truncated)
                    logger.debug("unparseable_frame_full_hex", client=connection_id, frame_hex=frame.hex())
                    
                    # Создаем базовую структуру для неизвестного фрейма
                    parsed_data = {
                        'frame_type': 'UNKNOWN',
                        'raw_bytes': frame,
                        'raw_hex': frame.hex(),
                        'is_binary': True,
                        'data_type': 'unknown'
                    }
                    await self.process_parsed_frame(parsed_data, writer, connection_id)
                    
            except Exception as e:
                frame_hex_truncated = frame.hex()[:64] + "..." if len(frame.hex()) > 64 else frame.hex()
                logger.exception("frame_parse_error", client=connection_id, error=str(e), 
                               frame_hex_preview=frame_hex_truncated)
                logger.debug("frame_parse_error_full_hex", client=connection_id, frame_hex=frame.hex())
            
            self.stats['frames_processed'] += 1
            
        except Exception as e:
            logger.exception("КРИТИЧЕСКАЯ ошибка обработки фрейма", client=connection_id, error=str(e), frame_hex=frame.hex())
            self.stats['errors'] += 1
    
    async def process_parsed_frame(self, parsed_data: Dict[str, Any], writer: asyncio.StreamWriter, connection_id: str):
        """Обработка распарсенного фрейма."""
        try:
            frame_type = parsed_data.get('frame_type')
            unique_id = parsed_data.get('unique_id')
            
            if not unique_id:
                logger.warning("Отсутствует unique_id в распарсенном фрейме", client=connection_id, frame_type=frame_type)
                return
            
            # Получение или создание устройства
            device_id = await db.get_or_create_device(unique_id, parsed_data.get('imei')) if DB_READY else None
            
            # Сохранение сырого кадра в БД
            if DB_READY and device_id:
                try:
                    await db.save_raw_frame(
                        device_id, unique_id, frame_type, 
                        parsed_data.get('raw_data', ''), parsed_data
                    )
                except Exception as e:
                    logger.exception("Ошибка сохранения в БД", client=connection_id, error=str(e))
            
            # Проверяем на keepalive в распарсенных данных
            if protocol.is_keepalive_request(parsed_data.get('raw_data', '')):
                self.stats['keepalive_requests'] += 1
                
                if RESPOND_ENABLED:
                    try:
                        # Генерируем keepalive ответ
                        response = protocol.generate_keepalive_response(unique_id)
                        writer.write(response.encode('utf-8'))
                        await asyncio.wait_for(writer.drain(), timeout=0.5)
                        
                        self.stats['keepalive_responses'] += 1
                        logger.info("parsed_keepalive_response_sent", client=connection_id, imei=unique_id, response=response)
                    except Exception as e:
                        logger.exception("Ошибка ответа на распарсенный keepalive", client=connection_id, error=str(e))
                return
            
            # Обработка по типу кадра
            if frame_type == 'A':
                await self.handle_gps_frame(parsed_data, device_id, unique_id)
            elif frame_type in ['T', 'X']:
                await self.handle_can_frame(parsed_data, device_id, unique_id)
            elif frame_type == 'E':
                await self.handle_event_frame(parsed_data, device_id, unique_id)
            elif frame_type in ['B', 'BINARY', 'FLEX']:
                await self.handle_binary_frame(parsed_data, device_id, unique_id)
            elif frame_type == 'UNKNOWN':
                logger.info("unknown_frame_processed", client=connection_id, unique_id=unique_id, 
                           frame_type=frame_type, is_binary=parsed_data.get('is_binary', False))
            
                # Отправка ACK ответа только в активном режиме
            if RESPOND_ENABLED and frame_type in ['A', 'T', 'X', 'E', 'B', 'FLEX']:
                ack_response = protocol.generate_ack_response(frame_type, unique_id)
                writer.write(ack_response.encode('utf-8'))
                await writer.drain()
                
                logger.info("ack_sent", client=connection_id, frame_type=frame_type, imei=unique_id, response=ack_response)
            
        except Exception as e:
            logger.exception("Ошибка обработки распарсенного фрейма", client=connection_id, error=str(e), parsed_data=parsed_data)
            self.stats['errors'] += 1
    
    async def save_raw_frame(self, frame: bytes, connection_id: str):
        """Сохранение сырого фрейма в файл (hex формат)."""
        try:
            # Проверка на пустой фрейм
            if not frame or len(frame) == 0:
                logger.debug("Пропущено сохранение пустого фрейма", client=connection_id)
                return
            
            # ВСЕГДА сохраняем в файл для отладки
            os.makedirs("logs", exist_ok=True)
            
            # Сохраняем с временной меткой в hex формате
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            # Сохраняем в двух форматах: hex и base64
            hex_data = frame.hex()
            base64_data = protocol.bytes_to_base64(frame)
            
            # Hex формат (основной)
            log_entry_hex = "[{}] {}: HEX={}\n".format(timestamp, connection_id, hex_data)
            with open("logs/raw.hex", "ab") as f:
                f.write(log_entry_hex.encode('utf-8'))
            
            # Base64 формат (дополнительный)
            log_entry_b64 = "[{}] {}: B64={}\n".format(timestamp, connection_id, base64_data)
            with open("logs/raw.b64", "ab") as f:
                f.write(log_entry_b64.encode('utf-8'))
            
            logger.debug("Фрейм сохранен в файлы", client=connection_id, frame_len=len(frame), hex_len=len(hex_data))
                    
        except Exception as e:
            logger.exception("КРИТИЧЕСКАЯ ошибка сохранения фрейма", client=connection_id, error=str(e))
    
    async def process_message(self, message: str, writer: asyncio.StreamWriter, connection_id: str):
        """Обработка сообщения от устройства."""
        try:
            # Проверка на пустое сообщение
            if not message or not message.strip():
                logger.debug("Пропущено пустое сообщение", client=connection_id)
                return
            
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
            logger.exception("Ошибка обработки сообщения", client=connection_id, error=str(e), message=message)
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
            logger.exception("Ошибка обработки кадра", error=str(e), frame=frame)
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
            logger.exception("Ошибка обработки GPS кадра", error=str(e), frame=frame)
    
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
            logger.exception("Ошибка обработки CAN кадра", error=str(e), frame=frame)
    
    async def handle_event_frame(self, frame: Dict[str, Any], device_id: int, unique_id: str):
        """Обработка кадра события."""
        try:
            # Сохранение события (можно расширить логику)
            logger.info(
                "event_received",
                device=unique_id,
                event_type=frame.get('event_type'),
                event_data=frame.get('event_data')
            )
            
        except Exception as e:
            logger.exception("Ошибка обработки кадра события", error=str(e), frame=frame)
    
    async def handle_binary_frame(self, frame: Dict[str, Any], device_id: int, unique_id: str):
        """Обработка бинарного кадра."""
        try:
            frame_type = frame.get('frame_type')
            data_type = frame.get('data_type')
            is_binary = frame.get('is_binary', False)
            
            logger.info(
                "binary_frame_processed",
                device=unique_id,
                frame_type=frame_type,
                data_type=data_type,
                is_binary=is_binary,
                binary_data_length=len(frame.get('binary_data', '')) // 2 if frame.get('binary_data') else 0
            )
            
            # Обработка по типу бинарных данных
            if data_type == 'binary_ntcb':
                # NTCB бинарный кадр
                embedded_ascii = frame.get('embedded_ascii')
                if embedded_ascii:
                    logger.info("ntcb_embedded_ascii_found", device=unique_id, ascii_data=embedded_ascii)
            elif data_type == 'binary_flex':
                # FLEX бинарный кадр
                flex_length = frame.get('flex_length')
                logger.info("flex_binary_frame", device=unique_id, flex_length=flex_length)
            elif data_type == 'binary_unknown':
                # Неизвестный бинарный кадр
                logger.info("unknown_binary_frame", device=unique_id)
            
            # Сохранение бинарных данных в БД (если доступна)
            if DB_READY and device_id:
                try:
                    await db.save_raw_frame(
                        device_id, unique_id, frame_type, 
                        frame.get('raw_data', ''), frame
                    )
                except Exception as e:
                    logger.error("Ошибка сохранения бинарного фрейма в БД", device=unique_id, error=str(e))
            
        except Exception as e:
            logger.exception("Ошибка обработки бинарного кадра", error=str(e), frame=frame)
    
    async def send_keepalive_fast(self, writer: asyncio.StreamWriter, connection_id: str):
        """Быстрая отправка keepalive сообщения (< 1 сек)."""
        try:
            # Стандартный формат keepalive для Navtelecom
            keepalive = "~KA~"
            writer.write(keepalive.encode('utf-8'))
            
            # Немедленный drain без ожидания
            await asyncio.wait_for(writer.drain(), timeout=0.5)
            
            logger.info("keepalive_sent", client=connection_id)
        except asyncio.TimeoutError:
            logger.warning("Таймаут отправки keepalive", client=connection_id)
        except Exception as e:
            logger.exception("Ошибка отправки keepalive", client=connection_id, error=str(e))
            raise
    
    async def send_keepalive(self, writer: asyncio.StreamWriter):
        """Отправка keepalive сообщения (отключено в пассивном режиме)."""
        if not RESPOND_ENABLED:
            return
        try:
            keepalive = "~KEEPALIVE~"
            writer.write(keepalive.encode('utf-8'))
            await writer.drain()
        except Exception as e:
            logger.exception("Ошибка отправки keepalive", error=str(e))
    
    async def monitor_connections(self):
        """Мониторинг соединений."""
        while True:
            await asyncio.sleep(60)  # Каждую минуту
            
            active_connections = len(self.connections)
            self.stats['devices_active'] = len(self.device_positions)
            
            logger.info(
                "server_stats",
                active_connections=active_connections,
                total_connections=self.stats['connections_total'],
                frames_processed=self.stats['frames_processed'],
                errors=self.stats['errors'],
                active_devices=self.stats['devices_active'],
                buffer_overflows=self.stats['buffer_overflows'],
                large_frames_dropped=self.stats['large_frames_dropped'],
                empty_frames_dropped=self.stats['empty_frames_dropped'],
                garbage_bytes_dropped=self.stats['garbage_bytes_dropped'],
                multiple_frames_chunks=self.stats['multiple_frames_chunks'],
                keepalive_requests=self.stats['keepalive_requests'],
                keepalive_responses=self.stats['keepalive_responses'],
                total_bytes_processed=self.stats['total_bytes_processed']
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

