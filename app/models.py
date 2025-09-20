"""Database models and operations."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from app.db import AsyncSessionLocal


async def save_raw_frame(
    payload: bytes, 
    remote_ip: str, 
    remote_port: int, 
    device_hint: Optional[str] = None
) -> int:
    """Save raw frame to database."""
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO raw_frames (payload, remote_ip, remote_port, device_hint, transport)
            VALUES (:payload, :remote_ip, :remote_port, :device_hint, 'tcp')
            RETURNING id
        """)
        result = await session.execute(query, {
            "payload": payload,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "device_hint": device_hint
        })
        await session.commit()
        return result.scalar_one()


async def save_telemetry(
    raw_id: int,
    device_id: str,
    device_time: Optional[datetime] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    speed: Optional[float] = None,
    course: Optional[float] = None,
    ignition: Optional[bool] = None,
    fuel_level: Optional[float] = None,
    engine_hours: Optional[float] = None,
    temperature: Optional[float] = None
) -> int:
    """Save telemetry data to database."""
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO telemetry_flat 
            (raw_id, device_id, device_time, lat, lon, speed, course, 
             ignition, fuel_level, engine_hours, temperature)
            VALUES (:raw_id, :device_id, :device_time, :lat, :lon, :speed, :course,
                    :ignition, :fuel_level, :engine_hours, :temperature)
            RETURNING id
        """)
        result = await session.execute(query, {
            "raw_id": raw_id,
            "device_id": device_id,
            "device_time": device_time,
            "lat": lat,
            "lon": lon,
            "speed": speed,
            "course": course,
            "ignition": ignition,
            "fuel_level": fuel_level,
            "engine_hours": engine_hours,
            "temperature": temperature
        })
        await session.commit()
        return result.scalar_one()


async def save_decode_error(
    raw_id: int, 
    stage: str, 
    message: str
) -> int:
    """Save decode error to database."""
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO decode_errors (raw_id, stage, message)
            VALUES (:raw_id, :stage, :message)
            RETURNING id
        """)
        result = await session.execute(query, {
            "raw_id": raw_id,
            "stage": stage,
            "message": message
        })
        await session.commit()
        return result.scalar_one()


async def get_telemetry_by_device(
    device_id: str,
    limit: int = 100,
    offset: int = 0
) -> list:
    """Get telemetry data by device ID."""
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT * FROM telemetry_flat 
            WHERE device_id = :device_id 
            ORDER BY device_time DESC 
            LIMIT :limit OFFSET :offset
        """)
        result = await session.execute(query, {
            "device_id": device_id,
            "limit": limit,
            "offset": offset
        })
        return [dict(row) for row in result]


async def get_raw_frames(
    limit: int = 100,
    offset: int = 0
) -> list:
    """Get raw frames from database."""
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT * FROM raw_frames 
            ORDER BY received_at DESC 
            LIMIT :limit OFFSET :offset
        """)
        result = await session.execute(query, {
            "limit": limit,
            "offset": offset
        })
        return [dict(row) for row in result]


async def save_can_raw_frame(
    device_id: str,
    can_id: int,
    payload: bytes,
    dlc: int,
    is_extended: bool,
    dev_time: datetime = None,
    can_channel: int = 0,
    rssi: int = None,
    seq: int = None,
    src_ip: str = None,
    raw_id: int = None
) -> int:
    """Save raw CAN frame to database."""
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO can_raw 
            (device_id, can_id, payload_hex, dlc, is_extended, dev_time, 
             can_channel, rssi, seq, src_ip, raw_id)
            VALUES (:device_id, :can_id, :payload, :dlc, :is_extended, :dev_time,
                    :can_channel, :rssi, :seq, :src_ip, :raw_id)
            RETURNING id
        """)
        result = await session.execute(query, {
            "device_id": device_id,
            "can_id": can_id,
            "payload": payload,
            "dlc": dlc,
            "is_extended": is_extended,
            "dev_time": dev_time,
            "can_channel": can_channel,
            "rssi": rssi,
            "seq": seq,
            "src_ip": src_ip,
            "raw_id": raw_id
        })
        await session.commit()
        return result.scalar_one()


async def save_can_signal(
    device_id: str,
    signal_time: datetime,
    name: str,
    value_num: float = None,
    value_text: str = None,
    unit: str = None,
    src_addr: int = None,
    pgn: int = None,
    spn: int = None,
    mode: int = None,
    pid: int = None,
    dict_version: str = None,
    raw_id: int = None
) -> int:
    """Save decoded CAN signal to database."""
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO can_signals 
            (device_id, signal_time, name, value_num, value_text, unit,
             src_addr, pgn, spn, mode, pid, dict_version, raw_id)
            VALUES (:device_id, :signal_time, :name, :value_num, :value_text, :unit,
                    :src_addr, :pgn, :spn, :mode, :pid, :dict_version, :raw_id)
            RETURNING id
        """)
        result = await session.execute(query, {
            "device_id": device_id,
            "signal_time": signal_time,
            "name": name,
            "value_num": value_num,
            "value_text": value_text,
            "unit": unit,
            "src_addr": src_addr,
            "pgn": pgn,
            "spn": spn,
            "mode": mode,
            "pid": pid,
            "dict_version": dict_version,
            "raw_id": raw_id
        })
        await session.commit()
        return result.scalar_one()


async def get_can_raw_frames(
    device_id: str = None,
    can_id: int = None,
    limit: int = 100,
    offset: int = 0
) -> list:
    """Get raw CAN frames from database."""
    async with AsyncSessionLocal() as session:
        where_clause = "WHERE 1=1"
        params = {"limit": limit, "offset": offset}
        
        if device_id:
            where_clause += " AND device_id = :device_id"
            params["device_id"] = device_id
        
        if can_id:
            where_clause += " AND can_id = :can_id"
            params["can_id"] = can_id
        
        query = text(f"""
            SELECT * FROM can_raw 
            {where_clause}
            ORDER BY recv_time DESC 
            LIMIT :limit OFFSET :offset
        """)
        result = await session.execute(query, params)
        return [dict(row) for row in result]


async def get_can_signals(
    device_id: str = None,
    pgn: int = None,
    spn: int = None,
    mode: int = None,
    pid: int = None,
    limit: int = 100,
    offset: int = 0
) -> list:
    """Get decoded CAN signals from database."""
    async with AsyncSessionLocal() as session:
        where_clause = "WHERE 1=1"
        params = {"limit": limit, "offset": offset}
        
        if device_id:
            where_clause += " AND device_id = :device_id"
            params["device_id"] = device_id
        
        if pgn:
            where_clause += " AND pgn = :pgn"
            params["pgn"] = pgn
        
        if spn:
            where_clause += " AND spn = :spn"
            params["spn"] = spn
        
        if mode:
            where_clause += " AND mode = :mode"
            params["mode"] = mode
        
        if pid:
            where_clause += " AND pid = :pid"
            params["pid"] = pid
        
        query = text(f"""
            SELECT * FROM can_signals 
            {where_clause}
            ORDER BY signal_time DESC 
            LIMIT :limit OFFSET :offset
        """)
        result = await session.execute(query, params)
        return [dict(row) for row in result]


async def save_raw_frame_batch(batch_data: List[Dict[str, Any]]) -> int:
    """Save multiple raw frames in batch."""
    if not batch_data:
        return 0
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO raw_frames (payload, remote_ip, remote_port, device_hint, transport)
            VALUES (:payload, :remote_ip, :remote_port, :device_hint, 'tcp')
            RETURNING id
        """)
        
        result = await session.execute(query, batch_data)
        await session.commit()
        return result.rowcount


async def save_can_raw_frame_batch(batch_data: List[Dict[str, Any]]) -> int:
    """Save multiple CAN raw frames in batch."""
    if not batch_data:
        return 0
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO can_raw 
            (device_id, can_id, payload_hex, dlc, is_extended, dev_time, 
             can_channel, rssi, seq, src_ip, raw_id)
            VALUES (:device_id, :can_id, :payload, :dlc, :is_extended, :dev_time,
                    :can_channel, :rssi, :seq, :src_ip, :raw_id)
            RETURNING id
        """)
        
        result = await session.execute(query, batch_data)
        await session.commit()
        return result.rowcount


async def save_can_signal_batch(batch_data: List[Dict[str, Any]]) -> int:
    """Save multiple CAN signals in batch."""
    if not batch_data:
        return 0
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO can_signals 
            (device_id, signal_time, name, value_num, value_text, unit,
             src_addr, pgn, spn, mode, pid, dict_version, raw_id)
            VALUES (:device_id, :signal_time, :name, :value_num, :value_text, :unit,
                    :src_addr, :pgn, :spn, :mode, :pid, :dict_version, :raw_id)
            RETURNING id
        """)
        
        result = await session.execute(query, batch_data)
        await session.commit()
        return result.rowcount


async def save_telemetry_batch(batch_data: List[Dict[str, Any]]) -> int:
    """Save multiple telemetry records in batch."""
    if not batch_data:
        return 0
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO telemetry_flat 
            (raw_id, device_id, device_time, lat, lon, speed, course, 
             ignition, fuel_level, engine_hours, temperature)
            VALUES (:raw_id, :device_id, :device_time, :lat, :lon, :speed, :course,
                    :ignition, :fuel_level, :engine_hours, :temperature)
            RETURNING id
        """)
        
        result = await session.execute(query, batch_data)
        await session.commit()
        return result.rowcount
