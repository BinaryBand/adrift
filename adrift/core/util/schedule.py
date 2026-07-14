from datetime import datetime, timedelta

from dateutil.rrule import rrulestr


def align_to_tzinfo(reference: datetime, target: datetime) -> datetime:
    """Align target tz-awareness to reference while preserving clock time."""
    state = (reference.tzinfo is None, target.tzinfo is None)
    if state == (False, True):
        return target.replace(tzinfo=reference.tzinfo)
    if state == (True, False):
        return target.replace(tzinfo=None)
    return target


def next_occurrence_in_window(schedule: str, day_start: datetime) -> datetime | None:
    """Return the first schedule occurrence at-or-after day_start."""
    if "DTSTART" in schedule.upper():
        rule = rrulestr(schedule)
        rule_start = getattr(rule, "_dtstart", None)
        if isinstance(rule_start, datetime):
            day_start = align_to_tzinfo(rule_start, day_start)
    else:
        rule = rrulestr(schedule, dtstart=day_start)
    return rule.after(day_start - timedelta(microseconds=1), inc=True)


def rrule_occurrence_exists(rule_str: str, day_start: datetime, day_end: datetime) -> bool:
    """Return True if rule_str has an occurrence within [day_start, day_end)."""
    try:
        occurrence = next_occurrence_in_window(rule_str, day_start)
        if occurrence is None:
            return False
        return occurrence < align_to_tzinfo(occurrence, day_end)
    except (TypeError, ValueError):
        return False
