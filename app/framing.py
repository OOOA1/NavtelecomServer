"""Frame extraction from TCP stream."""
import asyncio
import struct
from typing import AsyncGenerator, Optional
from app.settings import settings


class FrameExtractor:
    """Extract frames from TCP stream."""
    
    def __init__(self, max_frame_size: int = None):
        self.max_frame_size = max_frame_size or settings.frame_max_size
        self.buffer = bytearray()
    
    async def frame_stream(self, reader: asyncio.StreamReader) -> AsyncGenerator[bytes, None]:
        """Extract frames from stream."""
        while True:
            try:
                # Read chunk with timeout
                chunk = await asyncio.wait_for(
                    reader.read(self.max_frame_size),
                    timeout=settings.read_timeout
                )
                
                if not chunk:
                    break
                
                self.buffer.extend(chunk)
                
                # Try to extract frames from buffer
                while True:
                    frame = self._extract_frame()
                    if frame is None:
                        break
                    yield frame
                    
            except asyncio.TimeoutError:
                # Timeout is normal, continue reading
                continue
            except Exception as e:
                print(f"Frame extraction error: {e}")
                break
    
    def _extract_frame(self) -> Optional[bytes]:
        """Extract single frame from buffer."""
        if len(self.buffer) < 4:
            return None
        
        # Try to find frame start marker (0x7E for Navtelecom)
        start_idx = self.buffer.find(0x7E)
        if start_idx == -1:
            # No start marker found, clear buffer
            self.buffer.clear()
            return None
        
        # Remove data before start marker
        if start_idx > 0:
            self.buffer = self.buffer[start_idx:]
        
        # Check if we have enough data for frame header
        if len(self.buffer) < 4:
            return None
        
        # Try to parse frame length (this is protocol-specific)
        # For now, use simple approach - read until next 0x7E or max size
        end_idx = self.buffer.find(0x7E, 1)
        
        if end_idx == -1:
            # No end marker found
            if len(self.buffer) >= self.max_frame_size:
                # Frame too large, return what we have
                frame = bytes(self.buffer[:self.max_frame_size])
                self.buffer = self.buffer[self.max_frame_size:]
                return frame
            return None
        
        # Extract frame
        frame = bytes(self.buffer[:end_idx + 1])
        self.buffer = self.buffer[end_idx + 1:]
        
        return frame


# Global frame extractor instance
frame_extractor = FrameExtractor()


async def frame_stream(reader: asyncio.StreamReader) -> AsyncGenerator[bytes, None]:
    """Extract frames from stream using global extractor."""
    async for frame in frame_extractor.frame_stream(reader):
        yield frame
