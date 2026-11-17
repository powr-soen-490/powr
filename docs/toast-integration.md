# Toast POS Integration

## Overview

powr integrates with Toast via the **Toast Standard API** to import sales history, menu items, and stock information. This document covers the integration architecture, credentials, endpoints, field mappings, known limitations, and version history.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Credentials and Setup](#credentials-and-setup)
3. [Toast Logins and the Saved Token](#toast-logins-and-the-saved-token)
4. [Scopes](#scopes)
5. [Endpoints](#endpoints)
6. [Importing Sales History](#importing-sales-history)
7. [Running Without Toast](#running-without-toast)
8. [Field Mappings](#field-mappings)
9. [Known Limitations](#known-limitations)
10. [Version History](#version-history)

## Getting Started

### Prerequisites

Before you can use the Toast integration, ensure:

1. **Backend is running** (Docker or local Python setup)
   - See [README.md](../README.md) for setup instructions
2. **Database is initialized** with migrations
   - `pos_connections` table created by `backend/db/04_pos_connections.sql`
3. **Encryption key is configured** (POS_CREDENTIALS_ENCRYPTION_KEY in .env)

### Step 1: Generate the POS Encryption Key

The backend encrypts Toast credentials at rest using AES-256-GCM. Generate a new encryption key:

**On macOS/Linux:**
```bash
openssl rand -base64 32
```

**On Windows (PowerShell):**
```powershell
$key = [System.Convert]::ToBase64String((1..32 | ForEach-Object {[byte](Get-Random -Maximum 256)}))
$key
```

**In your `.env` file:**
```
POS_CREDENTIALS_ENCRYPTION_KEY=<paste-the-base64-string-here>
```

### Step 2: Get Toast Credentials

See [How to Create Toast Credentials](#how-to-create-toast-credentials) below.

Save the credentials:
- **Client ID** (e.g., `abc123def456`)
- **Client Secret** (e.g., `secret_xyz789`)

The owner never needs the restaurant GUID in the app: powr finds it when Toast is connected (see [Connecting a Restaurant](#connecting-a-restaurant)). Only the local pull script below needs it in `.env`.

### Step 3: Test Locally (Optional)

No Toast credentials? Set `TOAST_USE_RECORDED_DATA=true` instead and the app runs on a recorded
week of real, scrubbed Toast data. See [Running Without Toast](#running-without-toast).

To test the 30-day pull script locally, add credentials to your `.env`:

```env
TOAST_CLIENT_ID=<your-client-id>
TOAST_CLIENT_SECRET=<your-client-secret>
TOAST_RESTAURANT_GUID=<your-restaurant-guid>
TOAST_API_BASE_URL=https://ws-api.toasttab.com
```

Run the pull script:

```bash
cd backend
python ../scripts/pull_toast_sales.py
```

This script pulls the last 30 days of sales and prints a summary.

### Step 4: Use the REST Endpoints

Both endpoints require **owner authentication**. Credentials are stored encrypted in the database, not in `.env`, and a `pos_connections` row links the restaurant to its Toast restaurant GUID. The legacy `pos_integrations` table does not store a location GUID and is not used by these endpoints.

The owner connects Toast on the Toast connection page (`/settings/pos`, linked from **Settings → POS Settings**), which fills both; see [Connecting a Restaurant](#connecting-a-restaurant).

**Test with curl:**

```bash
# After authenticating as owner, use the session cookie
curl -b "powr_session=<your-session-cookie>" \
  http://localhost:8000/api/pos/toast/sales-summary?days=7

curl -b "powr_session=<your-session-cookie>" \
  http://localhost:8000/api/pos/toast/menu

# Import sales history in the background, then follow it
curl -b "powr_session=<your-session-cookie>" -H "Content-Type: application/json" \
  -d '{"start_date": "2026-11-09", "end_date": "2026-11-15"}' \
  http://localhost:8000/api/pos/toast/imports
curl -b "powr_session=<your-session-cookie>" \
  http://localhost:8000/api/pos/toast/imports/latest
```

See [Endpoints](#endpoints) for full documentation.

## Credentials and Setup

### Toast Credential Types

Toast Standard API requires **OAuth 2.0 Machine Client** credentials:

- **Client ID**: A unique identifier for your integration (e.g., `abcd1234efgh5678`)
- **Client Secret**: A secret key that should be protected like a password
- **Restaurant GUID**: Toast's unique identifier for the restaurant location (e.g., `rest-guid-abc123`)

### How to Create Toast Credentials

1. Log in to the Toast support portal
2. Navigate to **Settings > Integrations > Standard API**
3. Click **Create New Credential**
4. Select **Machine Client** as the access type
5. Save your **Client ID** and **Client Secret** securely
6. Optional, for the local pull script only: the **Restaurant GUID** is in the confirmation email Toast sends when the credential is created

### Connecting a Restaurant

The owner enters only the client ID and secret. When they click **Connect Toast**, `PUT /api/pos/toast/connection`:

1. Logs in to Toast with the credentials. This login's access token is saved with them (step 3),
   so the next import or menu request needs no login of its own.
2. Calls `GET /partners/v1/restaurants`, which lists the restaurants the credentials can access. This is the only Toast call made without the `Toast-Restaurant-External-ID` header, since no GUID is known yet.
3. If exactly one restaurant comes back, saves the credentials and the access token (encrypted),
   clears [Needs reconnect](#needs-reconnect), and links the owner's restaurant to that restaurant's GUID and name in `pos_connections`, in one transaction.

Nothing is saved when the check fails:

| Toast answer | HTTP status | Shown to the owner |
|---|---|---|
| Credentials rejected | 400 | Toast didn't accept this client ID and secret |
| No restaurant | 404 | These credentials can't access any restaurant |
| More than one restaurant | 409 | Not supported yet (choosing one is planned in #161) |
| Login rate limit | 429 | Toast is limiting logins; wait a few minutes |
| Unreachable or error | 502 | Couldn't reach Toast |

The page then shows **Connected to: _restaurant name_**. `GET /api/pos/toast/connection` returns `{location_id, location_name}` for the owner's restaurant (404 when not connected), and `DELETE /api/pos/toast/connection` removes the restaurant's GUID. The saved Toast credentials are removed too, unless another restaurant is still connected with them.

`pos_credentials` holds a single Toast login for the whole app, so connecting replaces any login saved before, even one another restaurant uses. Per-restaurant logins are part of the connection model planned in #161.

### Storing Credentials in powr

Credentials are stored in the `pos_credentials` table and encrypted at rest. They are:

- **Never** sent to the frontend
- **Only** accessible to endpoints marked as owner-only
- **Automatically** decrypted when needed for API calls
- **Validated** with Toast before they are saved

The access token from the latest Toast login is stored next to them, encrypted the same way, with
`expires_at` (when it stops working, UTC) and the `needs_reconnect` flag. The browser gets only
the client ID and `needs_reconnect`: never the secret, the token or its expiry.
`POST`/`PATCH /api/pos/credentials` take only a client ID and secret; a token can only come from
powr's own login.

## Toast Logins and the Saved Token

### Toast's login limit (a recommendation, not a block)

Toast asks integrations **not to request a new access token more than twice per hour**, to aim
for one or two a day, and to reuse each token until it expires
([Authentication rate limit](https://doc.toasttab.com/doc/devguide/apiAuthenticationRateLimit.html)).
"Requesting a token" and "logging in" are the same call: `POST
/authentication/v1/authentication/login` with the client ID and secret.

This is **not an automatic limit**. Toast does not block the third login in an hour, and repeated
logins while a token is still valid just return the same token. But Toast says its team may cut
off API access for integrations that request too many tokens, so powr follows the
recommendation anyway. A login can still get HTTP 429 under Toast's global rate limit (by IP
address) if it is sent many times per second.

Do not mix this up with the **API rate limits**, which are automatic: 20 requests per second and
10,000 per 15 minutes across all API calls, answered with HTTP 429
([Rate limiting](https://doc.toasttab.com/doc/devguide/apiRateLimiting.html)). Those count every
request made with a token, and `retry.py` handles them (see [Retry Strategy](#retry-strategy)).

### How powr reuses the token

- **Connect** saves the token from the login that checks the credentials.
- **Imports, the menu endpoint and the Toast scripts** start from the saved token and make no
  login while it is valid. One import uses no login, or one if the token expires mid-import.
- powr logs in again **only** when the saved token has expired (by `expires_at`) or Toast answers
  401 for it. It then saves the new token and resends the request. It never renews early: until
  a token expires, Toast hands back the same one, so an early login would be wasted.
- How long a token lasts comes from `expiresIn` in each login response, never a fixed number.
  Toast says about a day; the tokens we saw on 2026-11-17 lasted 3 hours (10,800 seconds).
  Each login logs the lifetime (never the token).
- A login answered with 429 is **not retried**. The import stops with "Toast is limiting logins
  right now. Retry in a few minutes", and the menu endpoint returns 429. The saved login stays
  as it is.
- An import started before a reconnect never overwrites the newer login: a token or flag is only
  saved if the client ID it was made with is still the saved one.

Connect, then import, then the menu: **one** login in total
(`backend/tests/integration/test_toast_login_count.py` checks this).

### Needs reconnect

`needs_reconnect` turns on only when Toast rejects the saved client ID or secret (HTTP 401 or 403
on login). The saved token is dropped, and later imports and menu requests stop without asking
Toast again, so a broken login costs no more logins. The Toast connection page shows
**Needs reconnect** and asks for working credentials. Reconnecting clears it.

A token that expires on its own, or Toast being busy or down, never turns it on: powr renews the
token by itself, and the owner has nothing to do.

### Rules for new code that calls Toast

- Build the adapter with `saved_toast_adapter` (`app/modules/pos/toast_tokens.py`), or give
  `ToastClient`/`ToastAdapter` a token store. Never create one without a store in the app: it
  would start without a token and log in on every request.
- Call `adapter.authenticate()` or `client.ensure_token()`, never `client.login()`: they log in
  only when there is no usable token.
- Read data powr already imported (like `sales-summary`) from the database instead of calling
  Toast when you can.
- Test with fake Toast responses, and develop with `TOAST_USE_RECORDED_DATA=true`
  ([Running Without Toast](#running-without-toast)), which makes no real logins. Use real Toast
  only on purpose.

## Scopes

Toast Standard API provides **read-only access** to:

- **Orders**: Order history with line items, modifiers, timestamps, and prices
- **Menus**: Menu items, prices, and modifier groups
- **Stock**: Real-time stock availability and limitations

Scopes are **not** explicitly restricted; access is determined by the application level.

## Endpoints

### GET /api/pos/toast/sales-summary

**Authorization**: Owner only

**Description**: Imported sales for the past N days, totalled by business day. It reads the
sales that [imports](#importing-sales-history) saved, so it never calls Toast and needs no Toast
login. Days that were never imported have no sales.

**Query Parameters**:
- `days` (integer, optional, default=30): Number of days to summarize (range: 1–365)

**Response** (200 OK):
```json
{
  "days": 30,
  "start_date": "2026-09-11",
  "end_date": "2026-10-11",
  "total_orders": 150,
  "total_items": "450.35",
  "total_revenue": "4500.00",
  "daily_stats": [
    {
      "date": "2026-09-11",
      "orders": 5,
      "items": "15.35",
      "revenue": "150.00"
    },
    {
      "date": "2026-09-12",
      "orders": 6,
      "items": "18",
      "revenue": "180.00"
    }
  ]
}
```

**Error Responses**:
- `401 Unauthorized`: No valid powr session
- `403 Forbidden`: Not an owner
- `422 Unprocessable Entity`: Invalid query parameters (e.g., days=0 or days=999)
- `500 Internal Server Error`: The imported sales could not be read

**Notes**:
- Follows the [void and refund rule](#voids-and-refunds): voided lines are left out, refunded
  ones count as sold
- Generated test data (`is_mock`) is left out
- `start_date` is `days` days before today (UTC), so the window covers `days + 1` dates
- Days with no imported sales are not listed; with nothing imported, totals are 0
- Item quantities and revenue are decimal strings, preserving fractional quantities and precision
- Revenue is a sum of line prices; discounts are reflected in line-level prices

### POST /api/pos/toast/imports

**Authorization**: Owner only

**Description**: Start importing Toast sales history in the background. It answers right away
(202) and the import keeps running; follow it with `GET /imports/latest`.

**Request body** (both optional):
```json
{ "start_date": "2024-01-01", "end_date": "2026-11-15" }
```
- `start_date` defaults to **2024-01-01**, the start of Mykonos Grill's Toast history (#52)
- `end_date` defaults to the **last finished business day**: 36 hours before now (UTC), which has
  ended in every North American time zone. A later end date is refused, so a day still in
  progress is never half-imported

**Response** (202 Accepted): the import job (see `GET /imports/latest`).

**Error Responses**:
- `401` / `403`: No valid session / not an owner
- `404 Not Found`: Toast is not connected
- `409 Conflict`: An import is already running for this restaurant
- `422 Unprocessable Entity`: Start after end, an end date that has not finished, or unknown fields

### GET /api/pos/toast/imports/latest

**Authorization**: Owner only

**Description**: The restaurant's most recent import, or `null` when it has never imported. The
Sales Import page polls this every 2 seconds while an import runs.

**Response** (200 OK):
```json
{
  "id": "6f1c…",
  "status": "running",
  "start_date": "2024-01-01",
  "end_date": "2026-11-15",
  "last_completed_date": "2025-03-02",
  "days_completed": 427,
  "total_days": 1050,
  "percent": 40,
  "orders_imported": 23410,
  "items_imported": 56190,
  "error": null,
  "created_at": "2026-11-17T15:00:00Z",
  "finished_at": null
}
```
- `status` is `running`, `failed` or `done`
- `last_completed_date` is the bookmark: every business day up to it is saved
- `percent` is business days done out of 100
- `items_imported` counts sale lines
- `error` explains why a failed import stopped, written for the owner

### POST /api/pos/toast/imports/{id}/retry

**Authorization**: Owner only

**Description**: Continue a **failed** import from the day after its bookmark, as the same job.

**Error Responses**:
- `404 Not Found`: No such import for this restaurant, or Toast is not connected
- `409 Conflict`: The import is not failed, or another import is running

### GET /api/pos/toast/menu

**Authorization**: Owner only

**Description**: Fetch the restaurant's menu items from Toast, including prices and modifier groups.

**Response** (200 OK):
```json
{
  "currency": "USD",
  "items": [
    {
      "item_id": "item-guid-123",
      "item_name": "Chicken Gyro Plate",
      "price": 14.99,
      "currency": "USD",
      "modifier_groups": [
        {
          "group_id": "mod-group-1",
          "group_name": "Toppings",
          "min_selections": 0,
          "max_selections": null,
          "options": [
            {
              "option_id": "mod-1",
              "option_name": "Extra Feta",
              "price": 1.50
            },
            {
              "option_id": "mod-2",
              "option_name": "Extra Tzatziki",
              "price": null
            }
          ]
        }
      ]
    }
  ]
}
```

**Error Responses**:
- `401 Unauthorized`: No valid powr session
- `404 Not Found`: Toast credentials or restaurant connection not configured
- `429 Too Many Requests`: Toast is limiting requests or logins; try again in a few minutes
- `502 Bad Gateway`: Toast rejected the saved login ("Reconnect Toast"; see
  [Needs reconnect](#needs-reconnect)), or another Toast API error

**Notes**:
- Reuses the saved Toast token, so it only logs in when that token has expired
- Returns all menu items visible to the Standard API
- Currency defaults to USD until it is stored on the POS connection
- Prices are base menu prices; dynamic pricing (by size, etc.) appears only at sale time
- Modifier options with `null` price are priced by customer choice or included with the item
- Items are ordered as they appear in Toast's menu structure

## Importing Sales History

Story #52: the owner imports the restaurant's menu and full Toast sales history from the
**Import sales history** page (Settings → POS Settings → Open). Issue #53 built it.

### How an import runs

1. `POST /imports` checks the dates and the Toast connection and saves a `sync_jobs` row with
   `status = running`. A partial unique index allows only one running import per restaurant.
2. A FastAPI background task runs the job after the response is sent. It creates **one**
   `ToastAdapter` that starts from the saved token, so an import usually needs no Toast login,
   and at most one if the token expires mid-import (see
   [Toast Logins](#toast-logins-and-the-saved-token)).
3. It saves the current menu first, so sales of current items find them.
4. It then goes **one business day at a time**, from the day after the bookmark to the end date.
   Each day is fetched with `ordersBulk?businessDate=YYYYMMDD` (every page), then saved **in one
   transaction together with the bookmark** (`last_completed_date`). A day is saved completely or
   not at all, and the bookmark never points past what is saved.
5. When the last day is saved, the job is `done`. If anything stops it, the job is `failed` with a
   message for the owner, and **Retry** continues from the day after the bookmark.

| What happens | What the import does |
|---|---|
| Toast answers 429 or 5xx | The client retries with exponential backoff (see [Retry Strategy](#retry-strategy)) |
| Toast asks to wait more than 30s | The job waits that long, if it is 10 minutes or less, up to 3 times per day; otherwise it fails |
| Toast is disconnected mid-import | Checked before each day: the job fails ("Toast was disconnected"); saved sales are kept |
| Toast rejects the saved login | The job fails and asks the owner to reconnect Toast; [Needs reconnect](#needs-reconnect) turns on, and later imports stop without asking Toast |
| Toast is limiting logins (429 on login) | The job fails and asks to retry in a few minutes; the login is not retried |
| The server restarts mid-import | At startup, jobs still `running` from before the restart are marked failed, so they can be retried |

Imports run inside the web server process. On Render's free plan the server sleeps after
15 minutes without requests, so the page asks the owner to keep it open (its polling keeps the
server awake). If the server sleeps anyway, Retry continues where it stopped.

### What is saved

`backend/db/06_pos_sales_import.sql` creates the tables. Every one has a `restaurant_id`, and
every query filters by it.

| Table | One row per | Unique on |
|---|---|---|
| `menu_items` | Menu item, with price, `is_active` and `is_mock` | restaurant, provider, POS item ID |
| `menu_modifiers` | Modifier option ("Extra feta"), with its group's name and price | restaurant, provider, POS modifier ID |
| `sales_orders` | POS order, with its business date | restaurant, provider, POS order ID |
| `sales_order_lines` | Item sold: quantity (decimal), price, modifiers, `is_voided` | order, POS line ID |
| `sync_jobs` | Import job: status, dates, bookmark, counts, error | (one running per restaurant and provider) |

Everything is an **upsert** (insert, or update when the row exists), so importing the same days
again never duplicates anything. Each day takes a few database round trips, because the rows
are sent as one JSON array per table.

Only allow-listed fields are copied. `ToastAdapter` keeps only the order and menu fields powr
needs, and the row types in `modules/pos/import_mapper.py` list every column the import fills.
Customer names, emails, phone numbers, card data and addresses are never stored;
`tests/integration/test_sales_import_privacy.py` imports orders full of them and checks every
imported table.

### Voids and refunds

This is the one rule for voided and refunded sales. The question is always "was food used up?"

| What happened in Toast | Stored as | Counted in forecasts and totals? |
|---|---|---|
| Normal sale | `is_voided = false` | Yes |
| **Voided or deleted** (the order, check or item) | `is_voided = true` | **No**: the food was never made |
| **Refunded** (money given back) | `is_voided = false` | **Yes**: the food was made and eaten or thrown away |
| A saved item that is **missing** when its order is imported again | `is_voided = true` | No |

Voided lines are kept, not dropped, because a void can happen after a day was imported: importing
that day again flips the saved line to `is_voided = true`. Nothing is ever deleted.

### Menu changes

- Items and modifiers Toast no longer lists become `is_active = false`, never deleted, and become
  active again if they come back. An empty menu from Toast changes nothing.
- An item seen in old sales but not on the current menu gets an inactive `menu_items` row, named
  after its first sale, so recipes can still be attached to it.
- Toast **open items** (names typed at the till, like "Xtra Dressing") all share one item ID. The
  placeholder takes the first name seen, and each sale line keeps its own `item_name`; recipes for
  open items will need to match by name.

## Running Without Toast

Toast has no sandbox for Standard API access, so powr ships one recorded week of real Mykonos
Grill data, scrubbed: the menu and the orders of **Nov 9–15, 2026**, in
`backend/tests/fixtures/toast_week/`. The tests use it, and so can local development:

1. Set `TOAST_USE_RECORDED_DATA=true` in `.env` and recreate the backend
   (`docker compose up -d backend`; `restart` does not read `.env` again). If your database
   existed before #53, add the new tables first; see
   [Run the backend](../README.md#option-a-with-docker) in the README.
2. Connect Toast on `/settings/pos` with **any** client ID and secret. The page shows
   "Connected to: Recorded Toast week (Nov 9-15, 2026)".
3. On **Import sales history**, import **2026-11-09 to 2026-11-15**: 367 orders, 743 items.

Every Toast request is then answered from the files (`integrations/pos/toast/recorded.py`),
underneath the real client, so the adapter, mappers and import run exactly as with Toast. Other
days have no orders. The backend refuses to start with the setting on when `ENVIRONMENT` is
`staging` or `production`.

Connecting in this mode replaces the Toast login saved in your local database (there is one for
the whole app), so reconnect your real login after turning the setting off. This mode makes no
real Toast logins, so use it by default while developing.

### Recording a new week

`scripts/record_toast_fixtures.py` records the menu and a week of orders using
`TOAST_CLIENT_ID`, `TOAST_CLIENT_SECRET` and `TOAST_RESTAURANT_GUID` from `.env`. When the app
in your local database is connected with the same client ID, it reuses the app's saved token
(no login) and saves any new one back; otherwise it logs in once. `scripts/pull_toast_sales.py`
works the same way:

```bash
cd backend
python ../scripts/record_toast_fixtures.py                     # last full Monday-Sunday week
python ../scripts/record_toast_fixtures.py --start 2026-11-02 --force
```

It keeps only allow-listed fields (`integrations/pos/toast/recording.py`), replaces the restaurant
GUID with a fake one, and refuses to save anything that looks like an email, card or phone
number. The repository is public, so read the files before committing them.

## Field Mappings

### Orders → SaleLine

| Toast Field | SaleLine Field | Notes |
|---|---|---|
| `order.guid` | `order_id` | Unique order identifier |
| `order.openedDate` | `timestamp` | UTC timestamp when order was placed |
| `order.businessDate` | `business_date` | Toast's business day (format: `YYYYMMDD`) |
| `check.selections[*].guid` | `line_id` | Unique line identifier within order |
| `selection.item.guid` | `item_id` | Menu item GUID |
| `selection.displayName` | `item_name` | Display name (e.g., "Chicken Gyro") |
| `selection.quantity` | `quantity` | Units sold (Decimal) |
| `selection.price` | `price` | Net price after discounts (Decimal) |
| `selection.modifiers[*]` | `modifiers` | List of SaleModifier objects |
| `order.voided \| selection.voided` | `is_voided` | True if voided/deleted |

### Menus → MenuItem

| Toast Field | MenuItem Field | Notes |
|---|---|---|
| `item.guid` | `item_id` | Unique item identifier |
| `item.name` | `item_name` | Menu display name |
| `item.price` | `price` | Base price (Decimal, may be null) |
| `modifierGroupReferences` | `modifier_groups` | Nested groups with options |

### Stock → StockItem

| Toast Field | StockItem Field | Notes |
|---|---|---|
| `item.guid` | `item_id` | Unique item identifier |
| `item.name` | `item_name` | Item name (may be null) |
| `item.quantity` | `quantity` | Available quantity (may be null) |
| `item.available` | `is_available` | Availability status (may be null) |

## Known Limitations

### API Limits

1. **Date Range**: The ordersBulk endpoint rejects date ranges longer than 30 days. Imports ask
   for one business day at a time; the older `fetch_orders` (used by the pull script) asks for
   7-day windows of modification dates.
2. **Page Size**: Maximum 100 orders per page; pagination is automatic.
3. **Rate Limiting**: Toast enforces rate limits; powr retries with exponential backoff.
4. **Logins**: Toast recommends at most two logins per hour. It is not an automatic block, but
   powr follows it by reusing the saved token; see
   [Toast Logins](#toast-logins-and-the-saved-token).

### Data Gaps

1. **Ingredient Recipes**: Toast does not provide recipe/ingredient mappings; powr manages these separately in the `recipes` table.
2. **Stock Details**: Stock endpoint returns only items that are out of stock or have limits; in-stock items are not included.
3. **Discounts**: Line-level prices reflect discounts, but the original full price is not available.
4. **Modifiers**: Modifier pricing appears only on sold items; modifier group pricing rules are not exposed.
5. **Menu Availability**: Menu endpoint returns the full menu; real-time availability (after hours, etc.) must be managed separately.

### Open Items

Toast "open items" (typed at the till) share one item ID with many names, so they cannot be told
apart by ID. Sale lines keep the typed name.

### Item Name Fallback

If Toast returns an order or menu item without a name, powr uses the constant `MISSING_NAME` ("Missing name") as a placeholder.

## Version History

### Version 1.3 (November 2026)

**Features** (#173, which also finishes the token refresh and Needs-reconnect parts of #48):
- The access token is saved (encrypted) and reused by connect, imports, the menu and the scripts;
  powr logs in only when it expires or Toast rejects it
- Connect, then import, then the menu use one Toast login in total
- `needs_reconnect`: set when Toast rejects the saved client ID or secret, shown on the Toast
  page, cleared by reconnecting
- A rate-limited login is not retried
- The browser no longer receives `expires_at`; `POST`/`PATCH /api/pos/credentials` no longer
  accept a token

### Version 1.2 (November 2026)

**Features** (#53):
- Background import of the menu and sales history, one business day at a time, with progress,
  retry from the last saved day, and one Toast login per import
- Upserts on restaurant, provider and POS order ID, so imports never duplicate orders
- The [void and refund rule](#voids-and-refunds); menu items removed in Toast become inactive
- `sales-summary` reads imported sales instead of calling Toast
- A scrubbed recorded week and `TOAST_USE_RECORDED_DATA` for running without Toast

**Endpoints**:
- `POST /api/pos/toast/imports` - Start an import
- `GET /api/pos/toast/imports/latest` - Follow the latest import
- `POST /api/pos/toast/imports/{id}/retry` - Continue a failed import

### Version 1.1 (November 2026)

**Features**:
- Connecting Toast finds the restaurant GUID automatically from the client ID and secret (#160)
- Credentials are checked with Toast before anything is saved
- The Toast connection page shows which restaurant is connected and is linked from POS Settings

**Endpoints**:
- `GET /api/pos/toast/connection` - Connected restaurant
- `PUT /api/pos/toast/connection` - Connect Toast
- `DELETE /api/pos/toast/connection` - Disconnect Toast

### Version 1.0 (October 2026)

**Features**:
- Sales data retrieval by date range with 30-day default
- Menu items with prices and modifier groups
- Stock item status (out of stock, limited availability)
- Automatic 7-day window splitting for large date ranges
- Retry logic with exponential backoff for rate limits and transient errors
- Token refresh before expiry and on-demand refresh on 401

**Endpoints**:
- `GET /api/pos/toast/sales-summary?days=N` - Fetch sales summary
- `GET /api/pos/toast/menu` - Fetch restaurant menu

**Test Coverage**:
- Unit tests using a fake Toast server (no real API calls in CI)
- Credentials and restaurant connection are checked when the endpoints are called
- Error handling for authentication failures, API errors, and missing data

**Known Issues**:
- None at release

## Implementation Details

### Architecture

The Toast integration follows powr's modular monolith pattern:

```
backend/app/
├── integrations/pos/
│   ├── interface.py          # PosAdapter contract
│   ├── models.py             # Internal data models (SaleLine, MenuItem, etc.)
│   └── toast/
│       ├── adapter.py        # ToastAdapter (implements PosAdapter)
│       ├── client.py         # HTTP client with auth and retries
│       ├── orders.py         # Order response parsing
│       ├── menus.py          # Menu response parsing
│       ├── stock.py          # Stock response parsing
│       ├── locations.py      # Restaurants a login can access (finds the GUID)
│       ├── recording.py      # Scrubs recorded Toast responses (allow-list)
│       ├── recorded.py       # Answers Toast requests from the recorded week
│       ├── retry.py          # Retry policy (rate limit, backoff)
│       └── token_store.py    # Where a client keeps its token between requests
├── api/
│   ├── toast.py              # Sales summary and menu endpoints
│   ├── toast_connection.py   # Connect, view and disconnect Toast
│   └── toast_import.py       # Start, follow and retry imports
├── modules/pos/
│   ├── service.py            # Credentials, connection and sales summary
│   ├── toast_tokens.py       # Adapters that reuse the saved Toast token
│   ├── repository.py         # Credential and connection queries
│   ├── import_service.py     # Runs imports, day by day
│   ├── import_mapper.py      # Adapter models -> rows to save (allow-list)
│   ├── import_repository.py  # Upserts for menus, orders and lines
│   ├── sync_job_repository.py # sync_jobs queries
│   └── sales_repository.py   # Imported sales by day
└── schemas/pos.py            # Pydantic response models
```

### Retry Strategy

Toast client implements exponential backoff for:
- HTTP 429 (rate limit), except on the login: a rate-limited login is not retried
- HTTP 5xx (server errors)
- Network timeouts

**Policy** (`retry.py`):
- Up to 4 attempts in total
- Exponential backoff from 1 second, with full jitter (a random wait up to the backoff)
- Every wait is capped at 30 seconds; `Retry-After` and `X-Toast-RateLimit-Reset` are honoured
- When Toast asks for a longer wait, the client stops and raises `ToastRateLimitError`, which
  imports handle by waiting (see [How an import runs](#how-an-import-runs))

### Encryption

Toast credentials are encrypted at rest in the `pos_credentials` table:
- **Storage**: `client_secret` and `access_token` columns, both encrypted; `expires_at` and
  `needs_reconnect` are stored as plain values
- **Context**: Unique encryption context per credential (`pos_credentials:<pos_name>:<field>`)
- **Decryption**: Automatic on retrieval for server-side use; never sent to frontend
