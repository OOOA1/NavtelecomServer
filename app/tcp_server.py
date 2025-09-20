"""TCP server for receiving GPS/telemetry data."""
import asyncio
import socket
import uvloop
import structlog
from datetime import datetime, timezone
from app.settings import settings
from app.framing import frame_stream
from app.models import save_raw_frame, save_can_raw_frame, save_can_signal
from app.decoder import decoder_service
from app.proto_navtel_v6 import try_parse_frame, generate_ack_response, generate_nack_response, NavtelParseError
from app.can_parser import can_parser
from app.tp_assembly import tp_assembler
from app.backpressure import backpressure_manager, rate_limiter
from app.batch_processor import batch_processor
from app.retention import retention_manager
from app.alerts import alert_manager
from app.slo import slo_manager
from app.reprocessing import reprocessing_manager
from app.hot_reload import hot_reload_manager
from app.canary import canary_manager
from app.metrics import (
    record_frame_received, record_ack_sent, record_can_frame_processed,
    record_connection_event, set_active_connections, record_database_operation
)

# Set up structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def process_can_frames(can_frames: list, device_id: str, raw_id: int):
    """Process CAN frames and save to database."""
    for can_frame in can_frames:
        try:
            can_id = can_frame["can_id"]
            payload = bytes.fromhex(can_frame["payload"])
            
            # Check if device is in canary for enhanced TP assembly
            use_enhanced_tp = canary_manager.get_feature_flag("enhanced_tp_assembly", device_id)
            
            # Check for TP assembly
            if use_enhanced_tp:
                # Use enhanced TP assembly
                assembled_data = tp_assembler.process_frame_enhanced(device_id, can_id, payload)
            else:
                # Use standard TP assembly
                assembled_data = tp_assembler.process_frame(device_id, can_id, payload)
            
            if assembled_data:
                # Process assembled TP data
                payload = assembled_data
                logger.info(
                    "tp_assembly_complete",
                    device_id=device_id,
                    can_id=can_id,
                    assembled_size=len(assembled_data),
                    enhanced=use_enhanced_tp
                )
            
            # Check rate limiting
            if not rate_limiter.is_allowed(device_id=device_id):
                logger.warning(
                    "rate_limit_exceeded",
                    device_id=device_id,
                    can_id=can_id
                )
                continue
            
            # Check backpressure
            if backpressure_manager.should_persist_only():
                # Only save raw data, skip processing
                await batch_processor.add_item(
                    "can_raw",
                    "insert",
                    {
                        "device_id": device_id,
                        "can_id": can_id,
                        "payload": payload,
                        "dlc": can_frame["dlc"],
                        "is_extended": can_frame["is_extended"],
                        "dev_time": datetime.fromtimestamp(can_frame["timestamp"], tz=timezone.utc) if can_frame.get("timestamp") else None,
                        "raw_id": raw_id
                    },
                    priority="high"
                )
                continue
            
            # Save raw CAN frame
            can_raw_id = await save_can_raw_frame(
                device_id=device_id,
                can_id=can_id,
                payload=payload,
                dlc=can_frame["dlc"],
                is_extended=can_frame["is_extended"],
                dev_time=datetime.fromtimestamp(can_frame["timestamp"], tz=timezone.utc) if can_frame.get("timestamp") else None,
                raw_id=raw_id
            )
            
            # Check if device is in canary for new CAN parser
            use_new_parser = canary_manager.get_feature_flag("new_can_parser", device_id)
            
            # Parse CAN signals (new or standard parser)
            if use_new_parser:
                signals = can_parser.parse_can_frame_enhanced(can_id, payload, device_id)
            else:
                signals = can_parser.parse_can_frame(can_id, payload, device_id)
            
            # Save decoded signals in batch
            for signal in signals:
                await batch_processor.add_item(
                    "can_signals",
                    "insert",
                    {
                        "device_id": device_id,
                        "signal_time": signal.timestamp,
                        "name": signal.name,
                        "value_num": signal.value if isinstance(signal.value, (int, float)) else None,
                        "value_text": str(signal.value) if not isinstance(signal.value, (int, float)) else None,
                        "unit": signal.unit,
                        "pgn": signal.pgn,
                        "spn": signal.spn,
                        "mode": signal.mode,
                        "pid": signal.pid,
                        "raw_id": can_raw_id
                    },
                    priority="normal"
                )
            
            # Send shadow traffic if configured
            if signals:
                await canary_manager.send_shadow_traffic(
                    "external_api",
                    device_id,
                    {
                        "can_id": can_id,
                        "signals": [
                            {
                                "name": s.name,
                                "value": s.value,
                                "unit": s.unit
                            }
                            for s in signals
                        ]
                    }
                )
            
            # Record CAN metrics
            record_can_frame_processed(device_id, can_id, len(signals))
            
            logger.debug(
                "can_frames_processed",
                device_id=device_id,
                can_id=can_id,
                signals_count=len(signals)
            )
            
        except Exception as e:
            logger.error(
                "can_frame_processing_error",
                device_id=device_id,
                can_id=can_frame.get("can_id"),
                error=str(e)
            )


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle client connection."""
    peer = writer.get_extra_info("peername")
    ip, port = peer if peer else ("unknown", 0)
    
    connection_id = f"{ip}:{port}"
    logger.info("connection_established", client=connection_id)
    record_connection_event("connected", ip)
    
    try:
        # Configure socket for low latency
        sock = writer.get_extra_info('socket')
        if sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Process frames from client
        async for frame in frame_stream(reader):
            frame_start_time = time.time()
            try:
                # Fast validation and ACK (before heavy processing)
                ack_sent = False
                device_id = None
                data_type = 0
                
                try:
                    # Quick parse for ACK generation
                    parsed_data = try_parse_frame(frame)
                    if parsed_data:
                        device_id = parsed_data.get("device_id", "unknown")
                        data_type = parsed_data.get("data_type", 0)
                        
                        # Send fast ACK
                        ack_response = generate_ack_response(device_id, data_type)
                        writer.write(ack_response)
                        await writer.drain()
                        record_ack_sent()
                        ack_sent = True
                        
                        # Record ACK latency
                        ack_latency = (time.time() - frame_start_time) * 1000
                        slo_manager.record_measurement(
                            "ack_latency", ack_latency, True, device_id, "ack"
                        )
                        
                        # Record metrics
                        record_frame_received(device_id, len(frame), data_type)
                        record_ack_sent(device_id, "ack")
                        
                        logger.debug(
                            "fast_ack_sent",
                            client=connection_id,
                            device_id=device_id,
                            data_type=data_type
                        )
                except NavtelParseError as e:
                    # Send NACK for protocol errors
                    if device_id:
                        nack_response = generate_nack_response(device_id, 0x02)  # Format error
                        writer.write(nack_response)
                        await writer.drain()
                        record_ack_sent(device_id, "nack")
                    
                    logger.warning(
                        "protocol_error",
                        client=connection_id,
                        error=str(e)
                    )
                    continue
                
                # Save raw frame (after ACK)
                raw_id = await save_raw_frame(
                    payload=frame,
                    remote_ip=ip,
                    remote_port=port,
                    device_hint=device_id
                )
                
                # Process CAN frames if present
                if parsed_data and "can_frames" in parsed_data:
                    await process_can_frames(parsed_data["can_frames"], device_id, raw_id)
                
                # Add to decoder queue for further processing
                decode_start_time = time.time()
                await decoder_service.add_frame(raw_id, frame)
                
                # Record decode latency
                decode_latency = (time.time() - decode_start_time) * 1000
                slo_manager.record_measurement(
                    "decode_latency", decode_latency, True, device_id, "decode"
                )
                
                logger.debug(
                    "frame_processed",
                    client=connection_id,
                    frame_size=len(frame),
                    raw_id=raw_id,
                    device_id=device_id,
                    ack_sent=ack_sent
                )
                
            except Exception as e:
                logger.error(
                    "frame_processing_error",
                    client=connection_id,
                    error=str(e)
                )
                
    except asyncio.IncompleteReadError:
        logger.info("connection_closed_by_client", client=connection_id)
    except Exception as e:
        logger.error("connection_error", client=connection_id, error=str(e))
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        
        logger.info("connection_closed", client=connection_id)
        record_connection_event("disconnected", ip)


async def main():
    """Main server function."""
    # Set up event loop policy
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    # Start services
    await decoder_service.start()
    await batch_processor.start()
    await retention_manager.start()
    await alert_manager.start()
    await slo_manager.start_monitoring()
    await reprocessing_manager.start()
    await hot_reload_manager.start()
    await canary_manager.start()
    
    try:
        # Start TCP server
        server = await asyncio.start_server(
            handle_connection,
            settings.tcp_host,
            settings.tcp_port
        )
        
        addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
        logger.info("tcp_server_started", addresses=addrs)
        
        # Start serving
        async with server:
            await server.serve_forever()
            
    except KeyboardInterrupt:
        logger.info("server_shutdown_requested")
    except Exception as e:
        logger.error("server_error", error=str(e))
    finally:
        await decoder_service.stop()
        await batch_processor.stop()
        await retention_manager.stop()
        await alert_manager.stop()
        await slo_manager.stop_monitoring()
        await reprocessing_manager.stop()
        await hot_reload_manager.stop()
        await canary_manager.stop()
        logger.info("server_stopped")


if __name__ == "__main__":
    asyncio.run(main())
