"""J1939 Transport Protocol assembly for multi-frame messages."""
import asyncio
import time
import struct
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import structlog

logger = structlog.get_logger()


@dataclass
class TPFrame:
    """Transport Protocol frame."""
    device_id: str
    pgn: int
    src_addr: int
    session_id: int
    sequence: int
    data: bytes
    timestamp: float
    frame_type: str  # 'bam', 'rts', 'cts', 'data', 'end'


@dataclass
class TPSession:
    """Transport Protocol session."""
    device_id: str
    pgn: int
    src_addr: int
    session_id: int
    total_size: int
    received_frames: Dict[int, bytes]
    last_update: float
    frame_type: str


class TPAssembler:
    """J1939 Transport Protocol assembler."""
    
    def __init__(self, timeout_ms: int = 500, max_sessions: int = 1000):
        self.timeout_ms = timeout_ms
        self.max_sessions = max_sessions
        self.sessions: Dict[str, TPSession] = {}
        self.cleanup_interval = 10.0  # seconds
        self.last_cleanup = time.time()
    
    def _make_session_key(self, device_id: str, pgn: int, src_addr: int, session_id: int) -> str:
        """Create unique session key."""
        return f"{device_id}:{pgn}:{src_addr}:{session_id}"
    
    def _is_tp_frame(self, can_id: int) -> bool:
        """Check if CAN ID is a Transport Protocol frame."""
        # J1939 TP frames have specific PGN ranges
        pgn = (can_id >> 8) & 0xFFFF
        return pgn in [0xEC00, 0xEB00, 0xEA00]  # BAM, RTS, CTS
    
    def _extract_tp_info(self, can_id: int, payload: bytes) -> Optional[Tuple[int, int, int, int, str]]:
        """Extract TP information from CAN frame."""
        if len(payload) < 8:
            return None
        
        # Extract PGN, SA, DA from CAN ID
        pgn = (can_id >> 8) & 0xFFFF
        sa = can_id & 0xFF
        
        # Extract TP control byte
        control = payload[0]
        
        if control == 0x20:  # BAM (Broadcast Announce Message)
            total_size = struct.unpack('>H', payload[1:3])[0]
            session_id = payload[3]
            return pgn, sa, 0, session_id, 'bam'
        
        elif control == 0x10:  # RTS (Request to Send)
            total_size = struct.unpack('>H', payload[1:3])[0]
            session_id = payload[3]
            return pgn, sa, 0, session_id, 'rts'
        
        elif control == 0x11:  # CTS (Clear to Send)
            session_id = payload[1]
            return pgn, sa, 0, session_id, 'cts'
        
        elif control & 0xF0 == 0x00:  # Data frame
            sequence = control & 0x0F
            session_id = payload[1]
            return pgn, sa, 0, session_id, 'data'
        
        elif control == 0x13:  # End of Message
            session_id = payload[1]
            return pgn, sa, 0, session_id, 'end'
        
        return None
    
    def process_frame(self, device_id: str, can_id: int, payload: bytes) -> Optional[bytes]:
        """Process TP frame and return assembled data if complete."""
        if not self._is_tp_frame(can_id):
            return None
        
        tp_info = self._extract_tp_info(can_id, payload)
        if not tp_info:
            return None
        
        pgn, src_addr, da, session_id, frame_type = tp_info
        session_key = self._make_session_key(device_id, pgn, src_addr, session_id)
        
        # Cleanup old sessions periodically
        self._cleanup_sessions()
        
        if frame_type == 'bam':
            return self._handle_bam(device_id, pgn, src_addr, session_id, payload, session_key)
        elif frame_type == 'rts':
            return self._handle_rts(device_id, pgn, src_addr, session_id, payload, session_key)
        elif frame_type == 'cts':
            return self._handle_cts(device_id, pgn, src_addr, session_id, payload, session_key)
        elif frame_type == 'data':
            return self._handle_data(device_id, pgn, src_addr, session_id, payload, session_key)
        elif frame_type == 'end':
            return self._handle_end(device_id, pgn, src_addr, session_id, payload, session_key)
        
        return None
    
    def _handle_bam(self, device_id: str, pgn: int, src_addr: int, session_id: int, 
                   payload: bytes, session_key: str) -> Optional[bytes]:
        """Handle BAM (Broadcast Announce Message)."""
        if len(payload) < 8:
            return None
        
        total_size = struct.unpack('>H', payload[1:3])[0]
        data = payload[4:8]  # First data bytes
        
        # Create new session
        session = TPSession(
            device_id=device_id,
            pgn=pgn,
            src_addr=src_addr,
            session_id=session_id,
            total_size=total_size,
            received_frames={0: data},
            last_update=time.time(),
            frame_type='bam'
        )
        
        self.sessions[session_key] = session
        
        logger.debug(
            "bam_received",
            device_id=device_id,
            pgn=pgn,
            total_size=total_size,
            session_id=session_id
        )
        
        # For BAM, we expect all data in the first frame
        if len(data) >= total_size:
            return data[:total_size]
        
        return None
    
    def _handle_rts(self, device_id: str, pgn: int, src_addr: int, session_id: int, 
                   payload: bytes, session_key: str) -> Optional[bytes]:
        """Handle RTS (Request to Send)."""
        if len(payload) < 8:
            return None
        
        total_size = struct.unpack('>H', payload[1:3])[0]
        
        # Create new session
        session = TPSession(
            device_id=device_id,
            pgn=pgn,
            src_addr=src_addr,
            session_id=session_id,
            total_size=total_size,
            received_frames={},
            last_update=time.time(),
            frame_type='rts'
        )
        
        self.sessions[session_key] = session
        
        logger.debug(
            "rts_received",
            device_id=device_id,
            pgn=pgn,
            total_size=total_size,
            session_id=session_id
        )
        
        # TODO: Send CTS response if needed
        return None
    
    def _handle_cts(self, device_id: str, pgn: int, src_addr: int, session_id: int, 
                   payload: bytes, session_key: str) -> Optional[bytes]:
        """Handle CTS (Clear to Send)."""
        if session_key not in self.sessions:
            return None
        
        session = self.sessions[session_key]
        session.last_update = time.time()
        
        logger.debug(
            "cts_received",
            device_id=device_id,
            pgn=pgn,
            session_id=session_id
        )
        
        return None
    
    def _handle_data(self, device_id: str, pgn: int, src_addr: int, session_id: int, 
                    payload: bytes, session_key: str) -> Optional[bytes]:
        """Handle data frame."""
        if session_key not in self.sessions:
            return None
        
        session = self.sessions[session_key]
        session.last_update = time.time()
        
        if len(payload) < 2:
            return None
        
        sequence = payload[0] & 0x0F
        data = payload[2:]  # Skip control byte and session ID
        
        session.received_frames[sequence] = data
        
        logger.debug(
            "tp_data_received",
            device_id=device_id,
            pgn=pgn,
            sequence=sequence,
            data_size=len(data),
            session_id=session_id
        )
        
        # Check if we have all frames
        return self._check_completion(session_key)
    
    def _handle_end(self, device_id: str, pgn: int, src_addr: int, session_id: int, 
                   payload: bytes, session_key: str) -> Optional[bytes]:
        """Handle End of Message."""
        if session_key not in self.sessions:
            return None
        
        session = self.sessions[session_key]
        session.last_update = time.time()
        
        logger.debug(
            "tp_end_received",
            device_id=device_id,
            pgn=pgn,
            session_id=session_id
        )
        
        return self._check_completion(session_key)
    
    def _check_completion(self, session_key: str) -> Optional[bytes]:
        """Check if session is complete and return assembled data."""
        session = self.sessions[session_key]
        
        # Calculate expected number of frames
        expected_frames = (session.total_size + 5) // 6  # 6 bytes per frame
        
        if len(session.received_frames) >= expected_frames:
            # Assemble data
            assembled_data = bytearray()
            for i in range(expected_frames):
                if i in session.received_frames:
                    assembled_data.extend(session.received_frames[i])
            
            # Remove session
            del self.sessions[session_key]
            
            logger.info(
                "tp_assembly_complete",
                device_id=session.device_id,
                pgn=session.pgn,
                total_size=session.total_size,
                assembled_size=len(assembled_data),
                session_id=session.session_id
            )
            
            return bytes(assembled_data[:session.total_size])
        
        return None
    
    def _cleanup_sessions(self):
        """Cleanup expired sessions."""
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return
        
        expired_sessions = []
        for session_key, session in self.sessions.items():
            if current_time - session.last_update > (self.timeout_ms / 1000.0):
                expired_sessions.append(session_key)
        
        for session_key in expired_sessions:
            session = self.sessions[session_key]
            logger.warning(
                "tp_session_timeout",
                device_id=session.device_id,
                pgn=session.pgn,
                session_id=session.session_id,
                timeout_ms=self.timeout_ms
            )
            del self.sessions[session_key]
        
        # Limit number of sessions
        if len(self.sessions) > self.max_sessions:
            # Remove oldest sessions
            sorted_sessions = sorted(
                self.sessions.items(),
                key=lambda x: x[1].last_update
            )
            for session_key, _ in sorted_sessions[:len(self.sessions) - self.max_sessions]:
                del self.sessions[session_key]
        
        self.last_cleanup = current_time


# Global TP assembler instance
tp_assembler = TPAssembler()
