import json
import time
from collections import deque

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from bookings.models import Booking
from .models import ChatRoom, Message

MAX_MESSAGE_LENGTH = 1000
RATE_LIMIT_COUNT, RATE_LIMIT_SECONDS = 5, 5


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous:
            await self.close(code=4401)
            return

        self.room_id = int(self.scope["url_route"]["kwargs"]["room_id"])
        self.group_name = f"chat_{self.room_id}"
        self._sent = deque()

        if not await self.can_access(user.id):
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            content = str(json.loads(text_data or "{}").get("message", "")).strip()
        except (ValueError, AttributeError):
            return
        if not content:
            return
        content = content[:MAX_MESSAGE_LENGTH]

        now = time.monotonic()
        while self._sent and now - self._sent[0] > RATE_LIMIT_SECONDS:
            self._sent.popleft()
        if len(self._sent) >= RATE_LIMIT_COUNT:
            await self.send(text_data=json.dumps({"error": "You're sending messages too fast."}))
            return
        self._sent.append(now)

        user = self.scope["user"]
        saved = await self.save_message(user.id, content)
        if saved is None:
            await self.close(code=4403)
            return

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat_message", "message": content, "sender": user.username, "timestamp": saved["timestamp"]},
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "sender": event["sender"],
            "timestamp": event["timestamp"],
        }))

    def _allowed(self, user_id):
        room = ChatRoom.objects.select_related("booking__service").filter(pk=self.room_id).first()
        if room is None:
            return None
        b = room.booking
        if not b.chat_enabled or user_id not in (b.customer_id, b.service.provider_id):
            return None
        return room

    @database_sync_to_async
    def can_access(self, user_id):
        return self._allowed(user_id) is not None

    @database_sync_to_async
    def save_message(self, user_id, content):
        room = self._allowed(user_id)
        if room is None:
            return None
        msg = Message.objects.create(room=room, sender_id=user_id, content=content)
        return {"timestamp": timezone.localtime(msg.timestamp).strftime("%H:%M")}
