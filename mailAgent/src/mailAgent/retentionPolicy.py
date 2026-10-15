"""Rolling IMAP retention policy calculations."""

from calendar import monthrange
from datetime import date


def retentionCutoff(today: date, months: int) -> date:
    """Return the inclusive rolling-retention cutoff using calendar months."""
    if not isinstance(today, date):
        raise ValueError("Retention cutoff requires a calendar date")
    if type(months) is not int or not 1 <= months <= 120:
        raise ValueError("imapRetentionMonths must be between 1 and 120")

    monthIndex = today.year * 12 + (today.month - 1) - months
    year, zeroBasedMonth = divmod(monthIndex, 12)
    month = zeroBasedMonth + 1
    day = min(today.day, monthrange(year, month)[1])
    return date(year, month, day)


def retentionArchiveEligible(messageDate: date, cutoff: date) -> bool:
    """Return True only when a message date is strictly older than the cutoff."""
    if not isinstance(messageDate, date) or not isinstance(cutoff, date):
        raise ValueError("Retention eligibility requires calendar dates")
    return messageDate < cutoff
