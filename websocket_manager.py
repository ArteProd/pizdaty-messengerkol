from fastapi import WebSocket
from typing import Dict, Set, Any
import asyncio
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}  # user_id -> websocket
        self.user_status: Dict[int, bool] = {}  # user_id -> online/offline
        self.chat_rooms: Dict[int, Set[int]] = {}  # chat_id -> set(user_ids)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        async with self._lock:
            self.active_connections[user_id] = websocket
            self.user_status[user_id] = True
            
        # Оповещаем всех о новом онлайн статусе
        await self.broadcast_status(user_id, True)

    async def disconnect(self, user_id: int):
        async with self._lock:
            # Удаляем из активных соединений
            if user_id in self.active_connections:
                del self.active_connections[user_id]
            
            # Обновляем статус
            old_status = self.user_status.get(user_id, False)
            self.user_status[user_id] = False
            
            # Если статус изменился - оповещаем
            if old_status:
                await self.broadcast_status(user_id, False)

    async def broadcast_status(self, user_id: int, is_online: bool):
        """Оповещает всех о смене статуса пользователя"""
        status_message = {
            "type": "user_status",
            "user_id": user_id,
            "is_online": is_online,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Рассылаем всем активным пользователям
        for uid, websocket in self.active_connections.items():
            try:
                await websocket.send_json(status_message)
            except:
                pass

    async def join_chat(self, user_id: int, chat_id: int):
        async with self._lock:
            if chat_id not in self.chat_rooms:
                self.chat_rooms[chat_id] = set()
            self.chat_rooms[chat_id].add(user_id)

    async def leave_chat(self, user_id: int, chat_id: int):
        async with self._lock:
            if chat_id in self.chat_rooms and user_id in self.chat_rooms[chat_id]:
                self.chat_rooms[chat_id].remove(user_id)

    async def send_personal_message(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json(message)
            except:
                await self.disconnect(user_id)

    async def broadcast_to_chat(self, message: dict, chat_id: int, exclude_user: int = None):
        if chat_id not in self.chat_rooms:
            return
        
        members = self.chat_rooms[chat_id].copy()
        
        for user_id in members:
            if user_id != exclude_user and user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].send_json(message)
                except:
                    await self.disconnect(user_id)

    def get_user_status(self, user_id: int) -> bool:
        return self.user_status.get(user_id, False)

manager = ConnectionManager()