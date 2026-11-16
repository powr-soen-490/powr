# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Argument validation and output shape of the mock POS data generator."""

import random
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import mean
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.pos import mock
from app.integrations.pos.models import MenuItem, SaleLine

RESTAURANT = uuid4()


@pytest.fixture(autouse=True)
def development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mock, "get_settings", lambda: SimpleNamespace(environment="development"))


def run(tmp_path: Path, *args: str) -> None:
    mock.main(["--restaurant", str(RESTAURANT), "--out-dir", str(tmp_path), *args])


def run_sales(tmp_path: Path, start: str = "2026-10-01", end: str = "2026-10-07") -> None:
    run(tmp_path, "--type", "sales", "--start", start, "--end", end, "--seed", "1")


def read_menu(tmp_path: Path) -> list[MenuItem]:
    return mock.MENU_ADAPTER.validate_json((tmp_path / str(RESTAURANT) / "menu.json").read_bytes())


def read_sales(tmp_path: Path) -> list[SaleLine]:
    return mock.SALES_ADAPTER.validate_json(
        (tmp_path / str(RESTAURANT) / "sales.json").read_bytes()
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--restaurant", str(RESTAURANT)],
        ["--restaurant", "not-a-uuid", "--type", "menu"],
        ["--restaurant", str(RESTAURANT), "--type", "stock"],
        ["--restaurant", str(RESTAURANT), "--type", "sales"],
        ["--restaurant", str(RESTAURANT), "--type", "sales", "--start", "2026-10-01"],
        ["--restaurant", str(RESTAURANT), "--type", "sales", "--start", "Oct 1", "--end", "x"],
        [
            *("--restaurant", str(RESTAURANT), "--type", "sales"),
            *("--start", "2026-10-08", "--end", "2026-10-01"),
        ],
    ],
)
def test_rejects_invalid_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        mock.main(argv)
    assert exc.value.code == 2


def test_disabled_in_production(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mock, "get_settings", lambda: SimpleNamespace(environment="production"))
    with pytest.raises(SystemExit, match="disabled in production"):
        run(tmp_path, "--type", "menu")
    assert not tmp_path.joinpath(str(RESTAURANT)).exists()


def test_sales_without_menu_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="run with --type menu first"):
        run_sales(tmp_path)


def test_menu_is_one_real_restaurant_menu(tmp_path: Path) -> None:
    run(tmp_path, "--type", "menu", "--seed", "1")
    menu = read_menu(tmp_path)
    names = [(item.item_name, item.price) for item in menu]
    assert names in mock._dataset_menus().values()
    assert all(item.is_mock and item.restaurant_id == RESTAURANT for item in menu)


def test_menu_depends_on_seed() -> None:
    def names(seed: int) -> list[str]:
        return [item.item_name for item in mock.generate_menu(RESTAURANT, random.Random(seed))]

    assert names(1) == names(1)
    assert len({tuple(names(seed)) for seed in range(10)}) > 1


def test_popularity_is_stable_positive_and_ignores_price() -> None:
    menu = mock.generate_menu(RESTAURANT, random.Random(1))
    weights = mock.popularity_weights(menu)
    assert weights == mock.popularity_weights(menu)
    assert all(weight > 0 for weight in weights)
    repriced = [item.model_copy(update={"price": Decimal("99")}) for item in menu]
    assert mock.popularity_weights(repriced) == weights


def test_popularity_distribution_differs_per_restaurant() -> None:
    menu = mock.generate_menu(RESTAURANT, random.Random(1))
    other = [item.model_copy(update={"restaurant_id": uuid4()}) for item in menu]
    assert mean(mock.popularity_weights(other)) != mean(mock.popularity_weights(menu))


def test_sales_match_domain_model_and_menu(tmp_path: Path) -> None:
    run(tmp_path, "--type", "menu")
    run_sales(tmp_path)
    menu_ids = {item.item_id for item in read_menu(tmp_path)}
    sales = read_sales(tmp_path)
    assert sales
    assert {line.item_id for line in sales} <= menu_ids
    assert {line.business_date for line in sales} == {date(2026, 10, d) for d in range(1, 8)}
    assert all(line.is_mock and line.restaurant_id == RESTAURANT for line in sales)


def test_same_seed_gives_same_output(tmp_path: Path) -> None:
    run(tmp_path, "--type", "menu")
    run_sales(tmp_path)
    first = (tmp_path / str(RESTAURANT) / "sales.json").read_bytes()
    run_sales(tmp_path)
    assert (tmp_path / str(RESTAURANT) / "sales.json").read_bytes() == first


def test_sales_have_weekend_and_meal_peaks() -> None:
    menu = mock.generate_menu(RESTAURANT, random.Random(7))
    sales = mock.generate_sales(menu, date(2026, 9, 7), date(2026, 10, 4), random.Random(7))
    orders_by_day: dict[date, set[str]] = {}
    for line in sales:
        orders_by_day.setdefault(line.business_date, set()).add(line.order_id)
    weekend = mean(len(o) for d, o in orders_by_day.items() if d.weekday() >= 4)
    weekday = mean(len(o) for d, o in orders_by_day.items() if d.weekday() < 4)
    assert weekend > weekday
    hours = [line.timestamp.astimezone(mock.MOCK_TIMEZONE).hour for line in sales]
    assert all(11 <= h <= 14 or 17 <= h <= 21 for h in hours)


def test_generate_sales_requires_menu() -> None:
    with pytest.raises(ValueError, match="without menu items"):
        mock.generate_sales([], date(2026, 10, 1), date(2026, 10, 1), random.Random(1))
