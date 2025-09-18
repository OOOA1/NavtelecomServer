"""Модуль для работы с базой данных."""
import asyncio
import asyncpg
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from .config import config


class Database:
    """Класс для работы с базой данных."""
    
    def __init__(self):
        """Инициализация подключения к БД."""
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Подключение к базе данных."""
        try:
            self.pool = await asyncpg.create_pool(
                config.get_database_url(),
                min_size=1,
                max_size=config.database.get('pool_size', 10),
                command_timeout=60
            )
            print("Подключение к базе данных установлено")
        except Exception as e:
            print(f"Ошибка подключения к базе данных: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от базы данных."""
        if self.pool:
            await self.pool.close()
            print("Подключение к базе данных закрыто")
    
    async def get_or_create_device(self, unique_id: str, imei: Optional[str] = None) -> int:
        """Получение или создание устройства."""
        async with self.pool.acquire() as conn:
            # Сначала пытаемся найти устройство по unique_id
            device_id = await conn.fetchval(
                "SELECT id FROM devices WHERE unique_id = $1",
                unique_id
            )
            
            if device_id:
                # Обновляем last_seen
                await conn.execute(
                    "UPDATE devices SET last_seen = NOW() WHERE id = $1",
                    device_id
                )
                return device_id
            
            # Создаем новое устройство
            device_id = await conn.fetchval(
                """
                INSERT INTO devices (unique_id, imei, name, last_seen)
                VALUES ($1, $2, $3, NOW())
                RETURNING id
                """,
                unique_id,
                imei,
                f"Device_{unique_id}"
            )
            return device_id
    
    async def save_position(self, device_id: int, unique_id: str, 
                          latitude: float, longitude: float,
                          speed: Optional[float] = None,
                          course: Optional[float] = None,
                          altitude: Optional[float] = None,
                          satellites: Optional[int] = None,
                          hdop: Optional[float] = None,
                          fix_time: datetime = None,
                          raw_data: Optional[str] = None) -> int:
        """Сохранение позиции GPS."""
        if fix_time is None:
            fix_time = datetime.now(timezone.utc)
        
        async with self.pool.acquire() as conn:
            position_id = await conn.fetchval(
                """
                INSERT INTO positions 
                (device_id, unique_id, latitude, longitude, speed, course, 
                 altitude, satellites, hdop, fix_time, raw_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
                """,
                device_id, unique_id, latitude, longitude, speed, course,
                altitude, satellites, hdop, fix_time, raw_data
            )
            return position_id
    
    async def save_raw_frame(self, device_id: int, unique_id: str,
                           frame_type: str, raw_data: str,
                           parsed_data: Optional[Dict[str, Any]] = None) -> int:
        """Сохранение сырого кадра."""
        async with self.pool.acquire() as conn:
            frame_id = await conn.fetchval(
                """
                INSERT INTO raw_frames 
                (device_id, unique_id, frame_type, raw_data, parsed_data)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                device_id, unique_id, frame_type, raw_data,
                json.dumps(parsed_data) if parsed_data else None
            )
            return frame_id
    
    async def save_can_data(self, device_id: int, unique_id: str,
                          can_id: str, can_data: Dict[str, Any],
                          position_id: Optional[int] = None) -> int:
        """Сохранение CAN-данных."""
        async with self.pool.acquire() as conn:
            can_data_id = await conn.fetchval(
                """
                INSERT INTO can_data 
                (device_id, unique_id, can_id, can_data, position_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                device_id, unique_id, can_id, json.dumps(can_data), position_id
            )
            return can_data_id
    
    async def get_last_position(self, unique_id: str) -> Optional[Dict[str, Any]]:
        """Получение последней позиции устройства."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT p.*, d.name as device_name
                FROM positions p
                JOIN devices d ON p.device_id = d.id
                WHERE p.unique_id = $1
                ORDER BY p.fix_time DESC
                LIMIT 1
                """,
                unique_id
            )
            return dict(row) if row else None
    
    async def get_positions(self, unique_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение позиций устройства."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT p.*, d.name as device_name
                FROM positions p
                JOIN devices d ON p.device_id = d.id
                WHERE p.unique_id = $1
                ORDER BY p.fix_time DESC
                LIMIT $2
                """,
                unique_id, limit
            )
            return [dict(row) for row in rows]
    
    async def get_devices(self) -> List[Dict[str, Any]]:
        """Получение списка устройств."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.*, p.latitude, p.longitude, p.fix_time as last_position_time
                FROM devices d
                LEFT JOIN LATERAL (
                    SELECT latitude, longitude, fix_time
                    FROM positions
                    WHERE device_id = d.id
                    ORDER BY fix_time DESC
                    LIMIT 1
                ) p ON true
                WHERE d.is_active = true
                ORDER BY d.last_seen DESC
                """
            )
            return [dict(row) for row in rows]


# Глобальный экземпляр базы данных
db = Database()

