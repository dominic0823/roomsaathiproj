# RoomSaathi v9.1 (Railway-ready)

- railway.json: collectstatic build command and a start command that migrates, creates the admin user from env vars, seeds demo data and starts Daphne.
- .python-version pins Python 3.12 (Django 5.0 is built for 3.10-3.12).
- README: Railway steps.

# RoomSaathi v9 (deploy-ready)

- Fixed: uploaded and seeded photos returned 404 when DEBUG=False; media is now served by the app unless object storage (AWS_*) is configured.
- Seed command restores photo files that disappeared (free hosts wipe the disk on restart).
- RENDER_EXTERNAL_HOSTNAME is trusted automatically (ALLOWED_HOSTS and CSRF).
- AWS_S3_CUSTOM_DOMAIN supported (Cloudflare R2 public domain).
- Deployment section in README. 192 automated tests.

# RoomSaathi v8 (exam / demo version)

- DEMO_MODE master switch (default on in LOCAL_MODE): forces local random OTP shown on screen, console email, demo payments - overrides any Twilio/Razorpay settings left in .env.
- OTP screen shows the random code in a "Demo OTP" card with a "Fill it for me" button.
- New demo payment gateway: UPI, card (Luhn + expiry + CVV checks, only last 4 digits kept), net banking, wallet; processing screen; simulate-failure option with retry; demo refunds on cancellation.
- Payment history page (tenants: my payments; owners: payments received) with totals and receipt links; payment method stored on each payment.
- Success page shows amount, method, payment ID, reference.
- Demo-mode bar at the top of every page (so nobody mistakes it for live payments).
- 189 automated tests.

Migration: payments 0003 -> python manage.py migrate

# RoomSaathi v7

- Demo rooms now use your real photos (static/demo): every room gets its own cover plus living room, bedroom and balcony shots.
- Photos are enlarged to 1280px wide and lightly sharpened for the big gallery; originals stay in static/demo.
- Re-running `seed_demo_data` swaps older generated illustrations for the real photos (no flush needed).
- One photo that carries a third-party watermark (download (9).jpg) is deliberately not used.
- Gallery grid handles 4 photos; 360 badge moved to the top-left of cards.
- 172 automated tests.

# RoomSaathi v6

- OTP can use Twilio Verify (`OTP_PROVIDER=twilio_verify`) for SMS and WhatsApp; setup steps in README.
- `REQUIRE_PHONE_VERIFICATION` switch (defaults to off in LOCAL_MODE) so listing and booking work without OTP while testing.
- Console OTP printing is safe on Windows terminals.
- Real photos: upload files or paste image links (Google Drive links converted); 360 tours with Pannellum; 360 badge on cards; demo rooms get a generated 360 tour.
- All code comments and docstrings removed.
- 170 automated tests.

Migration: services 0009 -> python manage.py migrate

# RoomSaathi v5.1 - hotfix

## Fixed: "We couldn't send the code right now" (WhatsApp / SMS / email)
- Cause 1: `.env.example` had comments after values (`OTP_SMS_BACKEND=console   # ...`), leaving trailing spaces, so the backend name was
  read as `'console   '` and rejected. Backend names are now trimmed and case-insensitive, and the example file has no inline comments.
  Existing `.env` files keep working - no edit needed.
- Cause 2: email only *printed* in the terminal by default, so nothing reached an inbox. The dev code now also shows on the page (DEBUG only);
  in production email is hidden unless SMTP is configured; `.env.example` has ready-to-fill Gmail SMTP lines.
- In DEBUG the real error is shown ("[Setup problem ...]"); end users still get a friendly message.
- New: `python manage.py check_messaging [--phone N --via whatsapp|sms] [--email you@x.com]` shows what is configured and sends a real test message.
- 152 automated tests.

