"""Reporting dates resolved at call time, never frozen when a server imports a module."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Los_Angeles")


def runtime_date():
    return datetime.now(TIMEZONE).date()


def latest_completed_week(reference=None):
    reference = reference or runtime_date()
    this_sunday = reference - timedelta(days=(reference.weekday() + 1) % 7)
    return this_sunday - timedelta(days=7)


def dataset_window(reference=None):
    latest = latest_completed_week(reference)
    return latest - timedelta(weeks=51), latest + timedelta(days=6)


def synthetic_holidays(start, end):
    holidays = set()
    for year in range(start.year, end.year + 1):
        november = date(year, 11, 1)
        thanksgiving = november + timedelta(days=(3 - november.weekday()) % 7 + 21)
        may_end = date(year, 5, 31)
        september = date(year, 9, 1)
        independence = date(year, 7, 4)
        observed = independence + timedelta(days=-1 if independence.weekday() == 5 else 1 if independence.weekday() == 6 else 0)
        holidays.update({date(year, 1, 1), thanksgiving, thanksgiving + timedelta(days=1),
                         date(year, 12, 25), date(year, 12, 26),
                         may_end - timedelta(days=may_end.weekday()), observed,
                         september + timedelta(days=(-september.weekday()) % 7)})
    return holidays
