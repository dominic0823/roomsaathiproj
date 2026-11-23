import json
import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import OTPCode, User
from .otp import OTPError, issue_otp, mask_target, normalize_phone, verify_otp

PH = OTPCode.Channel.PHONE


def capture_sms():
    sent = []
    patcher = mock.patch("accounts.otp.send_sms", side_effect=lambda phone, text: sent.append((phone, re.search(r"\d{6}", text).group())))
    patcher.start()
    return sent, patcher


class PhoneNormalizeTests(TestCase):
    def test_formats(self):
        self.assertEqual(normalize_phone("98765 43210"), "+919876543210")
        self.assertEqual(normalize_phone("+91-98765-43210"), "+919876543210")
        self.assertEqual(normalize_phone("09876543210"), "+919876543210")
        self.assertEqual(normalize_phone("919876543210"), "+919876543210")
        self.assertEqual(normalize_phone("+14155550123"), "+14155550123")
        self.assertEqual(normalize_phone(""), "")
        for bad in ("12345", "5876543210", "abcdefghij", "+91123"):
            self.assertIsNone(normalize_phone(bad), bad)

    def test_mask(self):
        self.assertEqual(mask_target(PH, "+919876543210"), "+91*******210")
        self.assertEqual(mask_target(OTPCode.Channel.EMAIL, "tushar@x.com"), "tu****@x.com")


class OTPCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", "u@x.com", "pw12345678", phone_number="+919876543210")
        self.sent, self.patcher = capture_sms()
        self.addCleanup(self.patcher.stop)

    def test_issue_and_verify_success_and_single_use(self):
        issue_otp(self.user, PH, self.user.phone_number)
        phone, code = self.sent[-1]
        self.assertEqual(phone, "+919876543210")
        self.assertEqual(verify_otp(self.user, PH, phone, code), (True, ""))
        ok, _ = verify_otp(self.user, PH, phone, code)
        self.assertFalse(ok)

    def test_code_is_not_stored_in_plain_text(self):
        issue_otp(self.user, PH, self.user.phone_number)
        code = self.sent[-1][1]
        self.assertNotIn(code, OTPCode.objects.get().code_hash)
        self.assertEqual(len(OTPCode.objects.get().code_hash), 64)

    def test_wrong_code_locks_after_max_attempts(self):
        issue_otp(self.user, PH, self.user.phone_number)
        real = self.sent[-1][1]
        wrong = "000000" if real != "000000" else "111111"
        for _ in range(5):
            ok, _ = verify_otp(self.user, PH, self.user.phone_number, wrong)
            self.assertFalse(ok)
        ok, msg = verify_otp(self.user, PH, self.user.phone_number, real)
        self.assertFalse(ok)

    def test_expired_code_rejected(self):
        issue_otp(self.user, PH, self.user.phone_number)
        OTPCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        ok, msg = verify_otp(self.user, PH, self.user.phone_number, self.sent[-1][1])
        self.assertFalse(ok)
        self.assertIn("expired", msg)

    def test_resend_cooldown_then_new_code_invalidates_old(self):
        issue_otp(self.user, PH, self.user.phone_number)
        with self.assertRaises(OTPError):
            issue_otp(self.user, PH, self.user.phone_number)
        OTPCode.objects.update(created_at=timezone.now() - timedelta(minutes=1))
        issue_otp(self.user, PH, self.user.phone_number)
        old, new = self.sent[0][1], self.sent[1][1]
        if old != new:
            self.assertFalse(verify_otp(self.user, PH, self.user.phone_number, old)[0])
        self.assertTrue(verify_otp(self.user, PH, self.user.phone_number, new)[0])

    def test_hourly_cap(self):
        for _ in range(5):
            issue_otp(self.user, PH, self.user.phone_number)
            OTPCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        with self.assertRaises(OTPError) as ctx:
            issue_otp(self.user, PH, self.user.phone_number)
        self.assertIn("Too many", str(ctx.exception))

    def test_failed_delivery_does_not_burn_the_cooldown(self):
        self.patcher.stop()
        with mock.patch("accounts.otp.send_sms", side_effect=RuntimeError("provider down")):
            with self.assertRaises(OTPError):
                issue_otp(self.user, PH, self.user.phone_number)
        self.assertEqual(OTPCode.objects.count(), 0)
        self.patcher.start()

    def test_email_otp_is_emailed(self):
        issue_otp(self.user, OTPCode.Channel.EMAIL, self.user.email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["u@x.com"])
        code = re.search(r"\d{6}", mail.outbox[0].body).group()
        self.assertTrue(verify_otp(self.user, OTPCode.Channel.EMAIL, self.user.email, code)[0])


@override_settings(OTP_SMS_BACKEND="twilio", TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="tok", TWILIO_FROM_NUMBER="+15550001111")
class TwilioBackendTests(TestCase):
    def test_posts_to_twilio(self):
        from .otp import send_sms
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 201
            send_sms("+919876543210", "123456 is your code")
        args, kwargs = post.call_args
        self.assertIn("/Accounts/AC123/Messages.json", args[0])
        self.assertEqual(kwargs["data"]["To"], "+919876543210")
        self.assertEqual(kwargs["auth"], ("AC123", "tok"))

    def test_provider_error_becomes_user_message(self):
        from .otp import send_sms
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 400
            post.return_value.text = "bad"
            with self.assertRaises(OTPError):
                send_sms("+919876543210", "x")


class VerificationFlowTests(TestCase):
    def setUp(self):
        self.sent, p = capture_sms()
        self.addCleanup(p.stop)

    def register(self, phone="98765 43210"):
        return self.client.post(reverse("accounts:register"), {
            "username": "newbie", "email": "n@x.com", "phone_number": phone, "role": "CUSTOMER",
            "password1": "Zx9!qwerty77", "password2": "Zx9!qwerty77"})

    def test_register_requires_valid_phone_and_stores_normalized(self):
        self.assertEqual(self.register("12345").status_code, 200)
        self.assertFalse(User.objects.exists())
        resp = self.register()
        self.assertRedirects(resp, reverse("accounts:verify", args=["phone"]), fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual(user.phone_number, "+919876543210")
        self.assertFalse(user.phone_verified)

    def test_full_phone_verification_via_otp(self):
        self.register()
        url = reverse("accounts:verify", args=["phone"])
        self.client.post(url, {"action": "send"})
        code = self.sent[-1][1]
        self.client.post(url, {"action": "verify", "code": "000000" if code != "000000" else "111111"})
        self.assertFalse(User.objects.get().phone_verified)
        self.client.post(url, {"action": "verify", "code": code})
        self.assertTrue(User.objects.get().phone_verified)

    def test_number_verified_elsewhere_cannot_be_claimed(self):
        User.objects.create_user("owner", "o@x.com", "pw12345678", phone_number="+919876543210", phone_verified=True)
        self.register()
        resp = self.client.post(reverse("accounts:verify", args=["phone"]), {"action": "send"})
        self.assertEqual(self.sent, [])
        self.assertFalse(User.objects.get(username="newbie").phone_verified)

    def test_changing_phone_resets_verification(self):
        u = User.objects.create_user("p", "p@x.com", "pw12345678", phone_number="+919876543210", phone_verified=True, email_verified=True)
        self.client.force_login(u)
        self.client.post(reverse("accounts:profile"), {"first_name": "P", "email": "p@x.com", "phone_number": "9123456789"})
        u.refresh_from_db()
        self.assertEqual(u.phone_number, "+919123456789")
        self.assertFalse(u.phone_verified)
        self.assertTrue(u.email_verified)

    def test_open_redirect_in_next_is_ignored(self):
        u = User.objects.create_user("p", "p@x.com", "pw12345678", phone_number="+919876543210")
        self.client.force_login(u)
        url = reverse("accounts:verify", args=["phone"])
        self.client.post(url, {"action": "send", "next": "https://evil.example/"})
        code = self.sent[-1][1]
        resp = self.client.post(url, {"action": "verify", "code": code, "next": "https://evil.example/"})
        self.assertEqual(resp.url, reverse("accounts:profile"))


class OTPLoginTests(TestCase):
    def setUp(self):
        self.sent, p = capture_sms()
        self.addCleanup(p.stop)
        self.user = User.objects.create_user("lg", "l@x.com", "pw12345678", phone_number="+919876543210", phone_verified=True)

    def test_login_with_otp(self):
        url = reverse("accounts:login_otp")
        self.client.post(url, {"action": "send", "phone": "98765 43210"})
        code = self.sent[-1][1]
        self.client.post(url, {"action": "verify", "code": code})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_wrong_code_does_not_log_in(self):
        url = reverse("accounts:login_otp")
        self.client.post(url, {"action": "send", "phone": "9876543210"})
        self.client.post(url, {"action": "verify", "code": "999999" if self.sent[-1][1] != "999999" else "888888"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_number_gets_no_sms_and_same_message(self):
        resp = self.client.post(reverse("accounts:login_otp"), {"action": "send", "phone": "9000000001"}, follow=True)
        self.assertEqual(self.sent, [])
        self.assertContains(resp, "If this number is registered")

    def test_unverified_phone_cannot_use_otp_login(self):
        User.objects.filter(pk=self.user.pk).update(phone_verified=False)
        self.client.post(reverse("accounts:login_otp"), {"action": "send", "phone": "9876543210"})
        self.assertEqual(self.sent, [])


class NotificationTests(TestCase):
    def test_bell_count_and_mark_read(self):
        from .notifications import notify
        u = User.objects.create_user("n", "n@x.com", "pw12345678")
        notify(u, "Hello", "/x/")
        self.client.force_login(u)
        self.assertContains(self.client.get("/"), 'class="bell-count"')
        self.client.get(reverse("accounts:notifications"))
        self.assertEqual(u.notifications.filter(is_read=False).count(), 0)


class PasswordResetTests(TestCase):
    def test_reset_email_is_sent(self):
        User.objects.create_user("r", "r@x.com", "pw12345678")
        self.client.post(reverse("accounts:password_reset"), {"email": "r@x.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)


WA = OTPCode.Channel.WHATSAPP


def capture_whatsapp():
    sent = []
    patcher = mock.patch("accounts.otp.send_whatsapp",
                         side_effect=lambda phone, code, text: sent.append((phone, code)))
    patcher.start()
    return sent, patcher


@override_settings(OTP_WHATSAPP_BACKEND="twilio", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="tok",
                   TWILIO_WHATSAPP_FROM="whatsapp:+14155238886", TWILIO_WHATSAPP_CONTENT_SID="")
class TwilioWhatsAppTests(TestCase):
    def test_sends_whatsapp_prefixed_numbers_with_body(self):
        from .otp import send_whatsapp
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 201
            send_whatsapp("+919876543210", "123456", "123456 is your code")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["To"], "whatsapp:+919876543210")
        self.assertEqual(data["From"], "whatsapp:+14155238886")
        self.assertEqual(data["Body"], "123456 is your code")

    @override_settings(TWILIO_WHATSAPP_CONTENT_SID="HX123")
    def test_uses_approved_template_when_configured(self):
        from .otp import send_whatsapp
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 201
            send_whatsapp("+919876543210", "654321", "x")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["ContentSid"], "HX123")
        self.assertEqual(json.loads(data["ContentVariables"]), {"1": "654321"})
        self.assertNotIn("Body", data)

    def test_provider_error_suggests_sms(self):
        from .otp import send_whatsapp
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 400
            post.return_value.text = "bad"
            with self.assertRaises(OTPError) as ctx:
                send_whatsapp("+919876543210", "1", "x")
        self.assertIn("text message", str(ctx.exception))


@override_settings(OTP_WHATSAPP_BACKEND="meta", META_WA_TOKEN="tok", META_WA_PHONE_NUMBER_ID="555",
                   META_WA_TEMPLATE_NAME="otp_code", META_WA_TEMPLATE_LANG="en", META_WA_AUTH_TEMPLATE=True)
class MetaWhatsAppTests(TestCase):
    def test_cloud_api_payload(self):
        from .otp import send_whatsapp
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 200
            send_whatsapp("+919876543210", "246810", "x")
        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        self.assertIn("/555/messages", url)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer tok")
        self.assertEqual(body["to"], "919876543210")
        self.assertEqual(body["type"], "template")
        self.assertEqual(body["template"]["name"], "otp_code")
        comps = body["template"]["components"]
        self.assertEqual(comps[0]["parameters"][0]["text"], "246810")
        self.assertEqual(comps[1]["sub_type"], "url")

    @override_settings(META_WA_AUTH_TEMPLATE=False)
    def test_plain_template_has_only_body(self):
        from .otp import send_whatsapp
        with mock.patch("accounts.otp.requests.post") as post:
            post.return_value.status_code = 200
            send_whatsapp("+919876543210", "1", "x")
        self.assertEqual(len(post.call_args.kwargs["json"]["template"]["components"]), 1)


class ConsoleSafetyTests(TestCase):
    @override_settings(TESTING=False, DEBUG=False, OTP_WHATSAPP_BACKEND="console", OTP_SMS_BACKEND="console")
    def test_console_backends_refuse_to_fake_delivery_in_production(self):
        from .otp import channel_available, send_sms, send_whatsapp
        self.assertFalse(channel_available(WA))
        self.assertFalse(channel_available(PH))
        with self.assertRaises(OTPError):
            send_whatsapp("+919876543210", "1", "x")
        with self.assertRaises(OTPError):
            send_sms("+919876543210", "x")

    @override_settings(TESTING=False, DEBUG=False, OTP_WHATSAPP_BACKEND="twilio", OTP_SMS_BACKEND="console")
    def test_only_configured_channels_are_offered(self):
        from .otp import channel_available
        self.assertTrue(channel_available(WA))
        self.assertFalse(channel_available(PH))

    @override_settings(DEBUG=True)
    def test_console_is_fine_in_development(self):
        from .otp import channel_available
        self.assertTrue(channel_available(WA))


class ChannelChoiceFlowTests(TestCase):
    def setUp(self):
        self.wa, p1 = capture_whatsapp(); self.addCleanup(p1.stop)
        self.sms, p2 = capture_sms(); self.addCleanup(p2.stop)
        self.user = User.objects.create_user("c", "c@x.com", "pw12345678", phone_number="+919876543210")
        self.client.force_login(self.user)
        self.url = reverse("accounts:verify", args=["phone"])

    def test_choose_whatsapp_sends_only_on_whatsapp(self):
        self.client.post(self.url, {"action": "send", "via": "whatsapp"})
        self.assertEqual(len(self.wa), 1)
        self.assertEqual(self.sms, [])
        self.assertEqual(OTPCode.objects.get().channel, WA)

    def test_choose_sms_sends_only_sms(self):
        self.client.post(self.url, {"action": "send", "via": "sms"})
        self.assertEqual(len(self.sms), 1)
        self.assertEqual(self.wa, [])

    def test_code_from_whatsapp_verifies_the_phone(self):
        self.client.post(self.url, {"action": "send", "via": "whatsapp"})
        code = self.wa[-1][1]
        self.client.post(self.url, {"action": "verify", "code": code})
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)

    def test_switching_channel_invalidates_older_code_and_shares_limits(self):
        self.client.post(self.url, {"action": "send", "via": "sms"})
        sms_code = self.sms[-1][1]
        OTPCode.objects.update(created_at=timezone.now() - timedelta(minutes=1))
        self.client.post(self.url, {"action": "send", "via": "whatsapp"})
        wa_code = self.wa[-1][1]
        if sms_code != wa_code:
            self.assertFalse(verify_otp(self.user, PH, self.user.phone_number, sms_code)[0])
        self.assertTrue(verify_otp(self.user, PH, self.user.phone_number, wa_code)[0])

    def test_cooldown_applies_across_channels(self):
        self.client.post(self.url, {"action": "send", "via": "sms"})
        self.client.post(self.url, {"action": "send", "via": "whatsapp"})
        self.assertEqual(self.wa, [])

    def test_hourly_cap_is_shared_by_sms_and_whatsapp(self):
        for i in range(5):
            issue_otp(self.user, WA if i % 2 else PH, self.user.phone_number)
            OTPCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        with self.assertRaises(OTPError):
            issue_otp(self.user, WA, self.user.phone_number)

    def test_page_offers_both_channels_then_shows_code_boxes(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Send on WhatsApp", html)
        self.assertIn("Send as text message", html)
        self.client.post(self.url, {"action": "send", "via": "whatsapp"})
        html = self.client.get(self.url).content.decode()
        self.assertIn('id="otp-boxes"', html)
        self.assertIn("by WhatsApp", html)
        self.assertIn("Resend on WhatsApp", html)

    def test_email_channel_still_works(self):
        resp = self.client.post(reverse("accounts:verify", args=["email"]), {"action": "send"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.wa + self.sms, [])


class OTPLoginChannelTests(TestCase):
    def setUp(self):
        self.wa, p1 = capture_whatsapp(); self.addCleanup(p1.stop)
        self.sms, p2 = capture_sms(); self.addCleanup(p2.stop)
        self.user = User.objects.create_user("w", "w@x.com", "pw12345678", phone_number="+919876543210", phone_verified=True)

    def test_login_via_whatsapp(self):
        url = reverse("accounts:login_otp")
        self.client.post(url, {"action": "send", "phone": "9876543210", "via": "whatsapp"})
        self.assertEqual(self.sms, [])
        self.client.post(url, {"action": "verify", "code": self.wa[-1][1]})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_page_offers_whatsapp_and_sms(self):
        html = self.client.get(reverse("accounts:login_otp")).content.decode()
        self.assertIn("Get code on WhatsApp", html)
        self.assertIn("Get code by SMS", html)

    def test_unknown_number_sends_nothing_on_any_channel(self):
        self.client.post(reverse("accounts:login_otp"), {"action": "send", "phone": "9000000009", "via": "whatsapp"})
        self.assertEqual(self.wa + self.sms, [])


class ProfileChecklistTests(TestCase):
    def test_progress_reflects_verification(self):
        u = User.objects.create_user("p", "p@x.com", "pw12345678", first_name="Pia", phone_number="+919876543210",
                                     phone_verified=True)
        self.client.force_login(u)
        resp = self.client.get(reverse("accounts:profile"))
        self.assertEqual(resp.context["progress"], 67)
        u.email_verified = True
        u.save()
        self.assertEqual(self.client.get(reverse("accounts:profile")).context["progress"], 100)


class SettingsWhitespaceTests(TestCase):
    @override_settings(DEBUG=True, OTP_WHATSAPP_BACKEND="console     ", OTP_SMS_BACKEND="Console  ")
    def test_trailing_spaces_and_case_in_backend_names_are_tolerated(self):
        from .otp import backend_for, channel_available, send_sms, send_whatsapp
        self.assertEqual(backend_for(WA), "console")
        self.assertEqual(backend_for(PH), "console")
        self.assertTrue(channel_available(WA))
        send_whatsapp("+919876543210", "123456", "x")
        send_sms("+919876543210", "x")

    @override_settings(DEBUG=True, OTP_WHATSAPP_BACKEND="carrier-pigeon")
    def test_misconfiguration_shows_real_reason_in_debug(self):
        u = User.objects.create_user("m", "m@x.com", "pw12345678", phone_number="+919876543210")
        with self.assertRaises(OTPError) as ctx:
            issue_otp(u, WA, u.phone_number)
        self.assertIn("carrier-pigeon", str(ctx.exception))

    @override_settings(DEBUG=False, TESTING=False, OTP_WHATSAPP_BACKEND="carrier-pigeon")
    def test_misconfiguration_is_friendly_in_production(self):
        u = User.objects.create_user("m", "m@x.com", "pw12345678", phone_number="+919876543210")
        with self.assertRaises(OTPError) as ctx:
            issue_otp(u, WA, u.phone_number)
        self.assertNotIn("carrier-pigeon", str(ctx.exception))
        self.assertEqual(OTPCode.objects.count(), 0)

    def test_shipped_env_example_has_no_inline_comments_after_values(self):
        import pathlib
        text = (pathlib.Path(__file__).resolve().parent.parent / ".env.example").read_text()
        for line in text.splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                value = line.split("=", 1)[1]
                self.assertNotIn(" #", value, line)
                self.assertEqual(value, value.strip(), line)

    @override_settings(DEBUG=False, TESTING=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_email_is_not_offered_in_production(self):
        from .otp import channel_available
        self.assertFalse(channel_available(OTPCode.Channel.EMAIL))

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_email_code_is_echoed_on_page_in_dev(self):
        from django.conf import settings as dj
        u = User.objects.create_user("e", "e@x.com", "pw12345678", phone_number="+919876543210")
        self.client.force_login(u)
        with override_settings(OTP_DEV_ECHO=True):
            resp = self.client.post(reverse("accounts:verify", args=["email"]), {"action": "send"}, follow=True)
        self.assertContains(resp, "Demo OTP")


class CheckMessagingCommandTests(TestCase):
    def test_command_reports_backends_and_can_send_test(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        with override_settings(DEBUG=True):
            call_command("check_messaging", "--email", "t@x.com", stdout=out)
        text = out.getvalue()
        self.assertIn("WhatsApp", text)
        self.assertIn("Sent a test message", text)
        self.assertEqual(len(mail.outbox), 1)


from services.models import Service as _Service


@override_settings(OTP_PROVIDER="twilio_verify", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="tok", TWILIO_VERIFY_SERVICE_SID="VA123")
class TwilioVerifyProviderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("v", "v@x.com", "pw12345678", phone_number="+919876543210")
        self.client.force_login(self.user)
        self.url = reverse("accounts:verify", args=["phone"])

    def post_mock(self, status_start=201, check_status="approved", check_code=200):
        def fake(url, data=None, auth=None, timeout=None, **kw):
            resp = mock.Mock()
            if url.endswith("/Verifications"):
                resp.status_code = status_start
                resp.text = "x"
            else:
                resp.status_code = check_code
                resp.json.return_value = {"status": check_status}
                resp.text = "x"
            return resp
        return mock.patch("accounts.otp.requests.post", side_effect=fake)

    def test_start_calls_verify_api_with_channel_and_no_local_code(self):
        with self.post_mock() as post:
            self.client.post(self.url, {"action": "send", "via": "whatsapp"})
        url = post.call_args.args[0]
        self.assertEqual(url, "https://verify.twilio.com/v2/Services/VA123/Verifications")
        self.assertEqual(post.call_args.kwargs["data"], {"To": "+919876543210", "Channel": "whatsapp"})
        self.assertEqual(post.call_args.kwargs["auth"], ("AC1", "tok"))
        self.assertEqual(OTPCode.objects.get().code_hash, "external")

    def test_sms_channel_and_full_verification(self):
        with self.post_mock() as post:
            self.client.post(self.url, {"action": "send", "via": "sms"})
            self.assertEqual(post.call_args.kwargs["data"]["Channel"], "sms")
            self.client.post(self.url, {"action": "verify", "code": "123456"})
        self.assertEqual(post.call_args.args[0], "https://verify.twilio.com/v2/Services/VA123/VerificationCheck")
        self.assertEqual(post.call_args.kwargs["data"], {"To": "+919876543210", "Code": "123456"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)

    def test_wrong_code_is_rejected(self):
        with self.post_mock(check_status="pending"):
            self.client.post(self.url, {"action": "send", "via": "sms"})
            self.client.post(self.url, {"action": "verify", "code": "000000"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.phone_verified)
        self.assertEqual(OTPCode.objects.get().attempts, 1)

    def test_expired_or_unknown_code_404_is_rejected(self):
        with self.post_mock(check_code=404):
            self.client.post(self.url, {"action": "send", "via": "sms"})
            self.client.post(self.url, {"action": "verify", "code": "123456"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.phone_verified)

    def test_send_failure_and_rate_limit_show_friendly_errors(self):
        with self.post_mock(status_start=429):
            resp = self.client.post(self.url, {"action": "send", "via": "sms"}, follow=True)
        self.assertContains(resp, "Too many codes")
        self.assertEqual(OTPCode.objects.count(), 0)
        with self.post_mock(status_start=400):
            resp = self.client.post(self.url, {"action": "send", "via": "whatsapp"}, follow=True)
        self.assertContains(resp, "WhatsApp")
        self.assertEqual(OTPCode.objects.count(), 0)

    def test_both_phone_channels_offered_and_email_stays_local(self):
        from .otp import backend_for, channel_available
        self.assertEqual(backend_for(WA), "twilio_verify")
        self.assertTrue(channel_available(WA) and channel_available(PH))
        self.client.post(reverse("accounts:verify", args=["email"]), {"action": "send"})
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(TWILIO_VERIFY_SERVICE_SID="")
    @override_settings(DEBUG=True)
    def test_missing_service_sid_gives_clear_debug_message(self):
        resp = self.client.post(self.url, {"action": "send", "via": "sms"}, follow=True)
        self.assertContains(resp, "TWILIO_VERIFY_SERVICE_SID")


class RequireVerificationToggleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("o", "o@x.com", "pw12345678", role="PROVIDER", phone_number="+919876543210")
        self.client.force_login(self.owner)

    @override_settings(REQUIRE_PHONE_VERIFICATION=True)
    def test_blocked_when_required(self):
        self.assertEqual(self.client.get(reverse("services:create")).status_code, 302)

    @override_settings(REQUIRE_PHONE_VERIFICATION=False)
    def test_open_when_not_required_and_banner_hidden(self):
        self.assertEqual(self.client.get(reverse("services:create")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("home")), "Verify your mobile number to book")

    @override_settings(REQUIRE_PHONE_VERIFICATION=False)
    def test_tenant_can_request_room_without_otp(self):
        import datetime
        from django.utils import timezone
        room = _Service.objects.create(provider=self.owner, title="R", description="d", price=5000, advance_amount=0)
        tenant = User.objects.create_user("t", "t@x.com", "pw12345678", role="CUSTOMER")
        self.client.force_login(tenant)
        self.client.post(reverse("bookings:rent_room", args=[room.pk]), {
            "move_in_date": (timezone.localdate() + datetime.timedelta(days=5)).isoformat(), "stay_months": 2})
        self.assertEqual(room.bookings.count(), 1)
