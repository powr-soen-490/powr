# Toast POS Integration

## Overview

powr integrates with Toast via the **Toast Standard API** to import sales data, menu items, and stock information. This document covers the integration architecture, credentials, endpoints, field mappings, known limitations, and version history.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Credentials and Setup](#credentials-and-setup)
3. [Scopes](#scopes)
4. [Endpoints](#endpoints)
5. [Field Mappings](#field-mappings)
6. [Known Limitations](#known-limitations)
7. [Version History](#version-history)

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
- **Restaurant GUID** (e.g., `rest-guid-123`)

### Step 3: Test Locally (Optional)

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

Both endpoints require **owner authentication**. Credentials are stored encrypted in the database, not in `.env`.

The owner enters Toast credentials through the UI (Integrations page), which encrypts and stores them before making API calls.

**Test with curl:**

```bash
# After authenticating as owner, get auth token from response headers
curl -H "Authorization: Bearer <your-auth-token>" \
  http://localhost:8000/api/pos/toast/sales-summary?days=7

curl -H "Authorization: Bearer <your-auth-token>" \
  http://localhost:8000/api/pos/toast/menu
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
6. Retrieve your **Restaurant GUID** from Toast's restaurant settings

### Storing Credentials in powr

Credentials are stored in the `pos_credentials` table and encrypted at rest. They are:

- **Never** sent to the frontend
- **Only** accessible to endpoints marked as owner-only
- **Automatically** decrypted when needed for API calls
- **Validated** on first use

## Scopes

Toast Standard API provides **read-only access** to:

- **Orders**: Order history with line items, modifiers, timestamps, and prices
- **Menus**: Menu items, prices, and modifier groups
- **Stock**: Real-time stock availability and limitations

Scopes are **not** explicitly restricted; access is determined by the application level.

## Endpoints

### GET /api/pos/toast/sales-summary

**Authorization**: Owner only

**Description**: Fetch and summarize sales data for the past N days from Toast.

**Query Parameters**:
- `days` (integer, optional, default=30): Number of days to pull (range: 1–365)

**Response** (200 OK):
```json
{
  "days": 30,
  "start_date": "2026-09-11",
  "end_date": "2026-10-11",
  "total_orders": 150,
  "total_items": 450,
  "total_revenue": 4500.00,
  "daily_stats": [
    {
      "date": "2026-09-11",
      "orders": 5,
      "items": 15,
      "revenue": 150.00
    },
    {
      "date": "2026-09-12",
      "orders": 6,
      "items": 18,
      "revenue": 180.00
    }
  ]
}
```

**Error Responses**:
- `401 Unauthorized`: Toast credentials invalid or not configured
- `404 Not Found`: Toast credentials or restaurant connection not configured
- `422 Unprocessable Entity`: Invalid query parameters (e.g., days=0 or days=999)
- `502 Bad Gateway`: Toast API error (rate limited, down, etc.)

**Notes**:
- Does NOT save data to the database (designed for ad-hoc reporting)
- Splits date ranges into 7-day windows due to Toast API limits
- Voided/refunded items are included (ingredient usage still occurred)
- Revenue is a sum of line prices; discounts are reflected in line-level prices

### GET /api/pos/toast/menu

**Authorization**: Owner only

**Description**: Fetch the restaurant's menu items from Toast, including prices and modifier groups.

**Response** (200 OK):
```json
{
  "currency": "CAD",
  "items": [
    {
      "item_id": "item-guid-123",
      "item_name": "Chicken Gyro Plate",
      "price": 14.99,
      "currency": "CAD",
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
- `401 Unauthorized`: Toast credentials invalid or not configured
- `404 Not Found`: Toast credentials or restaurant connection not configured
- `502 Bad Gateway`: Toast API error

**Notes**:
- Returns all menu items visible to the Standard API
- Prices are base menu prices; dynamic pricing (by size, etc.) appears only at sale time
- Modifier options with `null` price are priced by customer choice or included with the item
- Items are ordered as they appear in Toast's menu structure

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

1. **Date Range**: The ordersBulk endpoint rejects date ranges longer than 30 days. powr splits requests into 7-day windows.
2. **Page Size**: Maximum 100 orders per page; pagination is automatic.
3. **Rate Limiting**: Toast enforces rate limits; powr retries with exponential backoff.

### Data Gaps

1. **Ingredient Recipes**: Toast does not provide recipe/ingredient mappings; powr manages these separately in the `recipes` table.
2. **Stock Details**: Stock endpoint returns only items that are out of stock or have limits; in-stock items are not included.
3. **Discounts**: Line-level prices reflect discounts, but the original full price is not available.
4. **Modifiers**: Modifier pricing appears only on sold items; modifier group pricing rules are not exposed.
5. **Menu Availability**: Menu endpoint returns the full menu; real-time availability (after hours, etc.) must be managed separately.

### Item Name Fallback

If Toast returns an order or menu item without a name, powr uses the constant `MISSING_NAME` ("Missing name") as a placeholder.

## Version History

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
- Credentials and connection configuration validated on startup
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
│       └── retry.py          # Retry policy (rate limit, backoff)
├── api/
│   └── toast.py              # REST endpoints
├── modules/pos/
│   ├── service.py            # Credential management
│   └── repository.py         # Database queries
└── schemas/pos.py            # Pydantic response models
```

### Retry Strategy

Toast client implements exponential backoff for:
- HTTP 429 (rate limit)
- HTTP 5xx (server errors)
- Network timeouts

**Policy**:
- Initial backoff: 1 second
- Maximum backoff: 60 seconds
- Jitter: ±10%
- Max retries: 5

### Encryption

Toast credentials are encrypted at rest in the `pos_credentials` table:
- **Storage**: encrypted_client_secret, encrypted_access_token
- **Context**: Unique encryption context per credential (`pos_credentials:<pos_name>:<field>`)
- **Decryption**: Automatic on retrieval for server-side use; never sent to frontend
