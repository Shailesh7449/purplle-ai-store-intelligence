"""WebSocket: tail the Redis Stream and push live events to the dashboard."""
from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    """Live event WebSocket. Gracefully handles Redis unavailability."""
    await ws.accept()
    s = get_settings()
    r = None
    
    try:
        # Try to connect to Redis with timeout
        r = aioredis.Redis(
            host=s.redis_host, 
            port=s.redis_port, 
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        
        # Test connection
        await asyncio.wait_for(r.ping(), timeout=3)
        logger.info("[ws] connected to Redis")
        
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"[ws] Redis unavailable: {e}")
        # Send degraded mode message and keep connection alive
        await ws.send_text(json.dumps({
            "type": "degraded",
            "message": "Live events unavailable (Redis not connected)",
        }))
        # Continue in degraded mode: send heartbeats only
        try:
            while True:
                await asyncio.sleep(5)
                await ws.send_text(json.dumps({"type": "heartbeat"}))
        except WebSocketDisconnect:
            pass
        finally:
            return
    
    # Normal operation: stream events from Redis
    last_id = "$"
    try:
        while True:
            try:
                resp = await asyncio.wait_for(
                    r.xread({s.redis_stream: last_id}, count=50, block=2000),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                # Just send heartbeat on read timeout
                await ws.send_text(json.dumps({"type": "heartbeat"}))
                continue
            except Exception as e:
                logger.warning(f"[ws] Redis read error: {e}")
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": "Lost connection to event stream",
                }))
                break
            
            if not resp:
                await ws.send_text(json.dumps({"type": "heartbeat"}))
                continue
                
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    last_id = msg_id
                    await ws.send_text(fields.get("data", "{}"))
                    
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        if r:
            await r.aclose()
