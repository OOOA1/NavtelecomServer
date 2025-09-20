"""Frame decoder service."""
import asyncio
from typing import Optional
from app.proto_navtel_v6 import try_parse_frame, NavtelParseError
from app.models import save_telemetry, save_decode_error


async def decode_and_store(raw_id: int, payload: bytes) -> bool:
    """
    Decode frame and store telemetry data.
    
    Args:
        raw_id: ID of raw frame in database
        payload: Frame payload bytes
        
    Returns:
        True if frame was successfully decoded, False otherwise
    """
    try:
        # Try to parse frame
        parsed_data = try_parse_frame(payload)
        
        if parsed_data is None:
            # Incomplete frame, not an error
            return False
        
        # Extract telemetry data
        device_id = parsed_data.get("device_id")
        device_time = parsed_data.get("device_time")
        
        if not device_id:
            await save_decode_error(
                raw_id=raw_id,
                stage="decode",
                message="Missing device ID"
            )
            return False
        
        # Save telemetry data
        await save_telemetry(
            raw_id=raw_id,
            device_id=device_id,
            device_time=device_time,
            lat=parsed_data.get("lat"),
            lon=parsed_data.get("lon"),
            speed=parsed_data.get("speed"),
            course=parsed_data.get("course"),
            ignition=parsed_data.get("ignition"),
            fuel_level=parsed_data.get("fuel_level"),
            engine_hours=parsed_data.get("engine_hours"),
            temperature=parsed_data.get("temperature")
        )
        
        return True
        
    except NavtelParseError as e:
        # Protocol parsing error
        await save_decode_error(
            raw_id=raw_id,
            stage="decode",
            message=str(e)
        )
        return False
        
    except Exception as e:
        # Unexpected error
        await save_decode_error(
            raw_id=raw_id,
            stage="decode",
            message=f"Unexpected error: {str(e)}"
        )
        return False


class DecoderService:
    """Background decoder service."""
    
    def __init__(self):
        self.running = False
        self.queue = asyncio.Queue()
    
    async def start(self):
        """Start decoder service."""
        self.running = True
        asyncio.create_task(self._process_queue())
    
    async def stop(self):
        """Stop decoder service."""
        self.running = False
    
    async def add_frame(self, raw_id: int, payload: bytes):
        """Add frame to decode queue."""
        await self.queue.put((raw_id, payload))
    
    async def _process_queue(self):
        """Process decode queue."""
        while self.running:
            try:
                # Get frame from queue with timeout
                raw_id, payload = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0
                )
                
                # Decode frame
                await decode_and_store(raw_id, payload)
                
            except asyncio.TimeoutError:
                # Timeout is normal, continue
                continue
            except Exception as e:
                print(f"Decoder service error: {e}")


# Global decoder service instance
decoder_service = DecoderService()
