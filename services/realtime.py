import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.urls import reverse

logger = logging.getLogger(__name__)


def broadcast_slot(slot):
    try:
        async_to_sync(get_channel_layer().group_send)(
            f"availability_{slot.service_id}",
            {
                "type": "slot_update",
                "slot_id": slot.id,
                "is_booked": slot.is_booked,
                "label": slot.label,
                "sort_key": slot.sort_key,
                "book_url": reverse("bookings:create_booking", args=[slot.id]),
            },
        )
    except Exception:
        logger.exception("Could not broadcast slot update for slot %s", slot.id)
