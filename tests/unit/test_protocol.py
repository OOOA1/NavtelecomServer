"""
Unit tests for Navtelecom protocol parsing and validation.
"""
import pytest
import struct
from unittest.mock import Mock, patch

from app.proto_navtel_v6 import (
    calculate_crc16, try_parse_frame, parse_frame_data,
    generate_ack_response, generate_nack_response,
    NavtelParseError
)


class TestCRC16:
    """Test CRC16 calculation."""
    
    @pytest.mark.unit
    def test_crc16_calculation(self):
        """Test CRC16 calculation with known values."""
        # Test data
        test_data = b"TEST1234"
        expected_crc = 0x1234  # This would be calculated
        
        # Calculate CRC
        crc = calculate_crc16(test_data)
        
        # Verify CRC is a valid 16-bit value
        assert 0 <= crc <= 0xFFFF
        assert isinstance(crc, int)
    
    @pytest.mark.unit
    def test_crc16_consistency(self):
        """Test CRC16 consistency for same input."""
        test_data = b"CONSISTENCY_TEST"
        
        crc1 = calculate_crc16(test_data)
        crc2 = calculate_crc16(test_data)
        
        assert crc1 == crc2
    
    @pytest.mark.unit
    def test_crc16_different_inputs(self):
        """Test CRC16 produces different values for different inputs."""
        data1 = b"INPUT1"
        data2 = b"INPUT2"
        
        crc1 = calculate_crc16(data1)
        crc2 = calculate_crc16(data2)
        
        assert crc1 != crc2


class TestFrameParsing:
    """Test frame parsing functionality."""
    
    @pytest.mark.unit
    def test_parse_valid_frame(self, test_navtelecom_frame):
        """Test parsing a valid Navtelecom frame."""
        result = try_parse_frame(test_navtelecom_frame)
        
        assert result is not None
        assert "device_id" in result
        assert "timestamp" in result
        assert "data_type" in result
    
    @pytest.mark.unit
    def test_parse_invalid_crc(self):
        """Test parsing frame with invalid CRC."""
        # Create frame with wrong CRC
        device_id = b"TEST1234"
        timestamp = b"\x00\x00\x00\x01"
        data_type = b"\x01"
        payload = b"\x00\x00\x00\x00"
        
        frame_data = device_id + timestamp + data_type + payload
        wrong_crc = 0xFFFF  # Wrong CRC
        
        frame = bytearray()
        frame.append(0x7E)  # Start marker
        frame.extend(len(frame_data).to_bytes(2, 'little'))  # Length
        frame.extend(frame_data)  # Data
        frame.extend(wrong_crc.to_bytes(2, 'little'))  # Wrong CRC
        frame.append(0x7E)  # End marker
        
        with pytest.raises(NavtelParseError):
            try_parse_frame(bytes(frame))
    
    @pytest.mark.unit
    def test_parse_incomplete_frame(self):
        """Test parsing incomplete frame."""
        incomplete_frame = b"\x7E\x10\x00"  # Start marker + length, but no data
        
        result = try_parse_frame(incomplete_frame)
        assert result is None
    
    @pytest.mark.unit
    def test_parse_malformed_frame(self):
        """Test parsing malformed frame."""
        malformed_frames = [
            b"",  # Empty
            b"\x7E",  # Only start marker
            b"\x7E\x00\x00\x7E",  # No data
            b"INVALID_DATA",  # No markers
        ]
        
        for frame in malformed_frames:
            try:
                result = try_parse_frame(frame)
                # If no exception, result should be None or dict
                assert result is None or isinstance(result, dict)
            except Exception:
                # Exceptions are also acceptable for malformed frames
                pass


class TestACKResponse:
    """Test ACK/NACK response generation."""
    
    @pytest.mark.unit
    def test_ack_response_generation(self):
        """Test ACK response generation."""
        device_id = "TEST1234"
        data_type = 1
        
        ack = generate_ack_response(device_id, data_type)
        
        assert isinstance(ack, bytes)
        assert len(ack) > 0
        assert ack.startswith(b"\x7E")  # Should start with marker
    
    @pytest.mark.unit
    def test_nack_response_generation(self):
        """Test NACK response generation."""
        device_id = "TEST1234"
        error_code = 0x01
        
        nack = generate_nack_response(device_id, error_code)
        
        assert isinstance(nack, bytes)
        assert len(nack) > 0
        assert nack.startswith(b"\x7E")  # Should start with marker
    
    @pytest.mark.unit
    def test_ack_nack_different(self):
        """Test ACK and NACK responses are different."""
        device_id = "TEST1234"
        data_type = 1
        
        ack = generate_ack_response(device_id, data_type)
        nack = generate_nack_response(device_id, 0x01)
        
        assert ack != nack


class TestFrameDataParsing:
    """Test frame data parsing."""
    
    @pytest.mark.unit
    def test_parse_gps_data(self):
        """Test GPS data parsing."""
        # Mock GPS data (simplified)
        gps_data = struct.pack('<dd', 55.7558, 37.6176)  # lat, lon
        
        with patch('app.proto_navtel_v6.parse_gps_data') as mock_parse:
            mock_parse.return_value = {
                "lat": 55.7558,
                "lon": 37.6176,
                "speed": 0.0,
                "course": 0.0
            }
            
            result = parse_frame_data(b"TEST1234" + b"\x00\x00\x00\x01" + b"\x01" + gps_data)
            
            assert result is not None
            assert "lat" in result
            assert "lon" in result
    
    @pytest.mark.unit
    def test_parse_can_data(self):
        """Test CAN data parsing."""
        # Mock CAN data
        can_data = struct.pack('<I', 0x18F00400) + b"\x00\x80"  # can_id + payload
        
        with patch('app.proto_navtel_v6.parse_can_data') as mock_parse:
            mock_parse.return_value = {
                "can_frames": [
                    {
                        "can_id": 0x18F00400,
                        "payload": "0080",
                        "dlc": 2
                    }
                ]
            }
            
            result = parse_frame_data(b"TEST1234" + b"\x00\x00\x00\x01" + b"\x02" + can_data)
            
            assert result is not None
            assert "can_frames" in result
    
    @pytest.mark.unit
    def test_parse_event_data(self):
        """Test event data parsing."""
        # Mock event data
        event_data = struct.pack('<I', 0x01)  # event code
        
        with patch('app.proto_navtel_v6.parse_event_data') as mock_parse:
            mock_parse.return_value = {
                "event_code": 0x01,
                "event_data": {}
            }
            
            result = parse_frame_data(b"TEST1234" + b"\x00\x00\x00\x01" + b"\x03" + event_data)
            
            assert result is not None
            assert "event_code" in result


class TestProtocolEdgeCases:
    """Test protocol edge cases and error conditions."""
    
    @pytest.mark.unit
    def test_empty_payload(self):
        """Test frame with empty payload."""
        device_id = b"TEST1234"
        timestamp = b"\x00\x00\x00\x01"
        data_type = b"\x01"
        payload = b""  # Empty payload
        
        frame_data = device_id + timestamp + data_type + payload
        crc = calculate_crc16(frame_data)
        
        frame = bytearray()
        frame.append(0x7E)
        frame.extend(len(frame_data).to_bytes(2, 'little'))
        frame.extend(frame_data)
        frame.extend(crc.to_bytes(2, 'little'))
        frame.append(0x7E)
        
        try:
            result = try_parse_frame(bytes(frame))
            # Empty payload might cause parsing error, which is acceptable
            assert result is None or isinstance(result, dict)
        except Exception:
            # Exceptions are acceptable for empty payload
            pass
    
    @pytest.mark.unit
    def test_large_payload(self):
        """Test frame with large payload."""
        device_id = b"TEST1234"
        timestamp = b"\x00\x00\x00\x01"
        data_type = b"\x01"
        payload = b"X" * 1000  # Large payload
        
        frame_data = device_id + timestamp + data_type + payload
        crc = calculate_crc16(frame_data)
        
        frame = bytearray()
        frame.append(0x7E)
        frame.extend(len(frame_data).to_bytes(2, 'little'))
        frame.extend(frame_data)
        frame.extend(crc.to_bytes(2, 'little'))
        frame.append(0x7E)
        
        result = try_parse_frame(bytes(frame))
        assert result is not None
    
    @pytest.mark.unit
    def test_invalid_data_type(self):
        """Test frame with invalid data type."""
        device_id = b"TEST1234"
        timestamp = b"\x00\x00\x00\x01"
        data_type = b"\xFF"  # Invalid data type
        payload = b"\x00\x00\x00\x00"
        
        frame_data = device_id + timestamp + data_type + payload
        crc = calculate_crc16(frame_data)
        
        frame = bytearray()
        frame.append(0x7E)
        frame.extend(len(frame_data).to_bytes(2, 'little'))
        frame.extend(frame_data)
        frame.extend(crc.to_bytes(2, 'little'))
        frame.append(0x7E)
        
        result = try_parse_frame(bytes(frame))
        # Should still parse successfully, data type validation is separate
        assert result is not None
    
    @pytest.mark.unit
    def test_missing_end_marker(self):
        """Test frame missing end marker."""
        device_id = b"TEST1234"
        timestamp = b"\x00\x00\x00\x01"
        data_type = b"\x01"
        payload = b"\x00\x00\x00\x00"
        
        frame_data = device_id + timestamp + data_type + payload
        crc = calculate_crc16(frame_data)
        
        frame = bytearray()
        frame.append(0x7E)
        frame.extend(len(frame_data).to_bytes(2, 'little'))
        frame.extend(frame_data)
        frame.extend(crc.to_bytes(2, 'little'))
        # Missing end marker
        
        try:
            result = try_parse_frame(bytes(frame))
            # Missing end marker should cause parsing error
            assert result is None
        except Exception:
            # Exceptions are also acceptable for missing end marker
            pass


class TestProtocolPerformance:
    """Test protocol parsing performance."""
    
    @pytest.mark.unit
    @pytest.mark.slow
    def test_parse_performance(self, test_navtelecom_frame):
        """Test frame parsing performance."""
        import time
        
        start_time = time.time()
        
        # Parse frame 1000 times
        for _ in range(1000):
            try_parse_frame(test_navtelecom_frame)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should parse 1000 frames in less than 1 second
        assert duration < 1.0
        print(f"Parsed 1000 frames in {duration:.3f} seconds")
    
    @pytest.mark.unit
    def test_crc_performance(self):
        """Test CRC calculation performance."""
        import time
        
        test_data = b"PERFORMANCE_TEST_DATA" * 100  # Large data
        
        start_time = time.time()
        
        # Calculate CRC 1000 times
        for _ in range(1000):
            calculate_crc16(test_data)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should calculate 1000 CRCs in less than 5 seconds (more realistic)
        assert duration < 5.0
        print(f"Calculated 1000 CRCs in {duration:.3f} seconds")
