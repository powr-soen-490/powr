# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Fetching Toast orders one business day at a time, checked against a real recorded week."""

from datetime import date, timedelta

import httpx2
import pytest

from app.integrations.pos.toast.client import LOGIN_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from tests.unit.toast_fakes import CONNECTION, RECORDED_WEEK_DIR, FakeToast

NOV_9 = date(2026, 11, 9)
RECORDED_DAYS = [NOV_9 + timedelta(days=offset) for offset in range(7)]


def recorded_orders(day: date) -> httpx2.Response:
    return httpx2.Response(200, text=(RECORDED_WEEK_DIR / f"orders/{day}.json").read_text())


def test_fetch_orders_for_business_date_asks_toast_for_that_day() -> None:
    toast = FakeToast()
    toast.reply(ORDERS_PATH, recorded_orders(NOV_9))

    lines = toast.adapter().fetch_orders_for_business_date(NOV_9)

    assert len(lines) == 110
    assert sum(line.is_voided for line in lines) == 1
    assert {line.connection_id for line in lines} == {CONNECTION.id}
    assert {line.restaurant_id for line in lines} == {CONNECTION.restaurant_id}
    [request] = toast.requests_to(ORDERS_PATH)
    assert request.url.params["businessDate"] == "20261109"
    assert "startDate" not in request.url.params


@pytest.mark.parametrize("day", RECORDED_DAYS, ids=str)
def test_every_recorded_line_belongs_to_the_day_asked_for(day: date) -> None:
    toast = FakeToast()
    toast.reply(ORDERS_PATH, recorded_orders(day))

    lines = toast.adapter().fetch_orders_for_business_date(day)

    assert lines
    assert {line.business_date for line in lines} == {day}


def test_one_login_covers_many_days() -> None:
    toast = FakeToast()
    toast.reply(ORDERS_PATH, *(recorded_orders(day) for day in RECORDED_DAYS))

    with toast.adapter() as adapter:
        for day in RECORDED_DAYS:
            adapter.fetch_orders_for_business_date(day)

    assert len(toast.requests_to(LOGIN_PATH)) == 1
    asked = [request.url.params["businessDate"] for request in toast.requests_to(ORDERS_PATH)]
    assert asked == [day.strftime("%Y%m%d") for day in RECORDED_DAYS]


def test_a_day_without_orders_has_no_lines() -> None:
    toast = FakeToast()
    toast.reply(ORDERS_PATH, httpx2.Response(200, json=[]))

    assert toast.adapter().fetch_orders_for_business_date(date(2024, 1, 1)) == []
