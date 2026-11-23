import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AvailabilityConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.service_id = self.scope["url_route"]["kwargs"]["service_id"]
        self.group_name = f"availability_{self.service_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def slot_update(self, event):
        await self.send(text_data=json.dumps({
            "slot_id": event["slot_id"],
            "is_booked": event["is_booked"],
            "label": event.get("label", ""),
            "sort_key": event.get("sort_key", ""),
            "book_url": event.get("book_url", ""),
        }))
