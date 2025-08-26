# Web Application Design Document

## 1. Introduction
### 1.1 Purpose
auuction is a seasonal fundraising auction platform for a Unitarian Universalist (UU) church. It supports cataloging items (with emphasis on hosted events), bidder registration, online bidding during a limited yearly auction window, settlement of commitments/donations, and year-round fulfillment coordination and reminders for hosted events. This document captures the product requirements, domain model, and API surface—no implementation details.

### 1.2 Scope
In scope:
- Auction lifecycle: pre-auction setup, catalog publishing, registration, bidding window, closing, reoffer buy-it-now phase, settlement, fulfillment.
- Hosted events: capacity management, winner/attendee assignment, waitlist, communication, calendar reminders.
- Items and donations: competitive-bid items, fixed-price signups, services, and event slots.
- Roles and permissions: guests, bidders, donors/hosts, auction managers, admins, finance.
- Notifications via email (and optionally SMS) to hosts and attendees throughout the year.
- Reporting and exports for finance and ministries.

Out of scope (initial release):
- Live auction streaming; advanced dynamic pricing beyond proxy bids and reoffer buy-it-now.
- Complex tax advice or receipting beyond standard donation acknowledgments.
- Native mobile apps (responsive web only initially).

### 1.3 Definitions and Acronyms
| Term | Definition |
|------|------------|
| Hosted Event | An auction item representing a dated event hosted by a congregant, with limited capacity and attendee list. |
| Bidder | Registered user allowed to place bids or sign up for fixed-price items. |
| Donor/Host | Person offering an item or hosting an event. |
| Admin | Staff/volunteer with elevated privileges to manage configuration, users, items, and reports. |
| Auction Manager | Role responsible for running the auction lifecycle (setup, catalog, close). |
| Settlement | Post-auction process to confirm winners, compute commitments, and collect donations/payments. |
| Fulfillment | Execution of hosted events and delivery of physical items/services post-auction. |
| Reoffer (Buy-It-Now) | Post-bidding phase where unsold items may be offered at a fixed price; donors may set a separate reoffer price or opt-out. |
| UU | Unitarian Universalist. |

## 2. System Overview
### 2.1 System Architecture
High-level (technology-agnostic):
- Client (responsive web) for guests, bidders, hosts, and admins.
- API layer exposing resources for users, items, bids, events, notifications, and reports.
- Data layer storing users, items, bids, event instances, attendance, and audit logs.
- Background jobs/scheduler for notifications, waitlist promotion, and deadline-driven tasks (auction open/close, reoffer start/end, reminders).
- Integration layer for email/SMS provider, payment/donation processor, and calendar invites.

### 2.2 Technology Stack
#### Frontend
- Framework: Django server-rendered templates + HTMX and Alpine.js for progressive interactivity.
- State Management: HTMX request/response (oob swaps) with lightweight local storage for wishlist.
- UI Components: Tailwind CSS utility classes and partial templates.
- Build Tools: Tailwind CLI; no SPA bundler initially.

#### Backend
- Runtime: Python 3.12
- Framework: Django 5 + Django REST Framework (DRF)
- API Protocol: REST/JSON with pagination, filtering; idempotency keys for bids and reoffer purchases.
- Authentication: Django auth with email login; optional 2FA (django-otp) later.

#### Database
- Type: PostgreSQL 15/16
- ORM: Django ORM + migrations
- Caching: Redis (sessions, cache, rate limiting)
- Search: PostgreSQL FTS for catalog (optional enhancement)

#### Infrastructure
- Hosting: Self-hosted Proxmox VM (Ubuntu 22.04 LTS) using Docker Compose
- Reverse Proxy/TLS: Caddy with automatic Let’s Encrypt for auuction.org (and www)
- Background Jobs: Celery workers + Celery Beat scheduler (emails, reminders, state flips, exports)
- File Storage: Local volumes on host OS for media, static assets, backups (MinIO optional later)
- CI/CD: GitHub Actions (tests, build images) and simple deploy (compose pull && up -d)
- Monitoring: Sentry (errors), Uptime Kuma (uptime); container logs (Loki optional)

## 3. Functional Requirements
### 3.1 User Roles and Permissions
- Guest: Browse catalog, view public info; cannot bid.
- Bidder (Congregant/Guest): Register, manage profile, place bids, sign up for fixed-price events, view commitments and receipts.
- Donor/Host: Propose items/events, edit their items pre-publish, set reoffer preferences (separate price or opt-out), view winners/attendees, message attendees, propose schedule changes.
- Auction Manager: Configure auction, review/approve items, publish catalog, manage bidding window, handle reoffer phase, resolve ties/disputes, run settlement, manage notifications.
- Admin: Manage users/roles, site settings, content pages, exports; override data when necessary.
- Finance/Treasurer: Access commitment reports, payment reconciliation, receipts/acknowledgments.

### 3.2 Core Features
- Auction Lifecycle Management
  - Define auction dates: registration open/close, catalog publish, bidding open/close, reoffer start/end, settlement open.
  - Automatic state transitions and countdowns.
- Catalog & Search
  - Item categories, tags, search, filters, featured items.
  - Item pages with images, descriptions, donor notes, restrictions.
- Bidding & Signups
  - Proxy/maximum bids for competitive items; bid increments; optional anti-sniping grace.
  - Fixed-price signups for hosted events with capacity; waitlist auto-promotion.
- Reoffer Buy-It-Now Phase
  - After a pause post-bidding close, unsold items may automatically enter a buy-it-now phase.
  - Per-item donor settings: reoffer participation (opt-in/out), reoffer price (can differ from min/opening price), quantity available.
  - Visibility and notifications to bidders and subscribers when reoffer opens; items close when sold out or at reoffer end.
  - Defaults & rules (per user decisions):
    - Default participation: opt-in for all items unless donor opts out.
    - If donor does not set a reoffer price, default to the item's opening/min bid as the buy-it-now price.
    - Reoffer price may be set below the opening/min bid.
    - Inventory: all remaining units move into reoffer by default (unless donor quantity override is set).
    - Queueing/holds: no cart reservation; first-come-first-served. A buy action creates a commitment equivalent to a winning bid.
    - Visibility: During reoffer, remove items that were previously won (i.e., items with successful bids are not shown). Only unsold inventory is displayed.
- Hosted Events Management
  - Event date/time, location (private or church), capacity, accessibility/age/dietary notes.
  - Attendee roster, host messaging, calendar (.ics) invites, reminders, updates, and change management.
- Notifications
  - Transactional: registration, outbid alerts, winning notices, settlement statements, event reminders.
  - Scheduled: X weeks/days before events, day-of reminders, post-event thank-you/surveys.
- Settlement & Donations
  - Winner determination, commitments summary, payment/donation capture or pledge tracking.
  - Receipts and year-end statements.
- Admin & Reporting
  - Dashboard KPIs, item approval workflow, export to CSV for finance, attendance sheets for hosts.
- Accessibility & Inclusivity
  - Large-text and high-contrast modes, simple flows for low-tech users, support for alternate contact preferences.

- Auction Phases & Timelines
  - Pre-Registration: account creation, verification, basic onboarding.
  - Catalog Preview: read-only viewing, wishlist.
  - Bidding Window: live bidding/signups; outbid notifications.
  - Pause: brief inactivity to finalize bidding results and prepare reoffer inventory.
  - Reoffer (Buy-It-Now): fixed-duration window set on the auction calendar each year; offer unsold items at donor-specified (or default) price; donors may opt out per item.
  - Close & Tie Handling: finalize; optional anti-snipe/grace rules.
  - Settlement: statements, payments, receipts.
  - Fulfillment: hosted events occur throughout the year; ongoing notifications.

## 4. Data Model
### 4.1 Database Schema
Entities (high-level):
- User: id, name, email, phone, address, roles, preferences (email/SMS), household.
- DonorProfile/HostProfile: user_id, bio, contact preferences.
- Auction: id, year, key dates (registration_open, catalog_publish, bidding_open, bidding_close, reoffer_open, reoffer_close, settlement_open), state.
- Item: id, auction_id, donor_id, type (competitive, fixed_price_event, fixed_price_item, service), title, description, images, category, min_bid, bid_increment, buy_now, restrictions, tags, status (draft, approved, published, closed).
- ItemReofferSettings: id, item_id, participate (bool, default true), price (nullable; defaults to item's opening/min bid if null at reoffer start), allow_below_min (bool, default true), quantity_override (optional; defaults to all remaining), notes.
- Event (for hosted events): id, item_id, datetime_start/end, location, address privacy, capacity, age/accessibility notes, dietary notes, host_notes.
- Bid: id, item_id, bidder_id, amount, max_proxy_amount, created_at.
- Signup (for fixed-price events/items): id, item_id (or event_id), user_id, quantity, price_at_signup, created_at, status (active, waitlisted, canceled).
- Winner: id, item_id, user_id, amount, quantity, determined_at.
- Attendance: id, event_id, user_id, status (confirmed, waitlisted, canceled, attended, no_show), rsvp_notes.
- Notification: id, user_id, type, channel, subject, body_template_id, scheduled_for, sent_at, status, related_entity (event_id/item_id/auction_id).
- Payment/Donation: id, user_id, method, amount, currency, status, external_ref, created_at, settled_at.
- Receipt: id, user_id, period, total_amount, issued_at, delivery_method.
- AuditLog: id, actor_id, action, entity_type, entity_id, before/after snapshot, timestamp.

#### Columns and constraints (detailed)
- Auction
  - id (pk), year (unique), name, registration_open_at, catalog_publish_at, bidding_open_at, bidding_close_at,
    reoffer_open_at, reoffer_close_at, settlement_open_at, state [draft|registration|catalog|bidding|paused|reoffer|closed|settlement]
  - constraints: bidding_open_at < bidding_close_at; reoffer_open_at >= bidding_close_at; reoffer_close_at > reoffer_open_at
- Item
  - id (pk), auction_id (fk Auction), donor_id (fk User), type [competitive|fixed_price_event|fixed_price_item|service],
    title, description, images (array/JSON), category_id (fk Category), tags (array), restrictions (text),
    opening_min_bid (money), bid_increment (money, nullable for non-competitive), buy_now_price (nullable),
    quantity_total (int, default 1), quantity_sold (int, default 0), status [draft|approved|published|closed]
  - computed: quantity_remaining = quantity_total - quantity_sold
- ItemReofferSettings
  - id (pk), item_id (fk Item unique), participate (bool default true),
    price (money, nullable; if null at reoffer_open -> default opening_min_bid),
    allow_below_min (bool default true), quantity_override (int nullable), notes (text)
  - constraints: quantity_override <= quantity_remaining at reoffer_open
- Event (for hosted events)
  - id (pk), item_id (fk Item unique),
    datetime_start, datetime_end, location_label, address_line1, address_line2, city, state, postal_code,
    address_privacy [hide_all|show_city_only|show_full_to_attendees], capacity (int),
    accessibility_notes, age_restrictions, dietary_notes, host_notes
- Bid
  - id (pk), item_id (fk Item), bidder_id (fk User), amount (money), max_proxy_amount (money nullable), created_at
  - constraints: amount >= opening_min_bid; increments follow bid_increment; only for type=competitive
- Signup (fixed price)
  - id (pk), item_id (fk Item) OR event_id (fk Event), user_id (fk User), quantity (int>=1), price_at_signup (money),
    created_at, status [active|waitlisted|canceled]
- Winner
  - id (pk), item_id (fk Item), user_id (fk User), amount (money), quantity (int>=1), determined_at
- Attendance
  - id (pk), event_id (fk Event), user_id (fk User), status [confirmed|waitlisted|canceled|attended|no_show], rsvp_notes, updated_at
- Notification
  - id (pk), user_id (fk User), channel [email|sms], type [registration|outbid|win|settlement|event_reminder|reoffer_announcement|custom],
    template_key, payload (JSON), scheduled_for, sent_at, status [scheduled|sent|failed], related_entity_type, related_entity_id
- Payment/Donation
  - id (pk), user_id (fk User), method [offline|online], amount, currency, status [pledged|received|failed|refunded], external_ref, created_at, settled_at
- Receipt
  - id (pk), user_id (fk User), period (e.g., year), total_amount, issued_at, delivery_method [email|print]
- AuditLog
  - id (pk), actor_id (fk User), action, entity_type, entity_id, before (JSON), after (JSON), created_at

##### Lookup / picklist
- Category
  - id (pk), name (unique), slug (unique), active (bool default true), sort_order (int)
  - used by: Item.category_id (fk)

Seed (initial; editable by Admin):
- 1: Hosted Events (slug: hosted-events)
- 2: Experiences (slug: experiences)
- 3: Goods (slug: goods)
- 4: Services (slug: services)

##### Donor tracking note
- The offering user is tracked via `Item.donor_id` (fk to `User`). Users can be both bidders and donors; roles are stored in `User.roles`. Donor-level reporting and settlement include aggregates across all items for which the user is donor.

Relationships (high-level):
- Auction 1—N Item
- Item 1—0..1 Event
- Item 1—1 ItemReofferSettings
- Item 1—N Bid; winning Bid -> Winner 1—1 Item
- Event 1—N Attendance; Attendance links User to Event
- User 1—N Donation/Payment, 1—N Notification, 1—N Bid/Signup

### 4.2 Data Flow
- Pre-auction: Admin creates auction, donors submit items with optional reoffer settings; manager approves and publishes.
- Bidding: Users place bids; system updates leading bid and sends outbid alerts.
- Pause & Reoffer: After bidding close, system determines winners and prepares unsold inventory. At reoffer start (fixed calendar window), eligible items (including unfilled event capacity) appear at buy-it-now price; sales are first-come-first-served with no reservation holds.
- Close: Reoffer ends; commitments are finalized; settlement begins.
- Fulfillment: For events, attendees receive scheduled reminders; hosts receive rosters and updates; post-event surveys optionally sent.

## 5. API Design
### 5.1 Endpoint Catalog (high-level)
- Auth & Users
  - POST /auth/register, POST /auth/login, POST /auth/verify, POST /auth/password/reset
  - GET/PUT /users/me, GET /users/{id} (admin), GET /users?query=...
- Auctions
  - GET /auctions/current, GET /auctions/{id}
  - POST/PUT /auctions (admin)
  - POST /auctions/{id}/state (open/close)
  - POST /auctions/{id}/reoffer/state (open/close) (admin) — reoffer runs on a fixed window per the annual calendar.
- Items & Events
  - GET /items, POST /items (donor), GET /items/{id}, PUT /items/{id} (owner/admin), POST /items/{id}/publish
  - GET /items/{id}/event, POST/PUT /items/{id}/event
  - GET /items/{id}/reoffer, PUT /items/{id}/reoffer (owner/admin) — set participate flag, reoffer price, quantity override
- Categories (Admin only)
  - GET /categories, POST /categories (admin), PUT /categories/{id} (admin), DELETE /categories/{id} (admin)
  - Notes: Admin-only CRUD; `Item.category_id` must reference active categories.
- Bids & Signups
  - POST /items/{id}/bids, GET /items/{id}/bids (admin/owner), GET /users/me/bids
  - POST /items/{id}/signups, DELETE /signups/{id}, GET /users/me/signups
- Reoffer (Buy-It-Now)
  - GET /auctions/{id}/reoffer/items
  - POST /items/{id}/buy (reoffer purchase) — first-come-first-served; no cart holds; atomic inventory decrement.
- Winners & Settlement
  - GET /auctions/{id}/winners (admin), POST /auctions/{id}/settle, GET /users/me/commitments
  - GET /users/me/settlement (bidder view: items won, reoffer purchases, fixed-price signups; totals)
  - GET /users/me/sales (donor view: per-item lines; supports filters)
  - GET /users/me/sales/export (CSV; same filters as /users/me/sales)
  - GET /finance/settlement/summary (admin) — totals by category/donor; CSV export
- Attendance & Hosts
  - GET /events/{id}/attendees (host/admin), POST /events/{id}/attendees/{userId}/status
  - POST /events/{id}/message (host/admin)
- Notifications
  - POST /notifications/test (admin), GET /notifications?userId=..., POST /schedule/event-reminders
  - System behavior: when reoffer opens, send announcement to all registered bidders.
- Payments/Donations
  - POST /payments/intent, POST /payments/webhook, GET /users/me/receipts, GET /finance/exports (admin)

### 5.2 Request/Response Examples

#### Auth (sample)
POST /auth/register
Request:
```json
{
  "name": "Jane Doe",
  "email": "jane@example.org",
  "password": "<secret>",
  "preferences": {"email": true, "sms": false}
}
```
Response:
```json
{"id": "u_123", "email": "jane@example.org"}
```

#### Bids
POST /items/{id}/bids
Request:
```json
{
  "amount": 125.00,
  "maxProxyAmount": 200.00,
  "idempotencyKey": "b-9f2f"
}
```
Response (leading):
```json
{
  "itemId": "it_123",
  "leading": true,
  "currentBid": 125.00
}
```
Response (outbid):
```json
{
  "itemId": "it_123",
  "leading": false,
  "currentBid": 150.00,
  "leadingBidderId": "u_999"
}
```

#### Reoffer settings (donor/admin)
PUT /items/{id}/reoffer
Request:
```json
{
  "participate": true,
  "price": 40.00,
  "quantityOverride": 2,
  "notes": "Offer 2 units in reoffer"
}
```
Response:
```json
{
  "itemId": "it_456",
  "participate": true,
  "price": 40.00,
  "quantityEffective": 2
}
```

#### Reoffer listing
GET /auctions/{id}/reoffer/items
Response:
```json
{
  "items": [
    {"id": "it_456", "title": "Picnic Basket", "price": 40.00, "quantityRemaining": 2},
    {"id": "it_789", "title": "UU Dinner", "price": 25.00, "quantityRemaining": 5}
  ],
  "window": {"opensAt": "2025-05-03T18:00:00Z", "closesAt": "2025-05-05T18:00:00Z"}
}
```

#### Reoffer buy (no cart holds; atomic)
POST /items/{id}/buy
Request:
```json
{
  "quantity": 1,
  "idempotencyKey": "r-1a2b"
}
```
Response (success):
```json
{
  "itemId": "it_456",
  "quantityPurchased": 1,
  "priceEach": 40.00,
  "commitmentId": "c_321",
  "quantityRemaining": 1
}
```
Response (sold out):
```json
{
  "error": "sold_out",
  "message": "Item no longer available"
}
```

#### Settlement statements
GET /users/me/settlement
Response (bidder):
```json
{
  "wins": [
    {"itemId": "it_123", "title": "Handmade Quilt", "category": "Goods", "donorName": "A. Donor", "notes": "Pick up at church", "quantity": 1, "amount": 150.00, "source": "win"},
    {"itemId": "it_456", "title": "Picnic Basket", "category": "Goods", "donorName": "B. Donor", "notes": null, "quantity": 1, "amount": 40.00, "source": "reoffer"},
    {"itemId": "it_789", "title": "UU Dinner Seat", "category": "Hosted Events", "donorName": "C. Host", "notes": "Event on June 12", "quantity": 2, "amount": 50.00, "source": "fixed_price"}
  ],
  "total": 240.00,
  "auctionId": "a_2025"
}
```

Notes field derivation in purchases (wins):
- Goods/fixed-price items: donor pickup or fulfillment notes (`Item.restrictions` or explicit pickup notes), if any.
- Hosted events: event date/time and location summary (from `Event.datetime_start`, `Event.location_label` or city-only per privacy).

GET /users/me/sales
Query params (optional): `?auctionId=a_2025&categoryId=cat_1&from=2025-05-01&to=2025-05-31`
Response (donor, per-item):
```json
{
  "sales": [
    {"itemId": "it_321", "title": "Garden Tour", "category": "Experiences", "unitsSold": 6, "gross": 300.00},
    {"itemId": "it_654", "title": "UU Dinner Seat", "category": "Hosted Events", "unitsSold": 10, "gross": 250.00}
  ],
  "totalGross": 550.00,
  "auctionId": "a_2025"
}
```

GET /users/me/sales/export
Query params (optional): `?auctionId=a_2025&categoryId=cat_1&from=2025-05-01&to=2025-05-31`
Response:
- Content-Type: text/csv
- Body (example header):
```
item_id,slug,title,category,units_sold,gross,auction_id,donor_name
```

#### Notifications (system behavior)
On reoffer open, send to all registered bidders:
```json
{
  "type": "reoffer_announcement",
  "template": "reoffer_open",
  "payload": {"auctionId": "a_2025", "opensAt": "...", "closesAt": "..."}
}
```

## 6. User Interface
### 6.1 Key Screens
- Home/Countdown, Auction Info, Registration
- Catalog (browse, filter), Item Detail, Bid/Signup/Buy Modals
- My Account: Bids, Commitments, Receipts, Events, Statements (tabbed: My Purchases | My Sales)
- Donor/Host: Submit Item/Event, Reoffer Settings, Manage Attendees, Message Attendees
- Admin: Dashboard, Item Review Queue, Auctions (bidding and reoffer controls), Users, Reports

### 6.2 UI Components
- ItemCard, BidPanel, SignupCapacityWidget, ReofferSettingsForm, BuyNowButton, EventRosterTable, NotificationPreferencesForm, AdminApprovalsTable

## 7. Security
### 7.1 Authentication
- Email-based login with verification; optional MFA later. Session/token management.

### 7.2 Authorization
- Role-based access control (RBAC) with least privilege; host can access only their items/events; admin overrides logged in audit log.

### 7.3 Data Protection
- Store minimal PII; encrypt at rest and in transit. Rate limiting and CSRF protection. Audit logs for sensitive changes.

## 8. Performance Considerations
### 8.1 Frontend Optimization
- Code splitting, lazy loading, image optimization, CDN-friendly assets.

### 8.2 Backend Optimization
- Caching for catalog pages during peak; efficient bid placement path with idempotency and contention control; concurrency controls for reoffer purchases.

## 9. Testing Strategy
- Unit tests: bidding logic, winner determination, capacity/waitlist, reoffer purchase rules.
- Integration tests: auth, notification scheduling, payment callbacks, reoffer state transitions.
- E2E tests: register→bid→settle; reoffer purchase→receipt; host message→attendee email.
- Performance tests around auction closing and reoffer opening.

## 10. Deployment
- Environments: staging, production. Feature flags for risky changes near auction events.
- Backups before major milestones (catalog publish, bidding open/close, reoffer open/close).

## 11. Monitoring and Analytics
- Uptime and error monitoring; email delivery metrics; job queue/cron health.
- Auction KPIs: total raised, participation rate, item performance, reoffer conversion, event capacity utilization.

## 12. Future Enhancements
- SMS notifications, multilingual content, guest checkout for donations, mobile app, volunteer shifts signup, ministry tagging.

## 13. Appendix
### 13.1 Third-party Services (candidates)
- Email: SES, SendGrid, Mailgun. SMS (optional): Twilio.
- Payments/Donations: Stripe, PayPal (donations). Calendar: .ics attachments.
### 13.2 Dependencies
### 13.3 References
- UU congregation accessibility and inclusivity guidelines (to be linked)

### 13.4 Production Setup (Self-hosted on Proxmox)

This appendix documents a minimal, secure production setup for `https://auuction.org` with local volumes, Caddy auto-TLS, Docker Compose, and Google Workspace mail for `@auuction.org`.

#### 13.4.1 Caddy reverse proxy (TLS & headers)
`ops/caddy/Caddyfile`
```caddy
auuction.org, www.auuction.org {
  encode gzip zstd
  @static path /static/* /assets/*
  handle @static {
    root * /var/www/static
    file_server
  }
  reverse_proxy web:8000
  log {
    output file /var/log/caddy/auuction_access.log
  }
  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Content-Type-Options "nosniff"
    Referrer-Policy "no-referrer-when-downgrade"
  }
}
```

#### 13.4.2 Docker Compose (services & local volumes)
Services (names reflect earlier sections): `proxy` (Caddy), `web` (Django+Gunicorn), `worker` (Celery), `beat` (Celery Beat), `db` (Postgres), `cache` (Redis). Use local volumes for persistence: `media`, `static_assets`, `pg_data`, `redis_data`, `backups`, plus `caddy_data`/`caddy_config`.

#### 13.4.3 Environment variables (.env template)
```
DJANGO_SECRET_KEY=change-me
DJANGO_ALLOWED_HOSTS=auuction.org,www.auuction.org
DATABASE_URL=postgres://auuction:${POSTGRES_PASSWORD}@db:5432/auuction
REDIS_URL=redis://cache:6379/0

# Email (Google Workspace for auuction.org)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=auction@auuction.org
EMAIL_HOST_PASSWORD=<app_password>
DEFAULT_FROM_EMAIL="TVUUC Auction <auction@auuction.org>"

# Optional features
SENTRY_DSN=
```

#### 13.4.4 DNS records (auuction.org)
- A: `auuction.org` → public IP of the VM
- A or CNAME: `www.auuction.org` → `auuction.org`
- CAA (optional): `0 issue "letsencrypt.org"`
- MX (Google Workspace):
  - `1 ASPMX.L.GOOGLE.COM`
  - `5 ALT1.ASPMX.L.GOOGLE.COM`
  - `5 ALT2.ASPMX.L.GOOGLE.COM`
  - `10 ALT3.ASPMX.L.GOOGLE.COM`
  - `10 ALT4.ASPMX.L.GOOGLE.COM`
- SPF (TXT at root): `v=spf1 include:_spf.google.com ~all`
- DKIM: generate in Google Admin for `auuction.org`, add TXT for selector (e.g., `google._domainkey`), then enable.
- DMARC (TXT at `_dmarc.auuction.org`): `v=DMARC1; p=quarantine; rua=mailto:postmaster@auuction.org; pct=100`

#### 13.4.5 Backups
- Nightly DB dump (host cron example):
  ```bash
  30 2 * * * docker exec -t <compose_project>_db pg_dump -U auuction -d auuction > /path/to/backups/auuction-$(date +\%F).sql
  ```
- Weekly Proxmox VM snapshot.
- Optional offsite with restic for `/path/to/backups` and media volume.

#### 13.4.6 Go-live checklist
- DNS A records resolve to VM; ports 80/443 forwarded to VM.
- `docker compose up -d` and Caddy obtained certs (check `docker logs proxy`).
- `collectstatic` run and static volume mounted to proxy.
- Django superuser created; roles assigned.
- Test outbound email from `auction@auuction.org` (SMTP submission with app password).
- HSTS header enabled after HTTPS confirmed site-wide.
- Nightly DB backup cron active; verify dumps.
