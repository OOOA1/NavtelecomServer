"""Упрощенный тестовый сервер без PostgreSQL."""
import asyncio
import socket
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UniversalNavtelecomServer:
    """Универсальный сервер с поддержкой Navtelecom и FLEX протоколов."""
    
    def __init__(self, host='0.0.0.0', port=5221):
        """Инициализация сервера."""
        self.host = host
        self.port = port
        self.server = None
        self.connections = {}
        self.device_data = {}  # Хранение данных в памяти
        self.stats = {
            'connections_total': 0,
            'frames_processed': 0,
            'errors': 0,
            'navtelecom_frames': 0,
            'flex_frames': 0
        }
        
        # Регулярные выражения для парсинга
        self.imei_pattern = re.compile(r'(\d{15})')
        self.frame_pattern = re.compile(r'~([ATXE])([^~]*)~')
        
        # FLEX протокол - бинарный формат
        self.flex_header_pattern = re.compile(rb'\x02\x02\x02\x02')  # FLEX заголовок
    
    async def start(self):
        """Запуск сервера."""
        try:
            self.server = await asyncio.start_server(
                self.handle_client,
                self.host,
                self.port
            )
            
            logger.info(f"Сервер запущен на {self.host}:{self.port}")
            
            # Запуск мониторинга
            asyncio.create_task(self.monitor_stats())
            
            async with self.server:
                await self.server.serve_forever()
                
        except Exception as e:
            logger.error(f"Ошибка запуска сервера: {e}")
            raise
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Обработка клиентского соединения."""
        client_addr = writer.get_extra_info('peername')
        connection_id = f"{client_addr[0]}:{client_addr[1]}"
        
        self.connections[connection_id] = reader
        self.stats['connections_total'] += 1
        
        logger.info("connection_established", client=connection_id)

        # Пробуем отправить краткое приветствие сразу после подключения
        try:
            writer.write(b'OK\n')
            await writer.drain()
        except Exception as e:
            logger.warning(f"Не удалось отправить приветствие: {e}")

        try:
            buffer = ""
            
            while True:
                try:
                    data = await asyncio.wait_for(reader.read(1024), timeout=120)
                    
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Обработка полных сообщений
                    while '\n' in buffer or '~' in buffer:
                        if '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                        else:
                            end_pos = buffer.find('~', 1)
                            if end_pos == -1:
                                break
                            line = buffer[:end_pos + 1]
                            buffer = buffer[end_pos + 1:]
                        
                        if line.strip():
                            await self.process_message(line.strip(), writer, connection_id)
                        else:
                            logger.debug("Пропущена пустая строка")
                
                except asyncio.TimeoutError:
                    # Ничего не шлем, просто продолжаем ждать данные
                    continue
                
                except Exception as e:
                    logger.exception(f"Ошибка чтения данных: {e}")
                    self.stats['errors'] += 1
                    break
        
        except Exception as e:
            logger.exception(f"Ошибка обработки клиента: {e}")
            self.stats['errors'] += 1
        
        finally:
            try:
                if connection_id in self.connections:
                    del self.connections[connection_id]
                
                writer.close()
                await writer.wait_closed()
                logger.info("connection_closed", client=connection_id)
            except Exception as cleanup_error:
                logger.error(f"Ошибка при закрытии соединения: {cleanup_error}")
    
    async def process_message(self, message: str, writer: asyncio.StreamWriter, connection_id: str):
        """Обработка сообщения от устройства."""
        try:
            # Проверка на пустое сообщение
            if not message or not message.strip():
                logger.debug("Пропущено пустое сообщение")
                return
            
            logger.info("message_received", message=message)
            
            # Некоторые устройства Navtelecom сначала посылают приветствие вида
            # "@NTC ... FG*>S:<IMEI>" и ожидают ответ "OK".
            # Отвечаем немедленно, чтобы устройство не разрывало соединение.
            if "@NTC" in message:
                try:
                    writer.write(b"OK\r\n")
                    await writer.drain()
                    logger.info("greeting_response_sent", response="OK")
                except Exception as e:
                    logger.warning(f"Не удалось отправить OK на приветствие: {e}")

            # Определяем тип протокола и парсим
            parsed_data = None
            
            # Сначала пробуем Navtelecom протокол
            if '~' in message:
                parsed_data = self.parse_navtelecom_frame(message)
                if parsed_data:
                    self.stats['navtelecom_frames'] += 1
                    logger.info("navtelecom_frame_processed")
            
            # Если не получилось, пробуем FLEX протокол
            if not parsed_data:
                parsed_data = self.parse_flex_frame(message)
                if parsed_data:
                    self.stats['flex_frames'] += 1
                    logger.info("flex_frame_processed")
            
            if not parsed_data:
                logger.warning(f"Не удалось распарсить кадр: {message}")
                return
            
            # Обработка кадра
            await self.process_frame(parsed_data, writer, connection_id)
            self.stats['frames_processed'] += 1
            
        except Exception as e:
            logger.exception(f"Ошибка обработки сообщения: {e}")
            self.stats['errors'] += 1
    
    def parse_navtelecom_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг Navtelecom кадра."""
        try:
            data = data.strip()
            frames = self.frame_pattern.findall(data)
            
            if not frames:
                return None
            
            frame_type, frame_data = frames[0]
            parsed = self._parse_frame_by_type(frame_type, frame_data)
            
            if parsed:
                parsed['frame_type'] = frame_type
                parsed['protocol'] = 'navtelecom'
                parsed['raw_data'] = f"~{frame_type}{frame_data}~"
                return parsed
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка парсинга Navtelecom кадра: {e}")
            return None
    
    def parse_flex_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг FLEX кадра."""
        try:
            # FLEX протокол - попробуем извлечь IMEI и данные
            data = data.strip()
            
            # Ищем IMEI в данных
            imei_match = self.imei_pattern.search(data)
            if not imei_match:
                return None
            
            imei = imei_match.group(1)
            
            # Пытаемся извлечь координаты (примерный формат)
            # FLEX может содержать GPS данные в другом формате
            coords_match = re.search(r'(\d+\.\d+),(\d+\.\d+)', data)
            
            if coords_match:
                lat = float(coords_match.group(1))
                lon = float(coords_match.group(2))
                
                return {
                    'imei': imei,
                    'unique_id': imei,
                    'latitude': lat,
                    'longitude': lon,
                    'protocol': 'flex',
                    'data_type': 'gps',
                    'raw_data': data
                }
            
            # Если координат нет, создаем общий кадр
            return {
                'imei': imei,
                'unique_id': imei,
                'protocol': 'flex',
                'data_type': 'unknown',
                'raw_data': data
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга FLEX кадра: {e}")
            return None
    
    def _parse_frame_by_type(self, frame_type: str, frame_data: str) -> Optional[Dict[str, Any]]:
        """Парсинг кадра по типу."""
        if frame_type == 'A':
            return self._parse_A_frame(frame_data)
        elif frame_type == 'T':
            return self._parse_T_frame(frame_data)
        elif frame_type == 'X':
            return self._parse_X_frame(frame_data)
        elif frame_type == 'E':
            return self._parse_E_frame(frame_data)
        else:
            logger.warning(f"Неизвестный тип кадра: {frame_type}")
            return None
    
    def _parse_A_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг GPS кадра (~A)."""
        try:
            parts = data.split(',')
            if len(parts) < 7:
                return None
            
            imei = parts[0]
            timestamp = int(parts[1])
            latitude = float(parts[2])
            longitude = float(parts[3])
            speed = float(parts[4])
            course = float(parts[5])
            satellites = int(parts[6])
            hdop = float(parts[7]) if len(parts) > 7 else None
            
            fix_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            return {
                'imei': imei,
                'unique_id': imei,
                'latitude': latitude,
                'longitude': longitude,
                'speed': speed,
                'course': course,
                'satellites': satellites,
                'hdop': hdop,
                'fix_time': fix_time,
                'data_type': 'gps'
            }
            
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга A-кадра: {e}")
            return None
    
    def _parse_T_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг CAN кадра (~T)."""
        try:
            parts = data.split(',')
            if len(parts) < 3:
                return None
            
            imei = parts[0]
            can_id = parts[1]
            can_data = parts[2:]
            
            can_bytes = []
            for byte_str in can_data:
                try:
                    can_bytes.append(int(byte_str, 16))
                except ValueError:
                    continue
            
            return {
                'imei': imei,
                'unique_id': imei,
                'can_id': can_id,
                'can_data': can_bytes,
                'can_data_hex': ','.join(can_data),
                'data_type': 'can'
            }
            
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга T-кадра: {e}")
            return None
    
    def _parse_X_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг расширенного CAN кадра (~X)."""
        return self._parse_T_frame(data)  # Аналогично T-кадру
    
    def _parse_E_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг события (~E)."""
        try:
            parts = data.split(',')
            if len(parts) < 4:
                return None
            
            imei = parts[0]
            event_type = int(parts[1])
            timestamp = int(parts[2])
            event_data = ','.join(parts[3:])
            
            event_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            return {
                'imei': imei,
                'unique_id': imei,
                'event_type': event_type,
                'event_time': event_time,
                'event_data': event_data,
                'data_type': 'event'
            }
            
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга E-кадра: {e}")
            return None
    
    async def process_frame(self, frame: Dict[str, Any], writer: asyncio.StreamWriter, connection_id: str):
        """Обработка отдельного кадра."""
        try:
            unique_id = frame.get('unique_id')
            if not unique_id:
                return
            
            # Сохранение данных в памяти
            if unique_id not in self.device_data:
                self.device_data[unique_id] = {
                    'positions': [],
                    'can_data': [],
                    'events': [],
                    'flex_data': [],
                    'last_seen': datetime.now(timezone.utc),
                    'protocol': frame.get('protocol', 'unknown')
                }
            
            # Обработка по типу кадра и протоколу
            if frame.get('protocol') == 'flex':
                self.device_data[unique_id]['flex_data'].append(frame)
                self.device_data[unique_id]['last_seen'] = datetime.now(timezone.utc)
                
                if frame.get('data_type') == 'gps':
                    logger.info(f"FLEX GPS позиция сохранена: {unique_id} - ({frame['latitude']:.6f}, {frame['longitude']:.6f})")
                else:
                    logger.info(f"FLEX данные сохранены: {unique_id} - {frame.get('data_type', 'unknown')}")
                
                # Отправка ACK для FLEX (простой ответ)
                ack_response = "OK"
                writer.write(ack_response.encode('utf-8'))
                await writer.drain()
                logger.info("flex_ack_sent", response=ack_response)
                
            else:
                # Обработка Navtelecom кадров
                if frame.get('frame_type') == 'A':
                    self.device_data[unique_id]['positions'].append(frame)
                    self.device_data[unique_id]['last_seen'] = datetime.now(timezone.utc)
                    logger.info(f"GPS позиция сохранена: {unique_id} - ({frame['latitude']:.6f}, {frame['longitude']:.6f})")
                    
                elif frame.get('frame_type') in ['T', 'X']:
                    self.device_data[unique_id]['can_data'].append(frame)
                    logger.info(f"CAN данные сохранены: {unique_id} - CAN ID {frame['can_id']}")
                    
                elif frame.get('frame_type') == 'E':
                    self.device_data[unique_id]['events'].append(frame)
                    logger.info(f"Событие сохранено: {unique_id} - {frame['event_data']}")
                
                # Отправка ACK ответа для Navtelecom
                ack_response = f"~{frame['frame_type']}ACK,{unique_id}~"
                writer.write(ack_response.encode('utf-8'))
                await writer.drain()
                logger.info("navtelecom_ack_sent", response=ack_response)
            
        except Exception as e:
            logger.exception(f"Ошибка обработки кадра: {e}")
            self.stats['errors'] += 1
    
    async def send_keepalive(self, writer: asyncio.StreamWriter):
        """Отправка keepalive сообщения."""
        try:
            keepalive = "~KEEPALIVE~"
            writer.write(keepalive.encode('utf-8'))
            await writer.drain()
        except Exception as e:
            logger.exception(f"Ошибка отправки keepalive: {e}")
    
    async def monitor_stats(self):
        """Мониторинг статистики."""
        while True:
            await asyncio.sleep(60)
            
            active_connections = len(self.connections)
            active_devices = len(self.device_data)
            
            logger.info(f"Статистика: соединений={active_connections}, "
                       f"устройств={active_devices}, "
                       f"кадров={self.stats['frames_processed']}, "
                       f"Navtelecom={self.stats['navtelecom_frames']}, "
                       f"FLEX={self.stats['flex_frames']}, "
                       f"ошибок={self.stats['errors']}")
    
    def get_device_data(self, unique_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных устройства."""
        return self.device_data.get(unique_id)
    
    def get_all_devices(self) -> Dict[str, Any]:
        """Получение всех устройств."""
        return self.device_data


# Глобальный экземпляр сервера
server = UniversalNavtelecomServer()


async def main():
    """Главная функция."""
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Сервер остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())

