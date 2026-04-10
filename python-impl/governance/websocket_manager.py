from __future__ import annotations

import asyncio
import json
from typing import Any
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, user_id: str):
        async with self._lock:
            if user_id in self._connections:
                try:
                    self._connections[user_id].remove(websocket)
                    if not self._connections[user_id]:
                        del self._connections[user_id]
                except ValueError:
                    pass

    async def send_to_user(self, user_id: str, message: dict[str, Any]):
        async with self._lock:
            if user_id in self._connections:
                disconnected = []
                for ws in self._connections[user_id]:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    try:
                        self._connections[user_id].remove(ws)
                    except ValueError:
                        pass

    async def broadcast(self, message: dict[str, Any]):
        async with self._lock:
            for user_id, connections in self._connections.items():
                for ws in connections:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass

    def get_connected_users(self) -> list[str]:
        return list(self._connections.keys())


notification_manager = ConnectionManager()
agent_manager = ConnectionManager()
