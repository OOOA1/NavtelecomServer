"""CAN protocol parser for J1939 and OBD-II."""
import struct
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import yaml
import os


class CANSignal:
    """Represents a decoded CAN signal."""
    
    def __init__(self, name: str, value: Any, unit: str = None, 
                 pgn: int = None, spn: int = None, mode: int = None, pid: int = None):
        self.name = name
        self.value = value
        self.unit = unit
        self.pgn = pgn
        self.spn = spn
        self.mode = mode
        self.pid = pid
        self.timestamp = datetime.utcnow()


class CANDecoder:
    """Base class for CAN decoders."""
    
    def decode(self, can_id: int, payload: bytes) -> List[CANSignal]:
        """Decode CAN frame to signals."""
        raise NotImplementedError


class J1939Decoder(CANDecoder):
    """J1939 protocol decoder."""
    
    def __init__(self, dict_path: str = None):
        self.pgn_mappings = {}
        self.spn_mappings = {}
        self.load_dictionary(dict_path)
    
    def load_dictionary(self, dict_path: str):
        """Load J1939 dictionary from YAML file."""
        if not dict_path or not os.path.exists(dict_path):
            # Default J1939 mappings
            self.pgn_mappings = {
                0xF004: "Engine Speed",
                0xF003: "Vehicle Speed",
                0xF00C: "Fuel Level",
                0xFEEE: "Engine Temperature",
                0xFEF1: "Engine Oil Pressure",
                0xFEF2: "Engine Oil Temperature",
            }
            return
        
        try:
            with open(dict_path, 'r') as f:
                data = yaml.safe_load(f)
                self.pgn_mappings = data.get('pgns', {})
        except Exception as e:
            print(f"Error loading J1939 dictionary: {e}")
    
    def decode(self, can_id: int, payload: bytes) -> List[CANSignal]:
        """Decode J1939 frame."""
        signals = []
        
        # Extract J1939 fields from 29-bit CAN ID
        priority = (can_id >> 26) & 0x7
        pgn = (can_id >> 8) & 0xFFFF
        sa = can_id & 0xFF
        
        # Handle different PGN types
        if pgn in self.pgn_mappings:
            pgn_name = self.pgn_mappings[pgn]
            
            if pgn == 0xF004:  # Engine Speed
                if len(payload) >= 2:
                    rpm = struct.unpack('<H', payload[0:2])[0] * 0.125
                    signals.append(CANSignal("EngineRPM", rpm, "rpm", pgn=pgn))
            
            elif pgn == 0xF003:  # Vehicle Speed
                if len(payload) >= 2:
                    speed = struct.unpack('<H', payload[0:2])[0] * 0.00390625
                    signals.append(CANSignal("VehicleSpeed", speed, "km/h", pgn=pgn))
            
            elif pgn == 0xF00C:  # Fuel Level
                if len(payload) >= 1:
                    fuel = payload[0] * 0.4
                    signals.append(CANSignal("FuelLevel", fuel, "%", pgn=pgn))
            
            elif pgn == 0xFEEE:  # Engine Temperature
                if len(payload) >= 1:
                    temp = payload[0] - 40
                    signals.append(CANSignal("EngineTemp", temp, "°C", pgn=pgn))
        
        return signals


class OBD2Decoder(CANDecoder):
    """OBD-II protocol decoder."""
    
    def __init__(self, dict_path: str = None):
        self.pid_mappings = {}
        self.load_dictionary(dict_path)
    
    def load_dictionary(self, dict_path: str):
        """Load OBD-II dictionary from YAML file."""
        if not dict_path or not os.path.exists(dict_path):
            # Default OBD-II mappings
            self.pid_mappings = {
                0x0C: {"name": "EngineRPM", "formula": "(A*256 + B) / 4", "unit": "rpm"},
                0x0D: {"name": "VehicleSpeed", "formula": "A", "unit": "km/h"},
                0x05: {"name": "EngineCoolantTemp", "formula": "A - 40", "unit": "°C"},
                0x0F: {"name": "IntakeAirTemp", "formula": "A - 40", "unit": "°C"},
                0x10: {"name": "MAFAirFlow", "formula": "(A*256 + B) / 100", "unit": "g/s"},
                0x11: {"name": "ThrottlePosition", "formula": "A * 100 / 255", "unit": "%"},
            }
            return
        
        try:
            with open(dict_path, 'r') as f:
                data = yaml.safe_load(f)
                self.pid_mappings = data.get('modes', {}).get('01', {}).get('pids', {})
        except Exception as e:
            print(f"Error loading OBD-II dictionary: {e}")
    
    def decode(self, can_id: int, payload: bytes) -> List[CANSignal]:
        """Decode OBD-II frame."""
        signals = []
        
        # Check if this is an OBD-II response (0x7E8-0x7EF)
        if 0x7E8 <= can_id <= 0x7EF:
            if len(payload) >= 3:
                mode = payload[1]
                pid = payload[2]
                
                if mode == 0x41 and pid in self.pid_mappings:  # Mode 01 response
                    pid_info = self.pid_mappings[pid]
                    value = self._calculate_pid_value(payload[3:], pid_info["formula"])
                    
                    signals.append(CANSignal(
                        pid_info["name"], 
                        value, 
                        pid_info["unit"],
                        mode=mode,
                        pid=pid
                    ))
        
        return signals
    
    def _calculate_pid_value(self, data: bytes, formula: str) -> float:
        """Calculate PID value using formula."""
        if not data:
            return 0.0
        
        # Simple formula evaluation (A, B, C, D are bytes)
        A = data[0] if len(data) > 0 else 0
        B = data[1] if len(data) > 1 else 0
        C = data[2] if len(data) > 2 else 0
        D = data[3] if len(data) > 3 else 0
        
        try:
            # Replace formula variables with actual values
            formula = formula.replace('A', str(A))
            formula = formula.replace('B', str(B))
            formula = formula.replace('C', str(C))
            formula = formula.replace('D', str(D))
            
            return eval(formula)
        except:
            return 0.0


class CANParser:
    """Main CAN parser that coordinates different decoders."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.j1939_decoder = J1939Decoder(
            self.config.get('dicts', {}).get('j1939')
        )
        self.obd2_decoder = OBD2Decoder(
            self.config.get('dicts', {}).get('obd2')
        )
        self.brand_decoders = {}
        self.load_brand_packs()
    
    def load_brand_packs(self):
        """Load brand-specific decoders."""
        brand_packs = self.config.get('dicts', {}).get('brand_packs', [])
        for pack_path in brand_packs:
            if os.path.exists(pack_path):
                try:
                    with open(pack_path, 'r') as f:
                        brand_data = yaml.safe_load(f)
                        brand_name = brand_data.get('brand', 'unknown')
                        self.brand_decoders[brand_name] = brand_data
                except Exception as e:
                    print(f"Error loading brand pack {pack_path}: {e}")
    
    def parse_can_frame(self, can_id: int, payload: bytes, 
                       device_id: str = None) -> List[CANSignal]:
        """Parse CAN frame using appropriate decoder."""
        signals = []
        
        # Determine protocol type
        if can_id & 0x80000000:  # J1939 (29-bit)
            signals.extend(self.j1939_decoder.decode(can_id, payload))
        elif 0x7E0 <= can_id <= 0x7EF:  # OBD-II
            signals.extend(self.obd2_decoder.decode(can_id, payload))
        else:
            # Try brand-specific decoders
            for brand_name, brand_data in self.brand_decoders.items():
                if self._matches_brand_pattern(can_id, brand_data):
                    signals.extend(self._decode_brand_specific(can_id, payload, brand_data))
                    break
        
        return signals
    
    def _matches_brand_pattern(self, can_id: int, brand_data: Dict) -> bool:
        """Check if CAN ID matches brand-specific pattern."""
        patterns = brand_data.get('patterns', [])
        for pattern in patterns:
            if pattern.get('can_id_range'):
                start, end = pattern['can_id_range']
                if start <= can_id <= end:
                    return True
        return False
    
    def _decode_brand_specific(self, can_id: int, payload: bytes, 
                              brand_data: Dict) -> List[CANSignal]:
        """Decode brand-specific CAN frame."""
        signals = []
        # Implement brand-specific decoding logic here
        return signals

    def _reload_dictionary(self, dict_file: str, new_dict: Dict):
        """Reload a specific dictionary."""
        try:
            if "j1939" in dict_file:
                self.j1939_dicts = new_dict
                logger.info("j1939_dictionary_reloaded", file=dict_file)
            elif "obd2" in dict_file:
                self.obd2_dicts = new_dict
                logger.info("obd2_dictionary_reloaded", file=dict_file)
            elif "volvo" in dict_file or "scania" in dict_file:
                # Update brand packs
                for i, brand_file in enumerate(settings.can_dicts_brand_packs):
                    if dict_file in brand_file:
                        self.brand_packs[i] = new_dict
                        logger.info("brand_dictionary_reloaded", file=dict_file, index=i)
                        break
            else:
                logger.warning("unknown_dictionary_file", file=dict_file)
        except Exception as e:
            logger.error("dictionary_reload_error", file=dict_file, error=str(e))


# Global CAN parser instance
can_parser = CANParser()
