"""Navtelecom v6.x protocol parser."""
import struct
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class NavtelParseError(Exception):
    """Navtelecom protocol parsing error."""
    pass


def calculate_crc16(data: bytes) -> int:
    """Calculate CRC16 for Navtelecom protocol."""
    crc = 0xFFFF
    
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    
    return crc


def try_parse_frame(data: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse Navtelecom v6.x frame.
    
    Frame format (simplified):
    - Start byte: 0x7E
    - Length: 2 bytes (little endian)
    - Data: variable length
    - CRC: 2 bytes (little endian)
    - End byte: 0x7E
    """
    if len(data) < 6:  # Minimum frame size
        return None
    
    # Check start and end markers
    if data[0] != 0x7E or data[-1] != 0x7E:
        raise NavtelParseError("Invalid frame markers")
    
    # Extract length
    try:
        length = struct.unpack('<H', data[1:3])[0]
    except struct.error:
        raise NavtelParseError("Invalid length field")
    
    # Check frame size
    if len(data) < length + 6:  # length + start + end + crc
        return None  # Incomplete frame
    
    # Extract data and CRC
    frame_data = data[3:3+length]
    crc_received = struct.unpack('<H', data[3+length:3+length+2])[0]
    
    # Verify CRC
    crc_calculated = calculate_crc16(frame_data)
    if crc_received != crc_calculated:
        raise NavtelParseError(f"CRC mismatch: received {crc_received:04X}, calculated {crc_calculated:04X}")
    
    # Parse frame data
    return parse_frame_data(frame_data)


def parse_frame_data(data: bytes) -> Dict[str, Any]:
    """Parse frame data according to Navtelecom v6.x protocol."""
    if len(data) < 4:
        raise NavtelParseError("Frame data too short")
    
    # Extract device ID (IMEI) - first 8 bytes
    device_id = data[:8].hex()
    
    # Extract timestamp (4 bytes, Unix timestamp)
    timestamp = struct.unpack('<I', data[8:12])[0]
    device_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    
    # Parse data type
    data_type = data[12] if len(data) > 12 else 0
    
    result = {
        "device_id": device_id,
        "device_time": device_time,
        "data_type": data_type,
        "raw_data": data.hex()
    }
    
    # Parse based on data type
    if data_type == 0x01:  # GPS data
        result.update(parse_gps_data(data[13:]))
    elif data_type == 0x02:  # CAN data (legacy)
        result.update(parse_can_data(data[13:]))
    elif data_type == 0x03:  # Event data
        result.update(parse_event_data(data[13:]))
    elif data_type == 0x04:  # Raw CAN data (new)
        result.update(parse_raw_can_data(data[13:]))
    elif data_type == 0x05:  # Extended data
        result.update(parse_extended_data(data[13:]))
    else:
        result["unknown_data"] = data[13:].hex()
    
    return result


def parse_gps_data(data: bytes) -> Dict[str, Any]:
    """Parse GPS data from frame."""
    if len(data) < 20:
        raise NavtelParseError("GPS data too short")
    
    # Parse coordinates (4 bytes each, signed integer, scale 1e7)
    lat_raw = struct.unpack('<i', data[0:4])[0]
    lon_raw = struct.unpack('<i', data[4:8])[0]
    
    latitude = lat_raw / 1e7
    longitude = lon_raw / 1e7
    
    # Parse speed (2 bytes, km/h * 10)
    speed_raw = struct.unpack('<H', data[8:10])[0]
    speed = speed_raw / 10.0
    
    # Parse course (2 bytes, degrees * 10)
    course_raw = struct.unpack('<H', data[10:12])[0]
    course = course_raw / 10.0
    
    # Parse altitude (2 bytes, meters)
    altitude = struct.unpack('<H', data[12:14])[0]
    
    # Parse satellites count
    satellites = data[14] if len(data) > 14 else 0
    
    # Parse ignition status
    ignition = bool(data[15] & 0x01) if len(data) > 15 else None
    
    return {
        "lat": latitude,
        "lon": longitude,
        "speed": speed,
        "course": course,
        "altitude": altitude,
        "satellites": satellites,
        "ignition": ignition
    }


def parse_can_data(data: bytes) -> Dict[str, Any]:
    """Parse CAN data from frame."""
    if len(data) < 4:
        raise NavtelParseError("CAN data too short")
    
    # Parse CAN ID (4 bytes)
    can_id = struct.unpack('<I', data[0:4])[0]
    
    # Parse CAN data (remaining bytes)
    can_data = data[4:].hex()
    
    return {
        "can_id": can_id,
        "can_data": can_data
    }


def parse_event_data(data: bytes) -> Dict[str, Any]:
    """Parse event data from frame."""
    if len(data) < 2:
        raise NavtelParseError("Event data too short")
    
    # Parse event code (2 bytes)
    event_code = struct.unpack('<H', data[0:2])[0]
    
    # Parse event data (remaining bytes)
    event_data = data[2:].hex()
    
    return {
        "event_code": event_code,
        "event_data": event_data
    }


def parse_raw_can_data(data: bytes) -> Dict[str, Any]:
    """Parse raw CAN data from frame."""
    if len(data) < 8:
        raise NavtelParseError("Raw CAN data too short")
    
    can_frames = []
    offset = 0
    
    while offset < len(data):
        if offset + 8 > len(data):
            break
        
        # Parse CAN frame header: [timestamp(4)][can_id(4)][dlc(1)][is_extended(1)]
        timestamp = struct.unpack('<I', data[offset:offset+4])[0]
        can_id = struct.unpack('<I', data[offset+4:offset+8])[0]
        dlc = data[offset+8] if offset+8 < len(data) else 0
        is_extended = bool(data[offset+9]) if offset+9 < len(data) else False
        
        offset += 10
        
        # Parse CAN payload
        if offset + dlc > len(data):
            break
        
        payload = data[offset:offset+dlc]
        offset += dlc
        
        can_frames.append({
            "timestamp": timestamp,
            "can_id": can_id,
            "dlc": dlc,
            "is_extended": is_extended,
            "payload": payload.hex()
        })
    
    return {
        "can_frames": can_frames,
        "frame_count": len(can_frames)
    }


def parse_extended_data(data: bytes) -> Dict[str, Any]:
    """Parse extended data from frame."""
    if len(data) < 4:
        raise NavtelParseError("Extended data too short")
    
    # Parse extended data type (2 bytes)
    ext_type = struct.unpack('<H', data[0:2])[0]
    
    # Parse data length (2 bytes)
    data_length = struct.unpack('<H', data[2:4])[0]
    
    # Parse extended data
    ext_data = data[4:4+data_length].hex() if data_length > 0 else ""
    
    return {
        "extended_type": ext_type,
        "extended_data": ext_data,
        "data_length": data_length
    }


def generate_ack_response(device_id: str, data_type: int, status: int = 0x00) -> bytes:
    """Generate ACK response for Navtelecom protocol."""
    # ACK response format: [ACK_FLAG][STATUS][DEVICE_ID_HASH]
    ack_data = bytearray()
    ack_data.append(0x01)  # ACK flag
    ack_data.append(status)  # Status (0x00 = OK, 0x01 = CRC_ERROR, 0x02 = FORMAT_ERROR)
    
    # Add device ID hash for correlation
    device_hash = hash(device_id) & 0xFFFF
    ack_data.extend(struct.pack('<H', device_hash))
    
    crc = calculate_crc16(ack_data)
    
    # Build response frame
    response = bytearray()
    response.append(0x7E)  # Start marker
    response.extend(struct.pack('<H', len(ack_data)))  # Length
    response.extend(ack_data)  # Data
    response.extend(struct.pack('<H', crc))  # CRC
    response.append(0x7E)  # End marker
    
    return bytes(response)


def generate_nack_response(device_id: str, error_code: int) -> bytes:
    """Generate NACK response for Navtelecom protocol."""
    # NACK response format: [NACK_FLAG][ERROR_CODE][DEVICE_ID_HASH]
    nack_data = bytearray()
    nack_data.append(0x02)  # NACK flag
    nack_data.append(error_code)  # Error code
    
    # Add device ID hash for correlation
    device_hash = hash(device_id) & 0xFFFF
    nack_data.extend(struct.pack('<H', device_hash))
    
    crc = calculate_crc16(nack_data)
    
    # Build response frame
    response = bytearray()
    response.append(0x7E)  # Start marker
    response.extend(struct.pack('<H', len(nack_data)))  # Length
    response.extend(nack_data)  # Data
    response.extend(struct.pack('<H', crc))  # CRC
    response.append(0x7E)  # End marker
    
    return bytes(response)
