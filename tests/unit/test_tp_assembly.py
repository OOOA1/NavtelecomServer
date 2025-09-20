"""
Unit tests for J1939 Transport Protocol assembly.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch

from app.tp_assembly import TPAssembler, TPSession


class TestTPSession:
    """Test TP session management."""
    
    @pytest.mark.unit
    def test_session_creation(self):
        """Test TP session creation."""
        session = TPSession(
            device_id="TEST1234",
            pgn=0xECFF,
            src_addr=0x00,
            session_id=1
        )
        
        assert session.device_id == "TEST1234"
        assert session.pgn == 0xECFF
        assert session.src_addr == 0x00
        assert session.session_id == 1
        assert len(session.fragments) == 0
        assert session.total_packets == 0
        assert session.assembled_data is None
    
    @pytest.mark.unit
    def test_session_add_fragment(self):
        """Test adding fragment to session."""
        session = TPSession("TEST1234", 0xECFF, 0x00, 1)
        
        # Add first fragment
        session.add_fragment(1, b"Hello")
        assert len(session.fragments) == 1
        assert session.fragments[1] == b"Hello"
        
        # Add second fragment
        session.add_fragment(2, b"World")
        assert len(session.fragments) == 2
        assert session.fragments[2] == b"World"
    
    @pytest.mark.unit
    def test_session_is_complete(self):
        """Test session completion check."""
        session = TPSession("TEST1234", 0xECFF, 0x00, 1)
        session.total_packets = 2
        
        # Not complete yet
        assert not session.is_complete()
        
        # Add first fragment
        session.add_fragment(1, b"Hello")
        assert not session.is_complete()
        
        # Add second fragment
        session.add_fragment(2, b"World")
        assert session.is_complete()
    
    @pytest.mark.unit
    def test_session_assemble_data(self):
        """Test data assembly."""
        session = TPSession("TEST1234", 0xECFF, 0x00, 1)
        session.total_packets = 3
        
        # Add fragments in wrong order
        session.add_fragment(3, b"!")
        session.add_fragment(1, b"Hello")
        session.add_fragment(2, b"World")
        
        assembled = session.assemble_data()
        assert assembled == b"HelloWorld!"
    
    @pytest.mark.unit
    def test_session_timeout(self):
        """Test session timeout."""
        session = TPSession("TEST1234", 0xECFF, 0x00, 1)
        
        # Check if session is expired (should not be immediately)
        assert not session.is_expired(1000)  # 1 second timeout
        
        # Simulate time passing
        import time
        time.sleep(0.1)  # 100ms
        
        # Should still not be expired
        assert not session.is_expired(1000)


class TestTPAssembler:
    """Test TP assembler functionality."""
    
    @pytest.fixture
    def assembler(self):
        """Create TP assembler instance."""
        return TPAssembler(timeout_ms=5000)
    
    @pytest.mark.unit
    def test_assembler_initialization(self):
        """Test assembler initialization."""
        assembler = TPAssembler(timeout_ms=1000)
        
        assert assembler.timeout_ms == 1000
        assert len(assembler.sessions) == 0
    
    @pytest.mark.unit
    def test_is_multi_frame_bam(self, assembler):
        """Test BAM (Broadcast Announce Message) detection."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00  # BAM PGN
        payload = b"\x20\x00\x10\x01\x01\x02\x03\x04"  # BAM with data
        
        assert assembler.is_multi_frame(device_id, can_id, payload)
    
    @pytest.mark.unit
    def test_is_multi_frame_rts(self, assembler):
        """Test RTS (Request to Send) detection."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00  # RTS PGN
        payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        
        assert assembler.is_multi_frame(device_id, can_id, payload)
    
    @pytest.mark.unit
    def test_is_multi_frame_cts(self, assembler):
        """Test CTS (Clear to Send) detection."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00  # CTS PGN
        payload = b"\x11\x00\x10\x00\x00\x00\x00\x00"  # CTS
        
        assert assembler.is_multi_frame(device_id, can_id, payload)
    
    @pytest.mark.unit
    def test_is_multi_frame_single(self, assembler):
        """Test single frame detection."""
        device_id = "TEST1234"
        can_id = 0x18F00400  # Single frame PGN
        payload = b"\x00\x80"  # Single frame data
        
        assert not assembler.is_multi_frame(device_id, can_id, payload)
    
    @pytest.mark.unit
    def test_bam_assembly(self, assembler):
        """Test BAM assembly."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00  # BAM PGN
        payload = b"\x20\x00\x10\x01\x01\x02\x03\x04"  # BAM with data
        
        result = assembler.process_frame(device_id, can_id, payload)
        
        # BAM should return assembled data immediately
        assert result is not None
        assert len(result) > 0
    
    @pytest.mark.unit
    def test_rts_cts_assembly(self, assembler):
        """Test RTS/CTS assembly."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00  # RTS PGN
        payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        
        # RTS should not return data immediately
        result = assembler.process_frame(device_id, can_id, payload)
        assert result is None
        
        # Should create a session
        session_key = f"{device_id}:0xECFF:0x00:1"
        assert session_key in assembler.sessions
    
    @pytest.mark.unit
    def test_fragment_assembly(self, assembler):
        """Test fragment assembly."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        
        # First, create a session with RTS
        rts_payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        assembler.process_frame(device_id, can_id, rts_payload)
        
        # Add fragments
        fragment1 = b"\x21\x01\x01\x02\x03\x04\x05\x06"  # Fragment 1
        fragment2 = b"\x22\x02\x07\x08\x09\x0A\x0B\x0C"  # Fragment 2
        
        result1 = assembler.process_frame(device_id, can_id, fragment1)
        result2 = assembler.process_frame(device_id, can_id, fragment2)
        
        # Should return assembled data after last fragment
        assert result1 is None  # Not complete yet
        assert result2 is not None  # Complete
        assert len(result2) > 0
    
    @pytest.mark.unit
    def test_session_cleanup(self, assembler):
        """Test session cleanup."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        
        # Create session
        assembler.process_frame(device_id, can_id, payload)
        
        # Should have one session
        assert len(assembler.sessions) == 1
        
        # Cleanup expired sessions
        assembler.cleanup_expired_sessions()
        
        # Should still have session (not expired yet)
        assert len(assembler.sessions) == 1
    
    @pytest.mark.unit
    def test_memory_limit(self, assembler):
        """Test memory limit enforcement."""
        # Set low memory limit
        assembler.max_sessions = 2
        
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        
        # Create multiple sessions
        for i in range(5):
            assembler.process_frame(f"DEVICE{i}", can_id, payload)
        
        # Should not exceed max sessions
        assert len(assembler.sessions) <= assembler.max_sessions
    
    @pytest.mark.unit
    def test_duplicate_fragment(self, assembler):
        """Test handling duplicate fragments."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        
        # Create session
        rts_payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        assembler.process_frame(device_id, can_id, rts_payload)
        
        # Add same fragment twice
        fragment = b"\x21\x01\x01\x02\x03\x04\x05\x06"  # Fragment 1
        
        result1 = assembler.process_frame(device_id, can_id, fragment)
        result2 = assembler.process_frame(device_id, can_id, fragment)
        
        # Should handle duplicates gracefully
        assert result1 is None  # Not complete
        assert result2 is None  # Still not complete (duplicate)
    
    @pytest.mark.unit
    def test_invalid_fragment_sequence(self, assembler):
        """Test handling invalid fragment sequence."""
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        
        # Create session
        rts_payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        assembler.process_frame(device_id, can_id, rts_payload)
        
        # Add fragment with invalid sequence
        invalid_fragment = b"\x21\xFF\x01\x02\x03\x04\x05\x06"  # Invalid sequence
        
        result = assembler.process_frame(device_id, can_id, invalid_fragment)
        
        # Should handle invalid sequence gracefully
        assert result is None
    
    @pytest.mark.unit
    def test_assembly_performance(self, assembler):
        """Test assembly performance."""
        import time
        
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        
        start_time = time.time()
        
        # Process 1000 BAM frames
        for i in range(1000):
            payload = b"\x20\x00\x10\x01" + bytes([i % 256, (i >> 8) % 256, (i >> 16) % 256, (i >> 24) % 256])
            assembler.process_frame(device_id, can_id, payload)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should process 1000 frames in less than 1 second
        assert duration < 1.0
        print(f"Processed 1000 TP frames in {duration:.3f} seconds")
    
    @pytest.mark.unit
    def test_concurrent_sessions(self, assembler):
        """Test concurrent session handling."""
        device_ids = [f"DEVICE{i}" for i in range(10)]
        can_id = 0x18ECFF00
        payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        
        # Create multiple concurrent sessions
        for device_id in device_ids:
            assembler.process_frame(device_id, can_id, payload)
        
        # Should have all sessions
        assert len(assembler.sessions) == len(device_ids)
        
        # Each session should be independent
        for device_id in device_ids:
            session_key = f"{device_id}:0xECFF:0x00:1"
            assert session_key in assembler.sessions
    
    @pytest.mark.unit
    def test_session_timeout_cleanup(self, assembler):
        """Test session timeout cleanup."""
        # Set very short timeout
        assembler.timeout_ms = 100
        
        device_id = "TEST1234"
        can_id = 0x18ECFF00
        payload = b"\x10\x00\x10\x00\x00\x00\x00\x00"  # RTS
        
        # Create session
        assembler.process_frame(device_id, can_id, payload)
        assert len(assembler.sessions) == 1
        
        # Wait for timeout
        import time
        time.sleep(0.2)  # 200ms
        
        # Cleanup expired sessions
        assembler.cleanup_expired_sessions()
        
        # Session should be cleaned up
        assert len(assembler.sessions) == 0
