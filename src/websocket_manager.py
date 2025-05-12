"""
WebSocket连接管理模块
"""
import asyncio
import logging
from typing import Dict
from fastapi import WebSocket

# 初始化日志
logger = logging.getLogger(__name__)

class ConnectionManager:
    """管理WebSocket连接的类"""
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """建立WebSocket连接"""
        await websocket.accept()
        async with self.lock:
            self.active_connections[client_id] = websocket
        logger.info(f"WebSocket client {client_id} connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, client_id: str):
        """断开WebSocket连接"""
        async with self.lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
                logger.info(f"WebSocket client {client_id} disconnected. Remaining connections: {len(self.active_connections)}")
    
    async def send_text(self, message: str, client_id: str):
        """发送文本消息到指定客户端"""
        async with self.lock:
            if client_id in self.active_connections:
                await self.active_connections[client_id].send_text(message)
    
    async def send_json(self, data: dict, client_id: str):
        """发送JSON消息到指定客户端"""
        async with self.lock:
            if client_id in self.active_connections:
                await self.active_connections[client_id].send_json(data)
    
    async def send_bytes(self, data: bytes, client_id: str):
        """发送二进制数据到指定客户端"""
        async with self.lock:
            if client_id in self.active_connections:
                await self.active_connections[client_id].send_bytes(data)
    
    async def broadcast_text(self, message: str):
        """广播文本消息到所有客户端"""
        async with self.lock:
            for connection in self.active_connections.values():
                await connection.send_text(message)
    
    async def broadcast_json(self, data: dict):
        """广播JSON消息到所有客户端"""
        async with self.lock:
            for connection in self.active_connections.values():
                await connection.send_json(data)
    
    async def close_all(self, code: int = 1000, reason: str = "Server shutdown"):
        """关闭所有连接"""
        async with self.lock:
            for client_id, connection in list(self.active_connections.items()):
                try:
                    await connection.close(code=code, reason=reason)
                    logger.info(f"Closed WebSocket connection: {client_id}")
                except Exception as e:
                    logger.error(f"Error closing WebSocket connection {client_id}: {e}")
            self.active_connections.clear()

# 创建连接管理器实例
connection_manager = ConnectionManager()