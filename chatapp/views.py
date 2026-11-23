from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from bookings.models import Booking
from django.db.models import Q
from .models import ChatRoom, Message


@login_required
def chat_room(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related("service", "customer"), pk=booking_id)
    if request.user not in (booking.customer, booking.service.provider):
        return render(request, "chat/forbidden.html", status=403)
    if not booking.chat_enabled:
        messages.info(request, "Chat is available for confirmed bookings and room requests in progress.")
        return redirect("bookings:my_bookings" if request.user.is_customer else "bookings:provider_bookings")

    room, _ = ChatRoom.objects.get_or_create(booking=booking)
    recent = list(room.messages.select_related("sender").order_by("-timestamp")[:200])[::-1]
    other = booking.service.provider if request.user == booking.customer else booking.customer
    return render(request, "chat/room.html", {
        "booking": booking, "room": room, "messages_qs": recent, "other_user": other,
    })


@login_required
def inbox(request):
    bookings = list(
        Booking.objects.filter(Q(customer=request.user) | Q(service__provider=request.user))
        .select_related("service", "customer", "service__provider").order_by("-created_at")[:60]
    )
    rows = []
    for b in bookings:
        if not b.chat_enabled:
            continue
        last = Message.objects.filter(room__booking=b).select_related("sender").order_by("-timestamp").first()
        other = b.service.provider if request.user == b.customer else b.customer
        rows.append({"booking": b, "other": other, "last": last, "sort": last.timestamp if last else b.created_at})
    rows.sort(key=lambda r: r["sort"], reverse=True)
    return render(request, "chat/inbox.html", {"rows": rows})
