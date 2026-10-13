"""Rolling IMAP retention policy tests."""

from datetime import date

import pytest

from mailAgent.retentionPolicy import retentionArchiveEligible, retentionCutoff


@pytest.mark.parametrize(
    "today,months,expected",
    [
        (date(2026, 10, 13), 12, date(2025, 10, 13)),
        (date(2026, 3, 31), 1, date(2026, 2, 28)),
        (date(2024, 3, 31), 1, date(2024, 2, 29)),
        (date(2024, 2, 29), 12, date(2023, 2, 28)),
        (date(2026, 1, 31), 13, date(2024, 12, 31)),
    ],
)
def testRetentionCutoffCalendarMonths(today, months, expected):
    assert retentionCutoff(today, months) == expected


def testRetentionBoundaryIsInclusive():
    cutoff = date(2025, 10, 13)
    assert retentionArchiveEligible(date(2025, 10, 12), cutoff)
    assert not retentionArchiveEligible(date(2025, 10, 13), cutoff)
    assert not retentionArchiveEligible(date(2025, 10, 14), cutoff)


@pytest.mark.parametrize("months", [0, -1, 121, 12.0, "12", None])
def testRetentionMonthsRejectInvalidValues(months):
    with pytest.raises(ValueError):
        retentionCutoff(date(2026, 10, 13), months)


def testRetentionEligibilityRejectsMissingDates():
    with pytest.raises(ValueError):
        retentionArchiveEligible(None, date(2025, 10, 13))
    with pytest.raises(ValueError):
        retentionArchiveEligible(date(2025, 10, 13), None)
