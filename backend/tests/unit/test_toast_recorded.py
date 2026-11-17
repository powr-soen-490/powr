# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The recorded-week stand-in for Toast, used for local development without credentials."""

from datetime import UTC, date, datetime

import pytest

from app.core.config import Settings
from app.integrations.pos.toast import recorded
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import ToastCredentials
from app.integrations.pos.toast.locations import find_toast_locations
from app.integrations.pos.toast.recorded import RECORDED_RESTAURANT_NAME, recorded_toast_transport
from app.integrations.pos.toast.recording import FAKE_RESTAURANT_GUID
from app.modules.pos import service
from tests.unit.toast_fakes import CONNECTION, RECORDED_WEEK_DIR

ANY_LOGIN = ToastCredentials(client_id="anything", client_secret="anything")


def recorded_adapter() -> ToastAdapter:
    return ToastAdapter(
        CONNECTION,
        ANY_LOGIN,
        currency="USD",
        base_url="https://toast.test",
        transport=recorded_toast_transport(),
    )


def test_the_app_reads_the_same_recorded_week_as_the_tests() -> None:
    assert RECORDED_WEEK_DIR.resolve() == recorded.RECORDED_WEEK_DIR
    assert (recorded.RECORDED_WEEK_DIR / "menus.json").is_file()


def test_any_login_connects_to_the_recorded_restaurant() -> None:
    [location] = find_toast_locations(
        ANY_LOGIN, base_url="https://toast.test", transport=recorded_toast_transport()
    )

    assert (location.location_id, location.name) == (FAKE_RESTAURANT_GUID, RECORDED_RESTAURANT_NAME)


def test_the_adapter_reads_the_recorded_menu_and_days() -> None:
    with recorded_adapter() as adapter:
        assert adapter.authenticate()
        assert len(adapter.fetch_menu_items()) == 214
        assert len(adapter.fetch_orders_for_business_date(date(2026, 11, 9))) == 110
        assert len(adapter.fetch_orders_for_business_date(date(2026, 11, 15))) == 93
        # Days outside the recording have no orders.
        assert adapter.fetch_orders_for_business_date(date(2024, 1, 1)) == []
        assert adapter.fetch_stock_items() == []


def test_date_range_requests_get_no_orders() -> None:
    """The files are split by business day, so the old date-range fetch finds nothing."""
    start = datetime(2026, 11, 9, tzinfo=UTC)
    with recorded_adapter() as adapter:
        assert adapter.fetch_orders(start, datetime(2026, 11, 16, tzinfo=UTC)) == []


@pytest.mark.parametrize("use_recorded_data", [True, False])
def test_the_setting_picks_recorded_data_or_the_real_toast(
    monkeypatch: pytest.MonkeyPatch, use_recorded_data: bool
) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://powr:powr@localhost:5432/powr",
        toast_use_recorded_data=use_recorded_data,
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)

    assert (service.toast_transport() is not None) == use_recorded_data
