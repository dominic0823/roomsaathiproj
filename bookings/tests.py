import datetime
import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from payments.models import Payment
from services.models import Service, Slot
from .models import Booking
from .services import expire_stale_pending


class BookingBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "o@x.com", "pw12345678", role="PROVIDER", phone_verified=True)
        self.tenant = User.objects.create_user("tenant", "t@x.com", "pw12345678", role="CUSTOMER", phone_verified=True)
        self.tenant2 = User.objects.create_user("tenant2", "t2@x.com", "pw12345678", role="CUSTOMER", phone_verified=True)
        self.room = Service.objects.create(provider=self.owner, title="R", description="d", price=6000, booking_amount=300)
        day = timezone.localdate() + datetime.timedelta(days=2)
        self.slot = Slot.objects.create(service=self.room, date=day, start_time=datetime.time(10), end_time=datetime.time(11))

    def book(self, user=None, slot=None):
        self.client.force_login(user or self.tenant)
        return self.client.post(reverse("bookings:create_booking", args=[(slot or self.slot).pk]))


class BookingFlowTests(BookingBase):
    def test_booking_requires_post(self):
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(reverse("bookings:create_booking", args=[self.slot.pk])).status_code, 405)

    def test_book_sets_pending_and_amount_is_token_not_rent(self):
        resp = self.book()
        b = Booking.objects.get()
        self.assertRedirects(resp, reverse("payments:checkout", args=[b.pk]), fetch_redirect_response=False)
        self.assertEqual(b.status, "PENDING")
        self.assertEqual(b.total_price, 300)
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)

    def test_second_tenant_cannot_take_booked_slot(self):
        self.book()
        self.book(self.tenant2)
        self.assertEqual(Booking.objects.count(), 1)

    def test_owner_cannot_book(self):
        self.book(self.owner)
        self.assertEqual(Booking.objects.count(), 0)

    def test_free_room_confirms_immediately(self):
        self.room.booking_amount = 0
        self.room.save()
        self.book()
        self.assertEqual(Booking.objects.get().status, "CONFIRMED")

    def test_cancel_frees_slot_and_slot_can_be_rebooked(self):
        self.book()
        b = Booking.objects.get()
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(reverse("bookings:cancel_booking", args=[b.pk])).status_code, 405)
        self.client.post(reverse("bookings:cancel_booking", args=[b.pk]))
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_booked)
        self.book(self.tenant2)
        self.assertEqual(Booking.objects.exclude(status="CANCELLED").count(), 1)
        self.assertEqual(Booking.objects.count(), 2)

    def test_only_booking_owner_can_cancel(self):
        self.book()
        b = Booking.objects.get()
        self.client.force_login(self.tenant2)
        self.assertEqual(self.client.post(reverse("bookings:cancel_booking", args=[b.pk])).status_code, 404)

    def test_pending_expires_and_releases_slot(self):
        self.book()
        Booking.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=30))
        self.assertEqual(expire_stale_pending(), 1)
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_booked)
        self.assertEqual(Booking.objects.get().status, "CANCELLED")

    def test_past_slot_cannot_be_booked(self):
        Slot.objects.filter(pk=self.slot.pk).update(date=timezone.localdate() - datetime.timedelta(days=1))
        self.book()
        self.assertEqual(Booking.objects.count(), 0)

    def test_pending_limit(self):
        for h in range(11, 15):
            Slot.objects.create(service=self.room, date=self.slot.date, start_time=datetime.time(h), end_time=datetime.time(h + 1))
        for slot in Slot.objects.all():
            self.book(slot=slot)
        self.assertEqual(Booking.objects.count(), 3)

    def test_emails_go_to_tenant_and_owner(self):
        from django.core import mail
        with self.captureOnCommitCallbacks(execute=True):
            self.book()
        recipients = {m.to[0] for m in mail.outbox}
        self.assertEqual(recipients, {"t@x.com", "o@x.com"})


@override_settings(RAZORPAY_WEBHOOK_SECRET="whsec")
class PaymentSecurityTests(BookingBase):
    def setUp(self):
        super().setUp()
        self.book()
        self.booking = Booking.objects.get()
        self.payment = Payment.objects.create(booking=self.booking, razorpay_order_id="order_A", amount=300)

    def post_verify(self, order_id="order_A"):
        self.client.force_login(self.tenant)
        return self.client.post(reverse("payments:verify", args=[self.booking.pk]), {
            "razorpay_order_id": order_id, "razorpay_payment_id": "pay_1", "razorpay_signature": "sig"})

    @mock.patch("payments.views.get_razorpay_client")
    def test_valid_payment_confirms(self, client):
        self.post_verify()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "CONFIRMED")
        self.assertEqual(Payment.objects.get().status, "PAID")

    @mock.patch("payments.views.get_razorpay_client")
    def test_order_id_of_another_booking_is_rejected(self, client):
        self.post_verify(order_id="order_CHEAP")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "PENDING")
        client.return_value.utility.verify_payment_signature.assert_not_called()

    @mock.patch("payments.views.get_razorpay_client")
    def test_bad_signature_does_not_confirm(self, client):
        import razorpay
        client.return_value.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError("bad")
        self.post_verify()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "PENDING")
        self.assertEqual(Payment.objects.get().status, "FAILED")

    def test_verify_requires_post(self):
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(reverse("payments:verify", args=[self.booking.pk])).status_code, 405)

    @mock.patch("payments.views.get_razorpay_client")
    def test_webhook_confirms_when_signature_valid(self, client):
        body = json.dumps({"event": "payment.captured",
                           "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_A"}}}})
        resp = self.client.post(reverse("payments:webhook"), body, content_type="application/json",
                                HTTP_X_RAZORPAY_SIGNATURE="whatever")
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "CONFIRMED")

    @mock.patch("payments.views.get_razorpay_client")
    def test_webhook_rejects_bad_signature_or_missing_secret(self, client):
        import razorpay
        client.return_value.utility.verify_webhook_signature.side_effect = razorpay.errors.SignatureVerificationError("x")
        resp = self.client.post(reverse("payments:webhook"), "{}", content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="s")
        self.assertEqual(resp.status_code, 400)
        with override_settings(RAZORPAY_WEBHOOK_SECRET=""):
            resp = self.client.post(reverse("payments:webhook"), "{}", content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="s")
            self.assertEqual(resp.status_code, 400)

    @mock.patch("payments.utils.get_razorpay_client")
    def test_late_payment_after_expiry_is_refunded_not_confirmed(self, client):
        client.return_value.payment.refund.return_value = {"id": "rfnd_1"}
        Booking.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=30))
        expire_stale_pending()
        from payments.services import mark_paid
        mark_paid("order_A", "pay_late")
        self.assertEqual(Payment.objects.get().status, "REFUNDED")
        self.assertEqual(Booking.objects.get().status, "CANCELLED")

    @mock.patch("payments.utils.get_razorpay_client")
    def test_cancel_confirmed_booking_refunds(self, client):
        client.return_value.payment.refund.return_value = {"id": "rfnd_2"}
        Booking.objects.update(status="CONFIRMED")
        Payment.objects.update(status="PAID", razorpay_payment_id="pay_1")
        self.client.force_login(self.tenant)
        self.client.post(reverse("bookings:cancel_booking", args=[self.booking.pk]))
        p = Payment.objects.get()
        self.assertEqual(p.status, "REFUNDED")
        self.assertEqual(p.razorpay_refund_id, "rfnd_2")


class RentalBase(BookingBase):
    def setUp(self):
        super().setUp()
        self.room.advance_amount = 2000
        self.room.deposit_amount = 6000
        self.room.total_beds = 1
        self.room.min_stay_months = 2
        self.room.save()
        self.move_in = timezone.localdate() + datetime.timedelta(days=10)

    def rent(self, user=None, months=3, move_in=None, service=None):
        self.client.force_login(user or self.tenant)
        return self.client.post(reverse("bookings:rent_room", args=[(service or self.room).pk]), {
            "move_in_date": (move_in or self.move_in).isoformat(), "stay_months": months, "note": "student"})

    def approve(self, booking):
        self.client.force_login(self.owner)
        return self.client.post(reverse("bookings:approve_booking", args=[booking.pk]), {"note": "welcome"})


class RentalRequestTests(RentalBase):
    def test_request_creates_requested_booking_with_snapshots(self):
        self.rent()
        b = Booking.objects.get()
        self.assertEqual((b.kind, b.status), ("RENTAL", "REQUESTED"))
        self.assertEqual(b.total_price, 2000)
        self.assertEqual((b.monthly_rent, b.deposit_amount), (6000, 6000))
        self.assertGreater(b.stay_end_date, self.move_in)
        self.assertIsNone(b.slot)
        self.assertEqual(b.customer, self.tenant)

    def test_validation_min_stay_past_date_and_too_far(self):
        self.rent(months=1)
        self.rent(move_in=timezone.localdate() - datetime.timedelta(days=1))
        self.rent(move_in=timezone.localdate() + datetime.timedelta(days=400))
        self.rent(months=60)
        self.assertEqual(Booking.objects.count(), 0)

    def test_get_not_allowed_and_unverified_phone_blocked(self):
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(reverse("bookings:rent_room", args=[self.room.pk])).status_code, 405)
        self.tenant.phone_verified = False
        self.tenant.save()
        resp = self.rent()
        self.assertEqual(Booking.objects.count(), 0)
        self.assertIn("/accounts/verify/phone/", resp.url)

    def test_owner_cannot_rent_and_no_duplicate_requests(self):
        self.rent(user=self.owner)
        self.assertEqual(Booking.objects.count(), 0)
        self.rent()
        self.rent()
        self.assertEqual(Booking.objects.count(), 1)

    def test_owner_and_tenant_are_notified(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.rent()
        from accounts.models import Notification
        self.assertTrue(Notification.objects.filter(user=self.owner, message__startswith="New room request").exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant, message__startswith="Request sent").exists())


class RentalApprovalTests(RentalBase):
    def test_full_happy_path_request_approve_pay_confirm(self):
        self.rent()
        b = Booking.objects.get()
        self.approve(b)
        b.refresh_from_db()
        self.assertEqual(b.status, "PENDING")
        self.assertIsNotNone(b.approved_at)

        Payment.objects.create(booking=b, razorpay_order_id="order_R", amount=2000)
        self.client.force_login(self.tenant)
        with mock.patch("payments.views.get_razorpay_client"):
            self.client.post(reverse("payments:verify", args=[b.pk]), {
                "razorpay_order_id": "order_R", "razorpay_payment_id": "pay_R", "razorpay_signature": "s"})
        b.refresh_from_db()
        self.assertEqual(b.status, "CONFIRMED")
        self.assertTrue(self.room.is_full)
        self.assertEqual(self.client.get(reverse("bookings:receipt", args=[b.pk])).status_code, 200)

    def test_only_the_rooms_owner_can_approve_or_decline(self):
        self.rent()
        b = Booking.objects.get()
        other = User.objects.create_user("o2", "o2@x.com", "pw12345678", role="PROVIDER", phone_verified=True)
        self.client.force_login(other)
        for name in ("approve_booking", "decline_booking"):
            self.assertEqual(self.client.post(reverse(f"bookings:{name}", args=[b.pk])).status_code, 404)
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.post(reverse("bookings:approve_booking", args=[b.pk])).status_code, 404)

    def test_cannot_overbook_the_last_bed(self):
        self.rent()
        self.rent(user=self.tenant2)
        first, second = Booking.objects.order_by("id")
        self.approve(first)
        self.approve(second)
        second.refresh_from_db()
        self.assertEqual(second.status, "REQUESTED")

    def test_non_overlapping_dates_can_both_be_booked(self):
        self.rent(months=2)
        first = Booking.objects.get()
        self.approve(first)
        later = first.stay_end_date + datetime.timedelta(days=1)
        self.rent(user=self.tenant2, move_in=later, months=2) if later <= timezone.localdate() + datetime.timedelta(days=120) else None
        if Booking.objects.count() == 2:
            second = Booking.objects.order_by("-id").first()
            self.approve(second)
            second.refresh_from_db()
            self.assertEqual(second.status, "PENDING")

    def test_full_room_rejects_new_requests_for_overlapping_dates(self):
        self.rent()
        self.approve(Booking.objects.get())
        self.rent(user=self.tenant2)
        self.assertEqual(Booking.objects.count(), 1)

    def test_decline(self):
        self.rent()
        b = Booking.objects.get()
        self.client.force_login(self.owner)
        self.client.post(reverse("bookings:decline_booking", args=[b.pk]), {"note": "sorry"})
        b.refresh_from_db()
        self.assertEqual((b.status, b.owner_note), ("DECLINED", "sorry"))
        self.assertFalse(self.room.is_full)
        self.rent()
        self.assertEqual(Booking.objects.count(), 2)

    def test_zero_advance_confirms_on_approval(self):
        self.room.advance_amount = 0
        self.room.save()
        self.rent()
        b = Booking.objects.get()
        self.approve(b)
        b.refresh_from_db()
        self.assertEqual(b.status, "CONFIRMED")

    def test_cannot_approve_twice(self):
        self.rent()
        b = Booking.objects.get()
        self.approve(b)
        resp = self.approve(b)
        b.refresh_from_db()
        self.assertEqual(b.status, "PENDING")


class RentalLifecycleTests(RentalBase):
    def make_confirmed(self, move_in=None):
        self.rent(move_in=move_in)
        b = Booking.objects.get()
        self.approve(b)
        Payment.objects.create(booking=b, razorpay_order_id="order_R", amount=2000, status="PAID", razorpay_payment_id="pay_R")
        Booking.objects.filter(pk=b.pk).update(status="CONFIRMED")
        b.refresh_from_db()
        return b

    @mock.patch("payments.utils.get_razorpay_client")
    def test_tenant_cancel_well_before_move_in_is_refunded(self, client):
        client.return_value.payment.refund.return_value = {"id": "rfnd_1"}
        b = self.make_confirmed()
        self.client.force_login(self.tenant)
        self.client.post(reverse("bookings:cancel_booking", args=[b.pk]))
        self.assertEqual(Payment.objects.get().status, "REFUNDED")
        self.assertFalse(self.room.is_full)

    @mock.patch("payments.utils.get_razorpay_client")
    def test_tenant_cancel_last_minute_is_not_refunded(self, client):
        b = self.make_confirmed(move_in=timezone.localdate() + datetime.timedelta(days=1))
        self.client.force_login(self.tenant)
        self.client.post(reverse("bookings:cancel_booking", args=[b.pk]))
        b.refresh_from_db()
        self.assertEqual(b.status, "CANCELLED")
        self.assertEqual(Payment.objects.get().status, "PAID")
        client.return_value.payment.refund.assert_not_called()

    @mock.patch("payments.utils.get_razorpay_client")
    def test_owner_cancel_always_refunds_in_full(self, client):
        client.return_value.payment.refund.return_value = {"id": "rfnd_2"}
        b = self.make_confirmed(move_in=timezone.localdate() + datetime.timedelta(days=1))
        self.client.force_login(self.owner)
        self.client.post(reverse("bookings:owner_cancel_booking", args=[b.pk]))
        self.assertEqual(Payment.objects.get().status, "REFUNDED")
        self.assertEqual(Booking.objects.get().status, "CANCELLED")

    def test_unanswered_request_expires(self):
        self.rent()
        Booking.objects.update(created_at=timezone.now() - datetime.timedelta(hours=49))
        self.assertEqual(expire_stale_pending(), 1)
        self.assertEqual(Booking.objects.get().status, "CANCELLED")

    def test_unpaid_approved_request_expires_and_frees_the_bed(self):
        self.rent()
        b = Booking.objects.get()
        self.approve(b)
        self.assertTrue(self.room.is_full)
        Booking.objects.update(approved_at=timezone.now() - datetime.timedelta(hours=25))
        self.assertEqual(expire_stale_pending(), 1)
        self.assertFalse(self.room.is_full)

    def test_fresh_requests_do_not_expire(self):
        self.rent()
        self.assertEqual(expire_stale_pending(), 0)

    def test_review_only_after_move_in(self):
        b = self.make_confirmed()
        self.assertFalse(b.can_review)
        self.client.force_login(self.tenant)
        self.client.get(reverse("bookings:leave_review", args=[b.pk]))
        Booking.objects.filter(pk=b.pk).update(move_in_date=timezone.localdate() - datetime.timedelta(days=1))
        b.refresh_from_db()
        self.assertTrue(b.can_review)
        resp = self.client.post(reverse("bookings:leave_review", args=[b.pk]), {"rating": 5, "comment": "great"})
        self.assertEqual(self.room.reviews.count(), 1)

    def test_visit_review_only_after_slot_time(self):
        self.book()
        b = Booking.objects.get()
        Booking.objects.filter(pk=b.pk).update(status="CONFIRMED")
        b.refresh_from_db()
        self.assertFalse(b.can_review)

    def test_receipt_only_for_participants(self):
        b = self.make_confirmed()
        stranger = User.objects.create_user("st", "s@x.com", "pw12345678", phone_verified=True)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("bookings:receipt", args=[b.pk])).status_code, 403)

    def test_chat_open_while_request_is_pending_but_not_after_decline(self):
        self.rent()
        b = Booking.objects.get()
        self.assertTrue(b.chat_enabled)
        self.client.force_login(self.owner)
        self.client.post(reverse("bookings:decline_booking", args=[b.pk]))
        b.refresh_from_db()
        self.assertFalse(b.chat_enabled)

    def test_provider_page_lists_requests_needing_action(self):
        self.rent()
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("bookings:provider_bookings"))
        self.assertEqual(len(resp.context["needs_action"]), 1)
        self.assertContains(resp, "Approve")

    def test_detail_page_shows_both_booking_options(self):
        self.client.force_login(self.tenant)
        resp = self.client.get(reverse("services:detail", args=[self.room.pk]))
        self.assertContains(resp, "Book this room")
        self.assertContains(resp, "Schedule a visit")
        self.assertContains(resp, "What's a visit slot?")


class CalendarAndInboxTests(RentalBase):
    def confirmed_visit(self):
        self.book()
        Booking.objects.update(status="CONFIRMED")
        return Booking.objects.get()

    def test_ics_for_confirmed_visit(self):
        b = self.confirmed_visit()
        self.client.force_login(self.tenant)
        resp = self.client.get(reverse("bookings:calendar_ics", args=[b.pk]))
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/calendar")
        body = resp.content.decode()
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn("SUMMARY:Room visit: R", body)
        self.assertIn("DTSTART:", body)

    def test_ics_for_rental_is_all_day_and_blocked_for_strangers(self):
        self.rent()
        b = Booking.objects.get()
        Booking.objects.filter(pk=b.pk).update(status="CONFIRMED")
        self.client.force_login(self.tenant)
        self.assertIn("DTSTART;VALUE=DATE:", self.client.get(reverse("bookings:calendar_ics", args=[b.pk])).content.decode())
        self.client.force_login(self.tenant2)
        self.assertEqual(self.client.get(reverse("bookings:calendar_ics", args=[b.pk])).status_code, 302)

    def test_inbox_lists_conversations_for_both_sides(self):
        self.rent()
        for user in (self.tenant, self.owner):
            self.client.force_login(user)
            resp = self.client.get(reverse("chatapp:inbox"))
            self.assertEqual(len(resp.context["rows"]), 1)
        self.client.force_login(self.tenant2)
        self.assertEqual(len(self.client.get(reverse("chatapp:inbox")).context["rows"]), 0)

    def test_approval_records_response_time(self):
        self.rent()
        b = Booking.objects.get()
        self.approve(b)
        b.refresh_from_db()
        self.assertIsNotNone(b.approved_at)


class ErrorPageTests(TestCase):
    def test_404_is_branded(self):
        resp = self.client.get("/definitely/not/here/")
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "couldn't find that page", status_code=404)


@override_settings(PAYMENT_MODE="demo")
class DemoGatewayTests(RentalBase):
    def start_visit_checkout(self):
        self.book()
        b = Booking.objects.get()
        self.client.force_login(self.tenant)
        resp = self.client.get(reverse("payments:checkout", args=[b.pk]))
        return b, resp

    def pay(self, b, **data):
        base = {"method": "upi", "upi": "riya@okaxis"}
        base.update(data)
        return self.client.post(reverse("payments:demo_pay", args=[b.pk]), base)

    def test_checkout_page_is_the_demo_gateway_and_makes_a_demo_order(self):
        b, resp = self.start_visit_checkout()
        self.assertContains(resp, "RoomSaathi Pay")
        self.assertContains(resp, "Use test card")
        self.assertTrue(Payment.objects.get().razorpay_order_id.startswith("order_demo_"))

    def test_upi_payment_confirms_booking_and_records_method(self):
        b, _ = self.start_visit_checkout()
        resp = self.pay(b)
        self.assertRedirects(resp, reverse("payments:success", args=[b.pk]), fetch_redirect_response=False)
        b.refresh_from_db()
        p = Payment.objects.get()
        self.assertEqual((b.status, p.status), ("CONFIRMED", "PAID"))
        self.assertEqual(p.method, "UPI (riya@okaxis)")
        self.assertTrue(p.razorpay_payment_id.startswith("pay_demo_"))
        page = self.client.get(reverse("payments:success", args=[b.pk]))
        self.assertContains(page, "pay_demo_")

    def test_valid_card_netbanking_and_wallet(self):
        for i, data in enumerate([
            {"method": "card", "card_number": "4111 1111 1111 1111", "expiry": "12/40", "cvv": "123", "card_name": "A B"},
            {"method": "netbanking", "bank": "HDFC Bank"},
            {"method": "wallet", "wallet": "Paytm"},
        ]):
            Booking.objects.all().delete(); Payment.objects.all().delete()
            Slot.objects.update(is_booked=False)
            b, _ = self.start_visit_checkout()
            self.pay(b, **data)
            b.refresh_from_db()
            self.assertEqual(b.status, "CONFIRMED", data["method"])
        self.assertEqual(Payment.objects.get().method, "Wallet (Paytm)")

    def test_card_validation_rejects_bad_numbers_expired_cards_and_missing_fields(self):
        b, _ = self.start_visit_checkout()
        good = {"method": "card", "card_number": "4111111111111111", "expiry": "12/40", "cvv": "123", "card_name": "A"}
        for bad in ({"card_number": "4111 1111 1111 1112"}, {"expiry": "01/20"}, {"expiry": "13/40"},
                    {"cvv": "1"}, {"card_name": ""}, {"card_number": "abcd"}):
            self.pay(b, **{**good, **bad})
            b.refresh_from_db()
            self.assertEqual(b.status, "PENDING", bad)

    def test_bad_upi_and_unknown_bank_rejected(self):
        b, _ = self.start_visit_checkout()
        self.pay(b, upi="not-an-upi")
        self.pay(b, method="netbanking", bank="Fake Bank")
        self.pay(b, method="nonsense")
        b.refresh_from_db()
        self.assertEqual(b.status, "PENDING")

    def test_simulated_failure_then_successful_retry(self):
        b, _ = self.start_visit_checkout()
        resp = self.pay(b, simulate_fail="1")
        self.assertRedirects(resp, reverse("payments:failed", args=[b.pk]), fetch_redirect_response=False)
        b.refresh_from_db()
        self.assertEqual((b.status, Payment.objects.get().status), ("PENDING", "FAILED"))
        self.assertContains(self.client.get(reverse("payments:checkout", args=[b.pk])), "last payment attempt failed")
        self.pay(b)
        b.refresh_from_db()
        self.assertEqual((b.status, Payment.objects.get().status), ("CONFIRMED", "PAID"))

    def test_other_users_cannot_pay_and_double_payment_is_ignored(self):
        b, _ = self.start_visit_checkout()
        self.client.force_login(self.tenant2)
        self.assertEqual(self.pay(b).status_code, 404)
        self.client.force_login(self.tenant)
        self.pay(b)
        self.pay(b)
        self.assertEqual(Payment.objects.filter(status="PAID").count(), 1)

    def test_expired_hold_cannot_be_paid(self):
        b, _ = self.start_visit_checkout()
        Booking.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=30))
        self.pay(b)
        b.refresh_from_db()
        self.assertEqual(b.status, "CANCELLED")

    def test_demo_refund_on_cancel(self):
        b, _ = self.start_visit_checkout()
        self.pay(b)
        self.client.post(reverse("bookings:cancel_booking", args=[b.pk]))
        p = Payment.objects.get()
        self.assertEqual(p.status, "REFUNDED")
        self.assertTrue(p.razorpay_refund_id.startswith("rfnd_demo_"))

    def test_full_room_booking_flow_in_demo_mode(self):
        self.rent()
        b = Booking.objects.get()
        self.approve(b)
        self.client.force_login(self.tenant)
        self.assertContains(self.client.get(reverse("payments:checkout", args=[b.pk])), "Room booking advance")
        self.pay(b, method="card", card_number="4242424242424242", expiry="11/39", cvv="999", card_name="T")
        b.refresh_from_db()
        self.assertEqual(b.status, "CONFIRMED")
        self.assertTrue(self.room.is_full)

    @override_settings(PAYMENT_MODE="razorpay")
    def test_demo_endpoint_is_closed_in_razorpay_mode(self):
        self.book()
        b = Booking.objects.get()
        Payment.objects.create(booking=b, razorpay_order_id="order_x", amount=300)
        self.client.force_login(self.tenant)
        self.assertEqual(self.pay(b).status_code, 404)

    def test_payment_history_for_tenant_and_owner(self):
        b, _ = self.start_visit_checkout()
        self.pay(b)
        resp = self.client.get(reverse("payments:history"))
        self.assertContains(resp, "My payments")
        self.assertEqual(resp.context["paid"], 300)
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("payments:history"))
        self.assertContains(resp, "Payments received")
        self.assertEqual(resp.context["paid"], 300)
        self.client.force_login(self.tenant2)
        self.assertEqual(self.client.get(reverse("payments:history")).context["paid"], 0)


class DemoOtpCardTests(TestCase):
    def setUp(self):
        from accounts.models import User as U
        self.user = U.objects.create_user("d", "d@x.com", "pw12345678", phone_number="+919876543210")
        self.client.force_login(self.user)
        self.url = reverse("accounts:verify", args=["phone"])

    @override_settings(OTP_DEV_ECHO=True)
    def test_random_code_is_shown_on_screen_and_works(self):
        import re
        self.client.post(self.url, {"action": "send", "via": "sms"})
        html = self.client.get(self.url).content.decode()
        code = re.search(r'class="demo-otp">.*?<b>(\d{6})</b>', html, re.S).group(1)
        self.assertIn('id="demo-fill"', html)
        self.client.post(self.url, {"action": "verify", "code": code})
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)
        self.assertNotIn("demo_otp", self.client.session)

    @override_settings(OTP_DEV_ECHO=True)
    def test_each_request_makes_a_different_random_code(self):
        from accounts.models import OTPCode
        codes = set()
        for _ in range(4):
            self.client.post(self.url, {"action": "send", "via": "sms"})
            codes.add(self.client.session["demo_otp"])
            OTPCode.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=2))
        self.assertGreater(len(codes), 1)

    @override_settings(OTP_DEV_ECHO=False)
    def test_code_is_not_shown_when_echo_is_off(self):
        self.client.post(self.url, {"action": "send", "via": "sms"})
        self.assertNotIn("demo_otp", self.client.session)
        self.assertNotContains(self.client.get(self.url), "Demo OTP")


class DemoModeSettingsTests(TestCase):
    def run_settings(self, env):
        import os, subprocess, sys
        code = ("import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; "
                "from django.conf import settings; "
                "print(settings.DEMO_MODE, settings.PAYMENT_MODE, settings.OTP_PROVIDER, settings.OTP_SMS_BACKEND, settings.OTP_WHATSAPP_BACKEND, settings.OTP_DEV_ECHO, settings.REQUIRE_PHONE_VERIFICATION)")
        full = {**os.environ, **env}
        full.pop("DATABASE_URL", None)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=full, cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent))
        return out.stdout.strip().split("\n")[-1]

    def test_demo_mode_overrides_real_service_settings(self):
        line = self.run_settings({"DEMO_MODE": "True", "LOCAL_MODE": "True", "OTP_PROVIDER": "twilio_verify",
                                  "OTP_SMS_BACKEND": "twilio", "OTP_WHATSAPP_BACKEND": "meta", "PAYMENT_MODE": "razorpay",
                                  "REQUIRE_PHONE_VERIFICATION": "False"})
        self.assertEqual(line, "True demo local console console True False")

    def test_without_demo_mode_real_settings_are_respected(self):
        line = self.run_settings({"DEMO_MODE": "False", "LOCAL_MODE": "True", "OTP_PROVIDER": "twilio_verify",
                                  "PAYMENT_MODE": "razorpay", "DEBUG": "False", "OTP_DEV_ECHO": "False"})
        self.assertTrue(line.startswith("False razorpay twilio_verify"), line)
