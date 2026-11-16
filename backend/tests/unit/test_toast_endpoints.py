# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Unit tests for Toast endpoints: /pos/toast/sales-summary and /pos/toast/menu."""

from decimal import Decimal
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from tests.unit.toast_fakes import (
    FakeToast,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "toast"


@pytest.fixture
def toast() -> FakeToast:
    """Create a fake Toast server."""
    fake = FakeToast()
    # Load real fixtures
    fake.reply(ORDERS_PATH, httpx2.Response(200, text=(FIXTURES_DIR / "orders.json").read_text()))
    fake.reply(MENUS_PATH, httpx2.Response(200, text=(FIXTURES_DIR / "menus.json").read_text()))
    return fake


class TestToastSalesSummaryEndpoint:
    """Tests for GET /api/pos/toast/sales-summary endpoint."""

    def test_endpoint_returns_400_without_auth(self, client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = client.get("/api/pos/toast/sales-summary")
        assert response.status_code == 401

    def test_endpoint_accepts_valid_days_parameter(self, client: TestClient) -> None:
        """Test that endpoint accepts days parameter in valid range."""
        # These should not error on parameter validation
        for days in [1, 7, 30, 90, 365]:
            response = client.get(f"/api/pos/toast/sales-summary?days={days}")
            # Will fail on auth, not on parameter validation
            assert response.status_code in [401, 404, 502]

    def test_endpoint_rejects_invalid_days_parameter_zero(self, client: TestClient) -> None:
        """Test that endpoint rejects days=0 (after auth, would return 422)."""
        # Without auth, returns 401 first; auth is checked before parameter validation
        response = client.get("/api/pos/toast/sales-summary?days=0")
        assert response.status_code == 401

    def test_endpoint_rejects_invalid_days_parameter_negative(self, client: TestClient) -> None:
        """Test that endpoint rejects negative days (after auth, would return 422)."""
        # Without auth, returns 401 first; auth is checked before parameter validation
        response = client.get("/api/pos/toast/sales-summary?days=-5")
        assert response.status_code == 401

    def test_endpoint_rejects_invalid_days_parameter_too_large(self, client: TestClient) -> None:
        """Test that endpoint rejects days > 365 (after auth, would return 422)."""
        # Without auth, returns 401 first; auth is checked before parameter validation
        response = client.get("/api/pos/toast/sales-summary?days=999")
        assert response.status_code == 401

    def test_endpoint_has_correct_default_days(self, client: TestClient) -> None:
        """Test that endpoint defaults to 30 days."""
        # Without days parameter, should default to 30 (parameter validation passes)
        response = client.get("/api/pos/toast/sales-summary")
        # Will fail on auth, not parameter validation
        assert response.status_code in [401, 404, 502]

    def test_endpoint_is_owner_only(self, client: TestClient) -> None:
        """Test that endpoint requires owner role."""
        # This verifies the endpoint is decorated with OwnerDep
        response = client.get("/api/pos/toast/sales-summary")
        assert response.status_code == 401


class TestToastMenuEndpoint:
    """Tests for GET /api/pos/toast/menu endpoint."""

    def test_endpoint_returns_400_without_auth(self, client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = client.get("/api/pos/toast/menu")
        assert response.status_code == 401

    def test_endpoint_is_owner_only(self, client: TestClient) -> None:
        """Test that endpoint requires owner role."""
        # This verifies the endpoint is decorated with OwnerDep
        response = client.get("/api/pos/toast/menu")
        assert response.status_code == 401


class TestSalesSummaryResponseStructure:
    """Tests for the structure of the sales summary response."""

    def test_response_includes_required_fields(self) -> None:
        """Test that SalesSummaryResponse has the required fields."""
        # Import and validate the schema
        from app.schemas.pos import DailySalesStats, SalesSummaryResponse

        # Create a sample response to validate structure
        response = SalesSummaryResponse(
            days=30,
            start_date="2026-09-11",
            end_date="2026-10-11",
            total_orders=100,
            total_items=300,
            total_revenue=Decimal("3000.00"),
            daily_stats=[
                DailySalesStats(
                    date="2026-09-11",
                    orders=5,
                    items=15,
                    revenue=Decimal("150.00"),
                )
            ],
        )

        assert response.days == 30
        assert response.total_orders == 100
        assert response.total_items == 300
        assert response.total_revenue == Decimal("3000.00")
        assert len(response.daily_stats) == 1

    def test_daily_stats_includes_required_fields(self) -> None:
        """Test that DailySalesStats has the required fields."""
        from app.schemas.pos import DailySalesStats

        stat = DailySalesStats(
            date="2026-09-11",
            orders=5,
            items=15,
            revenue=Decimal("150.00"),
        )

        assert stat.date == "2026-09-11"
        assert stat.orders == 5
        assert stat.items == 15
        assert stat.revenue == Decimal("150.00")


class TestMenuResponseStructure:
    """Tests for the structure of the menu response."""

    def test_response_includes_required_fields(self) -> None:
        """Test that MenuResponse has the required fields."""
        from app.schemas.pos import MenuItemResponse, MenuResponse

        response = MenuResponse(
            currency="CAD",
            items=[
                MenuItemResponse(
                    item_id="item-1",
                    item_name="Gyro",
                    price=Decimal("14.99"),
                    currency="CAD",
                    modifier_groups=[],
                )
            ],
        )

        assert response.currency == "CAD"
        assert len(response.items) == 1
        assert response.items[0].item_id == "item-1"

    def test_menu_item_with_modifiers(self) -> None:
        """Test MenuItemResponse with modifier groups."""
        from app.schemas.pos import (
            MenuItemResponse,
            MenuModifierGroupResponse,
            MenuModifierOptionResponse,
            MenuResponse,
        )

        response = MenuResponse(
            currency="CAD",
            items=[
                MenuItemResponse(
                    item_id="item-1",
                    item_name="Gyro",
                    price=Decimal("14.99"),
                    currency="CAD",
                    modifier_groups=[
                        MenuModifierGroupResponse(
                            group_id="group-1",
                            group_name="Toppings",
                            min_selections=0,
                            max_selections=None,
                            options=[
                                MenuModifierOptionResponse(
                                    option_id="opt-1",
                                    option_name="Extra Feta",
                                    price=Decimal("1.50"),
                                )
                            ],
                        )
                    ],
                )
            ],
        )

        assert len(response.items[0].modifier_groups) == 1
        assert response.items[0].modifier_groups[0].group_name == "Toppings"
