#!/usr/bin/env python
# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pull about 30 days of Mykonos Grill sales through the ToastAdapter and print a summary.

Logs in with TOAST_CLIENT_ID and TOAST_CLIENT_SECRET from .env. When the app is connected to
Toast with the same client ID, it reuses the app's saved token instead, so it needs no login.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Import from the backend app
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.integrations.pos.models import PosConnection  # noqa: E402
from app.integrations.pos.toast.adapter import ToastAdapter  # noqa: E402
from app.integrations.pos.toast.client import (  # noqa: E402
    ToastApiError,
    ToastAuthenticationError,
    ToastCredentials,
)
from app.integrations.pos.toast.token_store import MemoryTokenStore  # noqa: E402
from app.modules.pos.service import aggregate_sales  # noqa: E402
from app.modules.pos.toast_tokens import script_token_store  # noqa: E402


def main() -> None:
    settings = get_settings()

    # Placeholder credentials - in real usage, would be retrieved from database
    # For testing with Mykonos Grill, these would be set via environment or config
    client_id = settings.toast_client_id if hasattr(settings, "toast_client_id") else ""
    client_secret = settings.toast_client_secret if hasattr(settings, "toast_client_secret") else ""
    restaurant_guid = (
        settings.toast_restaurant_guid if hasattr(settings, "toast_restaurant_guid") else ""
    )

    if not all([client_id, client_secret, restaurant_guid]):
        print("Error: Toast credentials not configured in environment.")
        print("Set TOAST_CLIENT_ID, TOAST_CLIENT_SECRET, and TOAST_RESTAURANT_GUID")
        sys.exit(1)

    # Create a mock connection - in real usage, this would come from the database
    connection = PosConnection(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        restaurant_id=UUID("00000000-0000-0000-0000-000000000002"),
        provider="TOAST",
        location_id=restaurant_guid,
    )

    credentials = ToastCredentials(
        client_id=client_id,
        client_secret=client_secret,
    )

    with script_token_store(credentials.client_id) as token_store:
        if isinstance(token_store, MemoryTokenStore):
            print("The app has no saved Toast login for this client ID; logging in once.")
        else:
            print("Reusing the app's saved Toast login.")
        adapter = ToastAdapter(
            connection,
            credentials,
            currency="USD",
            base_url=settings.toast_api_base_url,
            token_store=token_store,
        )
        pull(adapter)


def pull(adapter: ToastAdapter) -> None:
    try:
        # Authenticate with Toast
        if not adapter.authenticate():
            print("Error: Failed to authenticate with Toast API")
            sys.exit(1)

        # Calculate 30-day window (end is now, start is 30 days ago)
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=30)

        print(f"\nPulling Toast sales data from {start_time.date()} to {end_time.date()}")
        print("=" * 80)

        # Fetch orders
        orders = adapter.fetch_orders(start_time, end_time)

        # Aggregate data by business date
        summary = aggregate_sales(orders, start_time.date(), end_time.date())

        # Print summary by day
        print("\n{:<12} {:<10} {:<12} {:<10}".format("Date", "Orders", "Items", "Revenue"))
        print("-" * 50)

        for date_str in sorted(summary.daily):
            stat = summary.daily[date_str]
            num_orders = len(stat["orders"])
            num_items = stat["items"]
            revenue = stat["revenue"]

            print(f"{date_str:<12} {num_orders:<10} {num_items:<12} ${revenue:>9.2f}")
        # Print totals
        print("-" * 50)
        print(
            "{:<12} {:<10} {:<12} ${:>9.2f}".format(
                "TOTAL", summary.total_orders, summary.total_items, summary.total_revenue
            )
        )
        print("\nSummary:")
        print(f"  Period: {start_time.date()} to {end_time.date()}")
        print(f"  Total Orders: {summary.total_orders}")
        print(f"  Total Items: {summary.total_items}")
        print(f"  Total Revenue: ${summary.total_revenue:.2f}")

    except ToastAuthenticationError as e:
        print(f"Error: Authentication failed - {e}")
        sys.exit(1)
    except ToastApiError as e:
        print(f"Error: Toast API error - {e}")
        sys.exit(1)
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
