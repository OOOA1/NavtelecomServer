"""Модуль для парсинга протокола Navtelecom."""
import re
import struct
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


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
    
    def parse_frame(self, data: str) -> Optional[Dict[str, Any]]:
        """Парсинг кадра протокола."""
        try:
            # Удаляем лишние символы
            data = data.strip()
            
            # Ищем кадры в данных
            frames = self.frame_pattern.findall(data)
            if not frames:
                logger.warning(f"Не найдено кадров в данных: {data}")
                return None
            
            results = []
            for frame_type, frame_data in frames:
                parsed = self._parse_frame_by_type(frame_type, frame_data)
                if parsed:
                    parsed['frame_type'] = frame_type
                    parsed['raw_data'] = f"~{frame_type}{frame_data}~"
                    results.append(parsed)
            
            return results[0] if len(results) == 1 else results
            
        except Exception as e:
            logger.error(f"Ошибка парсинга кадра: {e}, данные: {data}")
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
    
    def generate_ack_response(self, frame_type: str, imei: str) -> str:
        """Генерация ACK ответа."""
        # Простой ACK ответ
        return f"~{frame_type}ACK,{imei}~"
    
    def generate_keepalive_response(self, imei: str) -> str:
        """Генерация keepalive ответа."""
        return f"~KEEPALIVE,{imei}~"


# Глобальный экземпляр парсера
protocol = NavtelecomProtocol()

