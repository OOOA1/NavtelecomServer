"""REST API для доступа к данным."""
import asyncio
from aiohttp import web, web_request
from aiohttp.web_response import Response
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import structlog

from .config import config
from .database import db

logger = structlog.get_logger()


class APIHandler:
    """Класс для обработки API запросов."""
    
    def __init__(self):
        """Инициализация API."""
        self.api_key = config.api.get('api_key', 'default-key')
    
    def check_auth(self, request: web_request.Request) -> bool:
        """Проверка авторизации."""
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return False
        
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            return token == self.api_key
        
        return False
    
    async def get_devices(self, request: web_request.Request) -> Response:
        """Получение списка устройств."""
        if not self.check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        
        try:
            devices = await db.get_devices()
            return web.json_response({
                'success': True,
                'data': devices,
                'count': len(devices)
            })
        except Exception as e:
            logger.error("Ошибка получения устройств", error=str(e))
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_device_positions(self, request: web_request.Request) -> Response:
        """Получение позиций устройства."""
        if not self.check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        
        try:
            unique_id = request.match_info.get('unique_id')
            if not unique_id:
                return web.json_response({'error': 'Missing unique_id'}, status=400)
            
            limit = int(request.query.get('limit', 100))
            if limit > 1000:
                limit = 1000
            
            positions = await db.get_positions(unique_id, limit)
            
            return web.json_response({
                'success': True,
                'data': positions,
                'count': len(positions),
                'device_id': unique_id
            })
        except Exception as e:
            logger.error("Ошибка получения позиций", error=str(e), unique_id=unique_id)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_last_position(self, request: web_request.Request) -> Response:
        """Получение последней позиции устройства."""
        if not self.check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        
        try:
            unique_id = request.match_info.get('unique_id')
            if not unique_id:
                return web.json_response({'error': 'Missing unique_id'}, status=400)
            
            position = await db.get_last_position(unique_id)
            
            if not position:
                return web.json_response({
                    'success': True,
                    'data': None,
                    'message': 'No position found'
                })
            
            return web.json_response({
                'success': True,
                'data': position
            })
        except Exception as e:
            logger.error("Ошибка получения последней позиции", error=str(e), unique_id=unique_id)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_can_data(self, request: web_request.Request) -> Response:
        """Получение CAN данных устройства."""
        if not self.check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        
        try:
            unique_id = request.match_info.get('unique_id')
            if not unique_id:
                return web.json_response({'error': 'Missing unique_id'}, status=400)
            
            # Получение CAN данных из базы
            async with db.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT c.*, p.latitude, p.longitude, p.fix_time as position_time
                    FROM can_data c
                    LEFT JOIN positions p ON c.position_id = p.id
                    WHERE c.unique_id = $1
                    ORDER BY c.received_at DESC
                    LIMIT 100
                    """,
                    unique_id
                )
            
            can_data = [dict(row) for row in rows]
            
            return web.json_response({
                'success': True,
                'data': can_data,
                'count': len(can_data),
                'device_id': unique_id
            })
        except Exception as e:
            logger.error("Ошибка получения CAN данных", error=str(e), unique_id=unique_id)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_raw_frames(self, request: web_request.Request) -> Response:
        """Получение сырых кадров устройства."""
        if not self.check_auth(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        
        try:
            unique_id = request.match_info.get('unique_id')
            if not unique_id:
                return web.json_response({'error': 'Missing unique_id'}, status=400)
            
            frame_type = request.query.get('type')  # A, T, X, E
            limit = int(request.query.get('limit', 100))
            if limit > 1000:
                limit = 1000
            
            # Получение сырых кадров
            async with db.pool.acquire() as conn:
                if frame_type:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM raw_frames
                        WHERE unique_id = $1 AND frame_type = $2
                        ORDER BY received_at DESC
                        LIMIT $3
                        """,
                        unique_id, frame_type, limit
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM raw_frames
                        WHERE unique_id = $1
                        ORDER BY received_at DESC
                        LIMIT $2
                        """,
                        unique_id, limit
                    )
            
            frames = [dict(row) for row in rows]
            
            return web.json_response({
                'success': True,
                'data': frames,
                'count': len(frames),
                'device_id': unique_id,
                'frame_type': frame_type
            })
        except Exception as e:
            logger.error("Ошибка получения сырых кадров", error=str(e), unique_id=unique_id)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def health_check(self, request: web_request.Request) -> Response:
        """Проверка состояния сервера."""
        try:
            # Проверка подключения к БД
            async with db.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            return web.json_response({
                'status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'database': 'connected'
            })
        except Exception as e:
            logger.error("Ошибка проверки здоровья", error=str(e))
            return web.json_response({
                'status': 'unhealthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }, status=503)


def create_app() -> web.Application:
    """Создание веб-приложения."""
    handler = APIHandler()
    
    app = web.Application()
    
    # Маршруты API
    app.router.add_get('/api/devices', handler.get_devices)
    app.router.add_get('/api/devices/{unique_id}/positions', handler.get_device_positions)
    app.router.add_get('/api/devices/{unique_id}/last', handler.get_last_position)
    app.router.add_get('/api/devices/{unique_id}/can', handler.get_can_data)
    app.router.add_get('/api/devices/{unique_id}/frames', handler.get_raw_frames)
    app.router.add_get('/api/health', handler.health_check)
    
    # CORS middleware
    async def cors_handler(request, handler):
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    app.middlewares.append(cors_handler)
    
    return app


async def start_api_server():
    """Запуск API сервера."""
    app = create_app()
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(
        runner,
        config.api['host'],
        config.api['port']
    )
    
    await site.start()
    
    logger.info(
        "API сервер запущен",
        host=config.api['host'],
        port=config.api['port']
    )
    
    return runner

