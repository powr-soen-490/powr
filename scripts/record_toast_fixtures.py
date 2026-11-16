#!/usr/bin/env python
# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Record one week of real Toast orders plus the menu as scrubbed test data.

Uses a single Toast login. Needs TOAST_CLIENT_ID, TOAST_CLIENT_SECRET and
TOAST_RESTAURANT_GUID in the repository's .env. From backend/:

    python ../scripts/record_toast_fixtures.py                     # last full Monday-Sunday
    python ../scripts/record_toast_fixtures.py --start 2026-11-02  # 7 days from that date

The files go to backend/tests/fixtures/toast_week/. The repository is public, so read them
before committing them.
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.integrations.pos.models import PosConnection  # noqa: E402
from app.integrations.pos.toast.client import (  # noqa: E402
    ToastApiError,
    ToastClient,
    ToastCredentials,
)
from app.integrations.pos.toast.orders import sale_lines_from_order  # noqa: E402
from app.integrations.pos.toast.recording import (  # noqa: E402
    FAKE_RESTAURANT_GUID,
    RecordedDays,
    find_personal_data,
    record_days,
    to_json,
)

DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "toast_week"
# Only used to count sale lines in the summary; nothing is saved to the database.
SUMMARY_CONNECTION = PosConnection(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    restaurant_id=UUID("00000000-0000-0000-0000-000000000002"),
    provider="TOAST",
    location_id=FAKE_RESTAURANT_GUID,
)


def last_full_week(today: date) -> date:
    """The Monday of the last Monday-to-Sunday week that has fully ended."""
    return today - timedelta(days=today.weekday() + 7)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=date.fromisoformat, help="first business day")
    parser.add_argument("--days", type=int, default=7, help="how many days (default 7)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="output folder")
    parser.add_argument("--force", action="store_true", help="replace files already there")
    args = parser.parse_args()
    args.start = args.start or last_full_week(date.today())
    if not 1 <= args.days <= 31:
        parser.error("--days must be between 1 and 31")
    if args.start + timedelta(days=args.days - 1) >= date.today():
        parser.error("the last day must be before today, so its business day is finished")
    if recorded_files(args.out) and not args.force:
        parser.error(f"{args.out} already has files; pass --force to replace them")
    return args


def toast_client() -> tuple[ToastClient, str]:
    settings = get_settings()
    if settings.environment == "production":
        sys.exit("Recording Toast data is disabled in production.")
    client_id = settings.toast_client_id
    client_secret = settings.toast_client_secret
    restaurant_guid = settings.toast_restaurant_guid
    if not (client_id and client_secret and restaurant_guid):
        sys.exit("Set TOAST_CLIENT_ID, TOAST_CLIENT_SECRET and TOAST_RESTAURANT_GUID in .env.")
    credentials = ToastCredentials(client_id=client_id, client_secret=client_secret)
    client = ToastClient(credentials, restaurant_guid, base_url=settings.toast_api_base_url)
    return client, restaurant_guid


def recorded_files(out_dir: Path) -> list[Path]:
    """Files an earlier run saved; nothing else in the folder is ever touched."""
    menus = out_dir / "menus.json"
    return [*([menus] if menus.exists() else []), *(out_dir / "orders").glob("*.json")]


def write_files(recorded: RecordedDays, out_dir: Path) -> None:
    for old_file in recorded_files(out_dir):
        old_file.unlink()
    for relative_path, content in recorded.files().items():
        path = out_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_json(content), encoding="utf-8")


def print_summary(recorded: RecordedDays, out_dir: Path) -> None:
    print(f"\nSaved to {out_dir}")
    print(f"{'Business day':<14}{'Orders':>8}{'Sale lines':>12}")
    for day, orders in recorded.orders_by_day.items():
        lines = sum(len(list(sale_lines_from_order(o, SUMMARY_CONNECTION))) for o in orders)
        print(f"{day.isoformat():<14}{len(orders):>8}{lines:>12}")
    print("\nNext: open the files and check that nothing personal is in them before committing.")


def main() -> None:
    args = parse_args()
    last_day = args.start + timedelta(days=args.days - 1)
    print(f"Recording Toast orders from {args.start} to {last_day}, plus the menu...")
    client, restaurant_guid = toast_client()
    try:
        recorded = record_days(client, args.start, args.days, restaurant_guid)
    except ToastApiError as exc:
        sys.exit(f"Toast request failed: {exc}")
    finally:
        client.close()

    findings = find_personal_data(recorded.files())
    if findings:
        print("Stopped: these places look like personal data, so nothing was saved:")
        print("\n".join(f"  {finding}" for finding in findings))
        sys.exit(1)
    write_files(recorded, args.out)
    print_summary(recorded, args.out)


if __name__ == "__main__":
    main()
