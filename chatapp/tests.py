import datetime

from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking
from services.models import Service, Slot
from .consumers import ChatConsumer
from .models import ChatRoom, Message


class ChatAccessTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "o@x.com", "pw12345678", role="PROVIDER")
        self.tenant = User.objects.create_user("tenant", "t@x.com", "pw12345678", role="CUSTOMER")
        self.stranger = User.objects.create_user("stranger", "s@x.com", "pw12345678", role="CUSTOMER")
        room = Service.objects.create(provider=self.owner, title="R", description="d", price=5000)
        slot = Slot.objects.create(service=room, date=timezone.localdate() + datetime.timedelta(days=2),
                                   start_time=datetime.time(10), end_time=datetime.time(11), is_booked=True)
        self.booking = Booking.objects.create(customer=self.tenant, service=room, slot=slot,
                                              status="CONFIRMED", total_price=300)
        self.room = ChatRoom.objects.create(booking=self.booking)

    def comm(self, user):
        c = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.room.pk}/")
        c.scope["user"] = user
        c.scope["url_route"] = {"kwargs": {"room_id": str(self.room.pk)}}
        return c

    async def test_stranger_and_anonymous_are_rejected(self):
        for user in (self.stranger, AnonymousUser()):
            c = self.comm(user)
            connected, _ = await c.connect()
            self.assertFalse(connected)

    async def test_participants_can_chat_and_see_each_other(self):
        a, b = self.comm(self.tenant), self.comm(self.owner)
        self.assertTrue((await a.connect())[0])
        self.assertTrue((await b.connect())[0])
        await a.send_json_to({"message": "hello"})
        got = await b.receive_json_from()
        self.assertEqual((got["sender"], got["message"]), ("tenant", "hello"))
        await a.disconnect(); await b.disconnect()
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 1)

    async def test_unconfirmed_booking_chat_rejected(self):
        await database_sync_to_async(Booking.objects.filter(pk=self.booking.pk).update)(status="PENDING")
        connected, _ = await self.comm(self.tenant).connect()
        self.assertFalse(connected)

    async def test_rate_limit_and_length_cap(self):
        c = self.comm(self.tenant)
        await c.connect()
        await c.send_json_to({"message": "x" * 5000})
        first = await c.receive_json_from()
        self.assertEqual(len(first["message"]), 1000)
        for _ in range(5):
            await c.send_json_to({"message": "spam"})
        seen_error = False
        while not await c.receive_nothing(timeout=0.2):
            if "error" in await c.receive_json_from():
                seen_error = True
        self.assertTrue(seen_error)
        await c.disconnect()

    def test_chat_page_needs_confirmed_booking_and_participant(self):
        url = reverse("chatapp:room", args=[self.booking.pk])
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(url).status_code, 200)
        Booking.objects.filter(pk=self.booking.pk).update(status="PENDING")
        self.assertEqual(self.client.get(url).status_code, 302)
