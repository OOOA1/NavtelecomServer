"""Модуль для парсинга протокола Navtelecom."""
import re
import struct
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, Union, List
import logging
import base64

logger = logging.getLogger(__name__)

# Константы для извлечения фреймов
START_MARKER = ord('~')
END_MARKER = ord('~')
NEWLINE_MARKER = ord('\n')


def extract_frames(buf: bytearray, max_frame: int = 65536) -> List[bytes]:
    """Извлечение фреймов из буфера с защитой от мусора."""
    frames = []
    garbage_count = 0
    
    while True:
        # Отрезаем мусор до первого '~'
        start_pos = buf.find(START_MARKER)
        if start_pos == -1:
            # Нет начального маркера - очищаем буфер
            garbage_count += len(buf)
            buf.clear()
            break
        
        if start_pos > 0:
            # Удаляем мусор до первого '~'
            garbage_count += start_pos
            logger.debug(f"Удален мусор до маркера: {buf[:start_pos].hex()}")
            del buf[:start_pos]
        
        # Ищем конечный маркер
        end_pos = buf.find(END_MARKER, 1)
        if end_pos == -1:
            # Нет конечного маркера - ждем догрузки хвоста
            break
        
        # Извлекаем содержимое между ~ ~
        frame = bytes(buf[1:end_pos])
        del buf[:end_pos + 1]
        
        # Проверяем размер фрейма
        if len(frame) <= max_frame:
            frames.append(frame)
            logger.debug(f"Извлечен ASCII фрейм: {frame.hex()[:64]}...")
        else:
            logger.warning(f"ASCII фрейм слишком большой, пропускаем: {len(frame)} байт")
    
    if garbage_count > 0:
        logger.info(f"Удалено ASCII мусорных байт: {garbage_count}")
    
    return frames


# Функция extract_ascii_lines удалена - больше не полагаемся на \n как разделитель


def extract_ntcb_frames(buf: bytearray, max_frame: int = 65536) -> List[bytes]:
    """Извлечение NTCB бинарных кадров (0x7E...0x7E) с защитой от мусора."""
    frames = []
    NTCB_START = 0x7E
    NTCB_END = 0x7E
    garbage_count = 0
    
    while True:
        # Отрезаем мусор до первого 0x7E
        start_pos = buf.find(NTCB_START)
        if start_pos == -1:
            # Нет начального маркера - очищаем буфер
            garbage_count += len(buf)
            buf.clear()
            break
        
        if start_pos > 0:
            # Удаляем мусор до первого 0x7E
            garbage_count += start_pos
            logger.debug(f"Удален мусор до NTCB маркера: {buf[:start_pos].hex()}")
            del buf[:start_pos]
        
        # Ищем конечный маркер 0x7E
        end_pos = buf.find(NTCB_END, 1)
        if end_pos == -1:
            # Нет конечного маркера - ждем догрузки хвоста
            break
        
        # Извлекаем содержимое между 0x7E...0x7E
        frame = bytes(buf[:end_pos + 1])  # Включаем оба маркера
        del buf[:end_pos + 1]
        
        # Проверяем размер фрейма
        if len(frame) <= max_frame:
            frames.append(frame)
            logger.debug(f"Извлечен NTCB кадр: {frame.hex()[:64]}...")
        else:
            logger.warning(f"NTCB кадр слишком большой, пропускаем: {len(frame)} байт")
    
    if garbage_count > 0:
        logger.info(f"Удалено NTCB мусорных байт: {garbage_count}")
    
    return frames


class NavtelecomProtocol:
    """Класс для парсинга протокола Navtelecom."""
    
    def __init__(self):
        """Инициализация парсера."""
        # Регулярные выражения для извлечения данных
        self.imei_pattern = re.compile(r'(\d{15})')
        self.frame_pattern = re.compile(r'~([ATXE])([^~]*)~')
        
    def extract_imei(self, data: str) -> Optional[str]:
        """Извлечение IMEI из данных."""
        match = self.imei_pattern.search(data)
        return match.group(1) if match else None
    
    def parse_frame(self, data: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """Парсинг кадра протокола."""
        try:
            # Определяем тип данных и обрабатываем соответственно
            if isinstance(data, bytes):
                return self._parse_bytes_frame(data)
            else:
                return self._parse_string_frame(data)
            
        except Exception as e:
            logger.error(f"Ошибка парсинга кадра: {e}, данные: {data}")
            return None
    
    def _parse_string_frame(self, data_str: str) -> Optional[Dict[str, Any]]:
        """Парсинг текстового кадра."""
        try:
            # Удаляем лишние символы
            data_str = data_str.strip()
            
            # Ищем кадры в данных
            frames = self.frame_pattern.findall(data_str)
            if not frames:
                logger.warning(f"Не найдено кадров в данных: {data_str}")
                return None
            
            results = []
            for frame_type, frame_data in frames:
                parsed = self._parse_frame_by_type(frame_type, frame_data)
                if parsed:
                    parsed['frame_type'] = frame_type
                    parsed['raw_data'] = f"~{frame_type}{frame_data}~"
                    parsed['raw_bytes'] = data_str.encode('utf-8')
                    parsed['raw_hex'] = data_str.encode('utf-8').hex()
                    parsed['is_binary'] = False
                    results.append(parsed)
            
            return results[0] if len(results) == 1 else results
            
        except Exception as e:
            logger.error(f"Ошибка парсинга текстового кадра: {e}, данные: {data_str}")
            return None
    
    def _parse_bytes_frame(self, data_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Парсинг байтового кадра."""
        try:
            # Сначала пробуем декодировать как текст
            try:
                data_str = data_bytes.decode('utf-8', errors='strict')
                # Если успешно декодировалось, обрабатываем как текст
                return self._parse_string_frame(data_str)
            except UnicodeDecodeError:
                # Не удалось декодировать - это бинарные данные
                return self._parse_binary_frame(data_bytes)
            
        except Exception as e:
            logger.error(f"Ошибка парсинга байтового кадра: {e}, данные: {data_bytes.hex()}")
            return None
    
    def _parse_binary_frame(self, data_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Парсинг бинарного кадра."""
        try:
            # Определяем тип бинарного кадра по первым байтам
            if len(data_bytes) < 2:
                logger.warning("Слишком короткий бинарный кадр")
                return None
            
            # Проверяем на различные бинарные форматы
            if data_bytes[0] == 0x7E:
                # NTCB бинарный кадр
                return self._parse_ntcb_binary_frame(data_bytes)
            elif data_bytes[:4] == b'\x02\x02\x02\x02':
                # FLEX бинарный кадр
                return self._parse_flex_binary_frame(data_bytes)
            else:
                # Неизвестный бинарный формат
                return self._parse_unknown_binary_frame(data_bytes)
            
        except Exception as e:
            logger.error(f"Ошибка парсинга бинарного кадра: {e}, данные: {data_bytes.hex()}")
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
            # Пример формата: ~A123456789012345,1234567890,123.456789,45.123456,180.5,90.0,5,2.5~
            parts = data.split(',')
            if len(parts) < 7:
                logger.warning(f"Недостаточно данных в A-кадре: {data}")
                return None
            
            imei = parts[0]
            timestamp = int(parts[1])
            latitude = float(parts[2])
            longitude = float(parts[3])
            speed = float(parts[4])
            course = float(parts[5])
            satellites = int(parts[6])
            hdop = float(parts[7]) if len(parts) > 7 else None
            
            # Конвертация timestamp (предполагаем Unix timestamp)
            fix_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            return {
                'imei': imei,
                'unique_id': imei,  # Используем IMEI как unique_id
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
            logger.error(f"Ошибка парсинга A-кадра: {e}, данные: {data}")
            return None
    
    def _parse_T_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг CAN кадра (~T)."""
        try:
            # Пример формата: ~T123456789012345,180,01,02,03,04,05,06,07,08~
            parts = data.split(',')
            if len(parts) < 3:
                logger.warning(f"Недостаточно данных в T-кадре: {data}")
                return None
            
            imei = parts[0]
            can_id = parts[1]
            can_data = parts[2:]
            
            # Конвертация hex данных
            can_bytes = []
            for byte_str in can_data:
                try:
                    can_bytes.append(int(byte_str, 16))
                except ValueError:
                    logger.warning(f"Неверный hex байт: {byte_str}")
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
            logger.error(f"Ошибка парсинга T-кадра: {e}, данные: {data}")
            return None
    
    def _parse_X_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг расширенного CAN кадра (~X)."""
        try:
            # Аналогично T-кадру, но с дополнительными полями
            parts = data.split(',')
            if len(parts) < 3:
                logger.warning(f"Недостаточно данных в X-кадре: {data}")
                return None
            
            imei = parts[0]
            can_id = parts[1]
            can_data = parts[2:]
            
            can_bytes = []
            for byte_str in can_data:
                try:
                    can_bytes.append(int(byte_str, 16))
                except ValueError:
                    logger.warning(f"Неверный hex байт: {byte_str}")
                    continue
            
            return {
                'imei': imei,
                'unique_id': imei,
                'can_id': can_id,
                'can_data': can_bytes,
                'can_data_hex': ','.join(can_data),
                'data_type': 'can_extended'
            }
            
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга X-кадра: {e}, данные: {data}")
            return None
    
    def _parse_E_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг события (~E)."""
        try:
            # Пример формата: ~E123456789012345,1,1234567890,Event description~
            parts = data.split(',')
            if len(parts) < 4:
                logger.warning(f"Недостаточно данных в E-кадре: {data}")
                return None
            
            imei = parts[0]
            event_type = int(parts[1])
            timestamp = int(parts[2])
            event_data = ','.join(parts[3:])  # Остальные части как описание события
            
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
            logger.error(f"Ошибка парсинга E-кадра: {e}, данные: {data}")
            return None
    
    def _parse_ntcb_binary_frame(self, frame_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Парсинг NTCB бинарного кадра (0x7E...0x7E)."""
        try:
            if len(frame_bytes) < 3 or frame_bytes[0] != 0x7E or frame_bytes[-1] != 0x7E:
                logger.warning(f"Неверный формат NTCB кадра: {frame_bytes.hex()}")
                return None
            
            # Извлекаем данные между маркерами
            data_bytes = frame_bytes[1:-1]
            
            # Ищем ASCII команды внутри бинарного кадра
            ascii_commands = [b'*?A', b'~A', b'~T', b'~X', b'~E']
            for cmd in ascii_commands:
                if cmd in data_bytes:
                    # Извлекаем ASCII часть
                    cmd_start = data_bytes.find(cmd)
                    cmd_end = data_bytes.find(b'\x00', cmd_start)
                    if cmd_end == -1:
                        cmd_end = len(data_bytes)
                    
                    ascii_part = data_bytes[cmd_start:cmd_end]
                    try:
                        ascii_str = ascii_part.decode('ascii', errors='replace')
                        parsed = self._parse_string_frame(ascii_str)
                        if parsed:
                            parsed['raw_bytes'] = frame_bytes
                            parsed['raw_hex'] = frame_bytes.hex()
                            parsed['is_binary'] = True
                            parsed['binary_data'] = data_bytes.hex()
                            parsed['embedded_ascii'] = ascii_str
                        return parsed
                    except Exception as e:
                        logger.error(f"Ошибка парсинга ASCII части NTCB кадра: {e}")
                        continue
            
            # Если ASCII команды не найдены, сохраняем как бинарные данные
            return {
                'frame_type': 'B',
                'raw_bytes': frame_bytes,
                'raw_hex': frame_bytes.hex(),
                'is_binary': True,
                'binary_data': data_bytes.hex(),
                'data_type': 'binary_ntcb'
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга NTCB кадра: {e}, данные: {frame_bytes.hex()}")
            return None
    
    def _parse_flex_binary_frame(self, frame_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Парсинг FLEX бинарного кадра."""
        try:
            if len(frame_bytes) < 8:
                logger.warning(f"Слишком короткий FLEX кадр: {frame_bytes.hex()}")
                return None
            
            # FLEX заголовок: 0x02 0x02 0x02 0x02
            if frame_bytes[:4] != b'\x02\x02\x02\x02':
                logger.warning(f"Неверный FLEX заголовок: {frame_bytes[:4].hex()}")
                return None
            
            # Извлекаем данные после заголовка
            data_bytes = frame_bytes[4:]
            
            # Парсим FLEX структуру (примерная структура)
            if len(data_bytes) >= 4:
                # Предполагаем что первые 4 байта - длина данных
                data_length = struct.unpack('<I', data_bytes[:4])[0]
                
                if len(data_bytes) >= 4 + data_length:
                    flex_data = data_bytes[4:4+data_length]
                    
                    # Пытаемся извлечь IMEI и другие данные
                    imei = self._extract_imei_from_binary(flex_data)
                    
                    return {
                        'frame_type': 'FLEX',
                        'raw_bytes': frame_bytes,
                        'raw_hex': frame_bytes.hex(),
                        'is_binary': True,
                        'binary_data': flex_data.hex(),
                        'data_type': 'binary_flex',
                        'imei': imei,
                        'unique_id': imei,
                        'flex_length': data_length,
                        'flex_data': flex_data.hex()
                    }
            
            # Если не удалось распарсить структуру
            return {
                'frame_type': 'FLEX',
                'raw_bytes': frame_bytes,
                'raw_hex': frame_bytes.hex(),
                'is_binary': True,
                'binary_data': data_bytes.hex(),
                'data_type': 'binary_flex_raw'
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга FLEX кадра: {e}, данные: {frame_bytes.hex()}")
            return None
    
    def _parse_unknown_binary_frame(self, frame_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Парсинг неизвестного бинарного кадра."""
        try:
            # Пытаемся извлечь IMEI из бинарных данных
            imei = self._extract_imei_from_binary(frame_bytes)
            
            return {
                'frame_type': 'BINARY',
                'raw_bytes': frame_bytes,
                'raw_hex': frame_bytes.hex(),
                'is_binary': True,
                'binary_data': frame_bytes.hex(),
                'data_type': 'binary_unknown',
                'imei': imei,
                'unique_id': imei
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга неизвестного бинарного кадра: {e}, данные: {frame_bytes.hex()}")
            return None
    
    def _extract_imei_from_binary(self, data_bytes: bytes) -> Optional[str]:
        """Извлечение IMEI из бинарных данных."""
        try:
            # Ищем 15-значное число в бинарных данных
            data_str = data_bytes.decode('ascii', errors='ignore')
            imei_match = self.imei_pattern.search(data_str)
            return imei_match.group(1) if imei_match else None
        except Exception:
            return None
    
    def parse_binary_frame(self, frame_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Парсинг бинарного кадра (0x7E...0x7E) - для обратной совместимости."""
        return self._parse_ntcb_binary_frame(frame_bytes)
    
    def is_keepalive_request(self, data: Union[str, bytes]) -> bool:
        """Проверка является ли данные keepalive запросом."""
        try:
            if isinstance(data, bytes):
                data_str = data.decode('ascii', errors='ignore')
            else:
                data_str = data
            
            data_str = data_str.upper().strip()
            
            # Ключевые слова для keepalive
            keepalive_keywords = ['PING', 'KEEP', 'ALIVE', 'KA', 'KEEPALIVE']
            
            # Проверяем наличие ключевых слов
            for keyword in keepalive_keywords:
                if keyword in data_str:
                    return True
            
            # Проверяем короткие кадры (возможно keepalive)
            if len(data_str) <= 10 and any(char in data_str for char in ['~', 'K', 'A']):
                return True
            
            # Проверяем специфичные FLEX форматы
            flex_keepalive_patterns = [
                r'~KA~',
                r'~KEEPALIVE~',
                r'~PING~',
                r'~ALIVE~'
            ]
            
            for pattern in flex_keepalive_patterns:
                if re.search(pattern, data_str):
                    return True
            
            return False
            
        except Exception:
            return False
    
    def extract_imei_from_keepalive(self, data: Union[str, bytes]) -> Optional[str]:
        """Извлечение IMEI из keepalive запроса."""
        try:
            if isinstance(data, bytes):
                data_str = data.decode('ascii', errors='ignore')
            else:
                data_str = data
            
            # Ищем IMEI в данных
            imei_match = self.imei_pattern.search(data_str)
            return imei_match.group(1) if imei_match else None
            
        except Exception:
            return None
    
    def generate_ack_response(self, frame_type: str, imei: str) -> str:
        """Генерация ACK ответа."""
        # Простой ACK ответ
        return f"~{frame_type}ACK,{imei}~"
    
    def generate_keepalive_response(self, imei: str) -> str:
        """Генерация keepalive ответа для FLEX 3.0."""
        # FLEX 3.0 формат keepalive ответа
        return f"~KA,{imei},OK~"
    
    def generate_flex_keepalive_response(self, imei: str) -> str:
        """Генерация FLEX keepalive ответа."""
        # Альтернативный FLEX формат
        return f"~KEEPALIVE,{imei}~"
    
    def bytes_to_hex(self, data: bytes) -> str:
        """Конвертация байтов в hex строку."""
        return data.hex()
    
    def bytes_to_base64(self, data: bytes) -> str:
        """Конвертация байтов в base64 строку."""
        return base64.b64encode(data).decode('ascii')
    
    def hex_to_bytes(self, hex_str: str) -> bytes:
        """Конвертация hex строки в байты."""
        try:
            return bytes.fromhex(hex_str)
        except ValueError as e:
            logger.error(f"Ошибка конвертации hex в байты: {e}")
            return b''


# Глобальный экземпляр парсера
protocol = NavtelecomProtocol()

