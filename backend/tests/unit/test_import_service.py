# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Which business day an import can safely end on."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.modules.pos.import_service import last_finished_business_day

NEW_YORK_WINTER = timezone(timedelta(hours=-5))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Monday 10am in New York: Sunday's business day ended at closing, early this morning.
        (datetime(2026, 11, 16, 10, 0, tzinfo=NEW_YORK_WINTER), date(2026, 11, 15)),
        # Monday 3am in New York: Sunday night service may still be open.
        (datetime(2026, 11, 16, 3, 0, tzinfo=NEW_YORK_WINTER), date(2026, 11, 14)),
        # Monday 7:30pm in New York (already Tuesday in UTC): Monday is still going.
        (datetime(2026, 11, 16, 19, 30, tzinfo=NEW_YORK_WINTER), date(2026, 11, 15)),
        (datetime(2026, 11, 17, 15, 0, tzinfo=UTC), date(2026, 11, 16)),
    ],
)
def test_last_finished_business_day_never_includes_a_day_still_open(
    now: datetime, expected: date
) -> None:
    assert last_finished_business_day(now) == expected
