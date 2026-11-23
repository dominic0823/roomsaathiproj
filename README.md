# RoomSaathi — Affordable Room Rentals for Students, Families & Defence Personnel

A two-sided room-rental marketplace: owners list rooms (PG/single/shared/family/
independent) with rent, deposit, minimum stay, and furnishing details; tenants
browse and filter by budget and who the room suits (students, families, or
defence personnel), schedule a live visit slot, chat with the owner once a
booking is confirmed, and pay a booking amount via Razorpay. Visit-slot
availability updates live for every visitor viewing the same room.

## Exam / demo guide (works offline, no keys needed)

`DEMO_MODE=True` (the default in `.env.example`) makes everything self-contained:
OTP codes are random and shown on screen; payments use a built-in demo gateway; no outside service is called.

Setup (Windows PowerShell):

```
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org
copy .env.example .env
python manage.py migrate
python manage.py seed_demo_data
python manage.py createsuperuser
python manage.py runserver
```

Logins (password `demopass123`): owners `cantt_stay`, `sharma_pg`, `mehta_studio`, `iyer_homes`; tenants `riya_s`, `arjun_k`. Admin: the superuser you created at /admin.

Suggested demo script:
1. Sign up as a new tenant -> verify mobile (pick WhatsApp or SMS; the random OTP appears in the yellow box, press "Fill it for me").
2. Browse rooms: filters, map, compare, 360 tour, photo gallery.
3. Book a visit slot -> demo gateway (UPI / card / net banking / wallet; tick "Simulate a failed payment" to show failure and retry) -> receipt and calendar file.
4. Request a room -> log in as the owner -> Approve -> pay the advance as the tenant -> confirmed.
5. Show chat, notifications, payments page, owner dashboard, admin panel.

To use real services later set `DEMO_MODE=False` and follow the OTP and Razorpay sections below.

## Deploying on Railway (demo)

1. Push the project to a GitHub repository (do not upload `.env`, `venv`, `db.sqlite3`, `media`, `staticfiles`).
2. Railway: New Project > Deploy from GitHub repo. Add a PostgreSQL database to the same project.
3. In the web service > Variables add:
   `DEBUG=False`, `SECRET_KEY=<long random>`, `LOCAL_MODE=True`, `DEMO_MODE=True`, `SECURE_SSL_REDIRECT=False`,
   `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `ALLOWED_HOSTS=.up.railway.app`, `CSRF_TRUSTED_ORIGINS=https://*.up.railway.app`,
   `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`.
4. Settings > Networking > Generate Domain. Open the URL once the deploy is Active.
5. Optional: add a Volume mounted at `/app/media` so uploaded photos survive redeploys.

`railway.json` already holds the build command (collectstatic) and the start command (migrate, create admin, seed demo data, daphne); `.python-version` pins Python 3.12.

## Deploying (Render, free demo)

Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`

Start command:
`python manage.py migrate --noinput && (python manage.py createsuperuser --noinput || true) && python manage.py seed_demo_data && daphne -b 0.0.0.0 -p $PORT config.asgi:application`

Environment variables: `PYTHON_VERSION=3.12.3`, `DEBUG=False`, `SECRET_KEY=<long random>`, `LOCAL_MODE=True`, `DEMO_MODE=True`, `SECURE_SSL_REDIRECT=False`,
`DATABASE_URL=<Postgres internal URL>`, `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`.
`RENDER_EXTERNAL_HOSTNAME` is provided by Render and is trusted automatically.

LOCAL_MODE keeps WebSockets in memory and runs emails inline, so no Redis or worker is needed for a single-instance demo.
For a real launch use `LOCAL_MODE=False`, `DEMO_MODE=False`, Redis (`REDIS_URL`), the `worker` and `beat` processes from the Procfile,
object storage (`AWS_*`, optional `AWS_S3_CUSTOM_DOMAIN`), Twilio Verify, Razorpay live keys and a webhook.

## Quick start without Docker (Windows / any laptop)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # LOCAL_MODE=True is already set: SQLite, no Redis, no Celery worker
python manage.py migrate
python manage.py seed_demo_data
python manage.py createsuperuser
python manage.py runserver
```

Set `LOCAL_MODE=False` in `.env` and run `docker compose up -d` to use Postgres + Redis + Celery.

## How booking works (v3)

* **Visit slots** = times the owner is free to show the room. A tenant books one (small refundable
  token) to *see* the room before deciding.
* **Book the room** = the real rental: tenant sends a request (move-in date + months) -> owner
  approves or declines (48 h) -> tenant pays the advance online (24 h) -> room confirmed, bed held.
  Deposit and rent are paid to the owner directly at move-in. Advance is refundable if the tenant
  cancels 3+ days before move-in; if the owner cancels it is always refunded.
* Rooms have **beds** (1 for a private room, more for a PG); overlapping stays can't overbook.

## OTP verification

Phone OTP is required to book, rent or list only when `REQUIRE_PHONE_VERIFICATION=True`. In `LOCAL_MODE` it defaults to False so nobody is blocked while testing.

Choose how codes are made with `OTP_PROVIDER` in `.env`:

* `local` - the app generates the code and sends it by console / Twilio / Meta (see `.env.example`).
* `twilio_verify` - Twilio Verify generates, sends (SMS or WhatsApp) and checks the code for you.

### Setup: Twilio Verify

1. Create a free account at twilio.com and note the Account SID and Auth Token (Console home page).
2. Console > Verify > Services > Create new. Name it RoomSaathi. Copy the Service SID (starts with VA).
3. Trial accounts can only text numbers you have added under Console > Phone Numbers > Verified Caller IDs - add your own number there.
4. For WhatsApp: open your Verify service > WhatsApp and enable it (Twilio explains the sender options there).
5. Put this in `.env`, then restart:

```
OTP_PROVIDER=twilio_verify
REQUIRE_PHONE_VERIFICATION=True
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_VERIFY_SERVICE_SID=VAxxxxxxxx
```

6. Test: `python manage.py check_messaging --phone 9876543210 --via sms`

Email codes always use the app's own email settings.

## Room photos and 360 tours

Owners add real photos by uploading files or pasting direct image links (a public Google Drive file link also works; Google Photos album links do not). 360 tours use 2:1 equirectangular panoramas (phone panorama mode, Google Street View app, any 360 camera), uploaded or linked. Viewer: Pannellum, loaded in the browser.

## What's new in v4 (UI + features)

* Complete redesign: sticky header with user menu, hero search (city / area / budget / audience),
  stats, popular localities, how-it-works, testimonials, FAQ, rich footer, toasts, mobile-first layout.
* Room page: photo grid + lightbox, sticky booking card, amenities, price-vs-area insight, map,
  rating breakdown, host card, similar rooms, mobile bottom CTA bar.
* Compare up to 3 rooms; recently viewed; search alerts (get notified when a matching room is listed);
  removable filter chips; city filter; messages inbox; owner public profiles + "replies within Xh";
  owner analytics (views, saves, requests, conversion); add-to-calendar (.ics); help/about/contact/terms/privacy;
  sitemap.xml + robots.txt + social-share meta; branded 404/500.
* `python manage.py seed_demo_data` now creates 10 rooms in 5 cities with generated photos and reviews.

## Features

**Tenants**: filter by budget, locality, audience (students / family / defence / professionals),
furnished, verified owners; map view of results; photo gallery; room location map with directions;
WhatsApp click-to-chat; live visit-slot availability; refundable visit token via Razorpay;
chat with the owner after a confirmed booking; reviews; saved rooms; report a listing.

**Owners**: multi-photo listings, map pin picker, edit / pause / delete, bulk slot generator,
"Verified owner" badge (request from the nav; staff approve in admin), email notifications,
dashboard with pending / confirmed counts.

**Platform**: Razorpay webhook + signature check bound to the booking's own order, automatic refunds
on cancellation, unpaid bookings auto-expire (default 15 min), admin moderation for reports,
rate-limited chat, throttled + paginated REST API, automated tests.

## Stack

- Django 5 + Django REST Framework (APIs)
- Django Channels + Redis (WebSockets: live slot availability, in-app chat)
- Celery + Redis (async booking notification emails)
- PostgreSQL (primary database)
- Razorpay test mode (payment checkout + signature verification)
- Vanilla HTML/CSS/JS templates (no frontend build step required)

## Project layout

```
marketplace/
  config/        settings, urls, asgi/wsgi, celery app
  accounts/      custom user model (customer/provider), auth
  services/      service listings, slots, availability websocket
  bookings/      booking creation, cancellation, Celery tasks
  chatapp/       chat rooms, chat websocket consumer
  payments/      Razorpay order creation + signature verification
  templates/     server-rendered HTML (base + per-app templates)
  static/        css/style.css, js/main.js, js/chat.js, js/availability.js
```

## 1. Prerequisites

- Python 3.11+
- Docker Desktop (for Postgres + Redis) — or install both natively if you prefer
- VS Code with the Python extension

## 2. Open the project in VS Code

```bash
cd marketplace
code .
```

Select the Python interpreter you create below via
`Ctrl+Shift+P` → "Python: Select Interpreter" once the venv exists.

## 3. Create a virtual environment and install dependencies

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## 4. Start Postgres + Redis

```bash
docker compose up -d
```

This starts:
- Postgres on `localhost:5432` (db `marketplace_db`, user `marketplace_user`, pass `marketplace_pass`)
- Redis on `localhost:6379`

## 5. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` using your
Razorpay **test mode** keys (dashboard → Settings → API Keys). Everything
else works out of the box with the docker-compose defaults.

## 6. Run migrations and create an admin user

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

## 7. Load demo data (recommended)

```bash
python manage.py seed_demo_data
```

Creates room types, 6 demo owners (password `demopass123`, two are "verified"), listings with map
pins and visit slots. Use `--flush` to reset the demo owners.

## 8. Run the app (three processes)

**Terminal 1 — Django (serves HTTP and WebSockets via Channels' runserver override):**
```bash
python manage.py runserver
```

**Terminal 2 — Celery worker (booking notification emails):**
```bash
celery -A config worker -l info
# on Windows, use:
celery -A config worker -l info --pool=solo
```

**Terminal 3 — Celery beat (releases unpaid bookings every minute):**
```bash
celery -A config beat -l info
```
(If you skip beat, expired holds are still released lazily whenever someone books or opens
a bookings page.)

Visit **http://127.0.0.1:8000**

## 9. Try the full flow

1. Register two accounts: one as **Provider**, one as **Customer** (role is
   picked at signup).
2. Log in as the provider → "My services" → **Add service** → fill details →
   you'll land on "Manage slots" → add a few date/time slots.
3. Open a second (incognito) browser window logged in as the customer →
   "Browse services" → open the service → you'll see live slots with a
   pulsing "available" indicator.
4. Book a slot as the customer. Watch the provider's/other tab's slot list —
   it flips to "Just booked" instantly via WebSocket, without a refresh.
5. Complete payment on the Razorpay test checkout (use Razorpay's test card
   `4111 1111 1111 1111`, any future expiry, any CVV).
6. Once payment succeeds, the booking status flips to **Confirmed** and a
   **Chat** button appears for both the customer and the provider — messages
   sent from either side arrive instantly on the other side via WebSocket.
7. Check the Celery worker terminal — you'll see the booking notification
   "emails" printed there (console email backend, no real SMTP needed for
   local dev).

## Running the tests

```bash
python manage.py test
```

Uses SQLite-compatible settings automatically when `DATABASE_URL=sqlite:///test.db` is set;
Redis is not needed (in-memory channel layer + eager Celery while testing).

## Razorpay webhook (recommended before going live)

Dashboard -> Settings -> Webhooks -> add `https://<your-domain>/payments/webhook/`, enable
`payment.captured`, set a secret and put the same value in `RAZORPAY_WEBHOOK_SECRET`. This confirms
bookings even if a tenant closes the tab right after paying.

## 10. Django admin

`http://127.0.0.1:8000/admin` — manage categories, rooms, slots, bookings, payments,
**owner verification** (select users -> "Mark selected owners as verified") and **reports**
(resolve, or pause the reported listings).

## Notes on production hardening

- Swap `EMAIL_BACKEND` to a real SMTP/API provider.
- Point `RAZORPAY_KEY_*` to live keys and add a signed webhook endpoint for
  extra payment reconciliation beyond the client-side signature check.
- Put Daphne behind Nginx and run Celery under a process manager (systemd/
  supervisor) instead of a bare terminal.
- Set `AWS_STORAGE_BUCKET_NAME` (+ keys) so uploaded photos survive redeploys.
- Run the `beat` process next to `worker` (see Procfile).
- Chat and the API are rate-limited; add login throttling (e.g. django-axes) before going live.
