"""Bounded local schedule contract. No provider or presentation dependencies."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


class ScheduleConflict(ValueError):
    pass


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def text(value, name, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Invalid {name}")
    return value.strip()


def zone(value):
    try:
        return ZoneInfo(text(value, "timezone", 100))
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown IANA timezone") from exc


def day(value):
    if not isinstance(value, str):
        raise ValueError("Date must be ISO YYYY-MM-DD")
    result = date.fromisoformat(value)
    if result.isoformat() != value or result.year > 9998:
        raise ValueError("Date must be ISO YYYY-MM-DD, before year 9999")
    return result


def aware(value):
    if not isinstance(value, str):
        raise ValueError("Datetime must be an ISO string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None or result.year > 9998:
        raise ValueError("Timezone-aware datetime required")
    return result


def localize(value: datetime, tz: ZoneInfo):
    """Choose fold=0; a gap is never silently moved to another wall time."""
    result = value.replace(tzinfo=tz, fold=0)
    if result.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != value:
        raise ValueError("Nonexistent local time (DST gap)")
    return result


def validate_item(raw):
    if not isinstance(raw, dict):
        raise ValueError("item must be an object")
    allowed = {"title", "notes", "kind", "timezone", "allDay", "start", "end", "due",
               "trackCompletion", "recurrence", "notification"}
    if set(raw) - allowed:
        raise ValueError("Unknown schedule fields")
    out = dict(raw)
    out["title"] = text(out.get("title"), "title", 300)
    if not isinstance(out.get("notes", ""), str) or len(out.get("notes", "")) > 2000:
        raise ValueError("Invalid notes")
    out.setdefault("notes", "")
    if out.get("kind") not in {"event", "study", "deadline"}:
        raise ValueError("Unknown schedule kind")
    tz = zone(out.get("timezone"))
    out.setdefault("allDay", False)
    out.setdefault("trackCompletion", out["kind"] != "event")
    if type(out["allDay"]) is not bool or type(out["trackCompletion"]) is not bool:
        raise ValueError("Boolean fields required")
    fields = ("due",) if out["kind"] == "deadline" else ("start", "end")
    if any(key in out for key in {"start", "end", "due"} - set(fields)):
        raise ValueError("Deadline and interval fields cannot be mixed")
    parsed = []
    for key in fields:
        value = day(out.get(key)) if out["allDay"] else aware(out.get(key))
        if not out["allDay"]:
            # Reject offsets that describe a different wall time in the declared zone.
            converted = value.astimezone(tz)
            if converted.replace(tzinfo=None) != value.replace(tzinfo=None) or converted.utcoffset() != value.utcoffset():
                raise ValueError("Datetime offset must match schedule timezone")
            localize(value.replace(tzinfo=None), tz)
        parsed.append(value)
        out[key] = value.isoformat()
    if len(parsed) == 2 and (parsed[1].astimezone(UTC) <= parsed[0].astimezone(UTC) if not out["allDay"] else parsed[1] <= parsed[0]):
        raise ValueError("end must be after start")
    recurrence = out.get("recurrence")
    if recurrence is not None:
        if not isinstance(recurrence, dict) or set(recurrence) - {"frequency", "interval", "weekdays", "until", "count"}:
            raise ValueError("Invalid recurrence")
        recurrence = dict(recurrence)
        if recurrence.get("frequency") not in {"daily", "weekly", "monthly"}:
            raise ValueError("Unknown recurrence frequency")
        recurrence["interval"] = integer(recurrence.get("interval", 1), "interval", 1, 120)
        if "count" in recurrence and "until" in recurrence:
            raise ValueError("Choose count or until")
        if "count" in recurrence:
            integer(recurrence["count"], "count", 1, 100000)
        if "until" in recurrence and day(recurrence["until"]) < anchor_date(out):
            raise ValueError("until precedes anchor")
        if recurrence["frequency"] == "weekly":
            weekdays = recurrence.get("weekdays")
            if not isinstance(weekdays, list) or not weekdays or len(weekdays) > 7:
                raise ValueError("Weekly recurrence needs weekdays")
            recurrence["weekdays"] = sorted(set(integer(x, "weekday", 0, 6) for x in weekdays))
        elif "weekdays" in recurrence:
            raise ValueError("weekdays only applies to weekly rules")
        out["recurrence"] = recurrence
    else:
        out["recurrence"] = None
    notification = out.get("notification", {"enabled": False})
    if not isinstance(notification, dict) or set(notification) - {"enabled", "minutesBefore", "allDayTime", "channel"}:
        raise ValueError("Invalid notification preference")
    notification = dict(notification)
    if type(notification.get("enabled")) is not bool:
        raise ValueError("notification.enabled must be boolean")
    notification.setdefault("minutesBefore", 10)
    integer(notification["minutesBefore"], "minutesBefore", 0, 10080)
    notification.setdefault("allDayTime", "09:00")
    clock = time.fromisoformat(notification["allDayTime"])
    if clock.tzinfo or clock.isoformat(timespec="minutes") != notification["allDayTime"]:
        raise ValueError("allDayTime must be HH:MM")
    notification.setdefault("channel", "panel")
    if notification["channel"] not in {"panel", "desktop"}:
        raise ValueError("Unknown notification channel")
    out["notification"] = notification
    return out


def anchor_date(item):
    value = item["due" if item["kind"] == "deadline" else "start"]
    return day(value) if item["allDay"] else aware(value).date()


def matches(item, candidate):
    anchor = anchor_date(item)
    if candidate < anchor:
        return False
    rule = item["recurrence"]
    if not rule:
        return candidate == anchor
    if rule.get("until") and candidate > day(rule["until"]):
        return False
    interval = rule["interval"]
    if rule["frequency"] == "daily":
        return (candidate - anchor).days % interval == 0
    if rule["frequency"] == "weekly":
        monday = anchor - timedelta(days=anchor.weekday())
        return ((candidate - monday).days // 7) % interval == 0 and candidate.weekday() in rule["weekdays"]
    return candidate.day == anchor.day and ((candidate.year-anchor.year)*12 + candidate.month-anchor.month) % interval == 0


def occurrence(item, candidate):
    result = dict(item)
    shift = candidate - anchor_date(item)
    for key in ("due",) if item["kind"] == "deadline" else ("start", "end"):
        if item["allDay"]:
            result[key] = (day(item[key]) + shift).isoformat()
        else:
            wall = aware(item[key]).replace(tzinfo=None) + shift
            result[key] = localize(wall, zone(item["timezone"])).isoformat()
    result["recurrence"] = None
    return result


def bounds(item):
    tz = zone(item["timezone"])
    def instant(key):
        return (datetime.combine(day(item[key]), time.min, tz) if item["allDay"] else aware(item[key])).astimezone(UTC)
    if item["kind"] == "deadline":
        start = instant("due")
        end = datetime.combine(day(item["due"]) + timedelta(days=1), time.min, tz).astimezone(UTC) if item["allDay"] else start
        return start, end
    return instant("start"), instant("end")


def prepare_item(raw):
    """Translate explicit wall-time form input at the domain boundary, then validate."""
    if not isinstance(raw,dict):
        raise ValueError("item must be an object")
    item = dict(raw)
    if not item.get("allDay",False):
        tz = zone(item.get("timezone"))
        for field in ("due",) if item.get("kind") == "deadline" else ("start","end"):
            value = item.get(field)
            if not isinstance(value,str):
                raise ValueError("Date and time required")
            parsed = datetime.fromisoformat(value)
            item[field] = (localize(parsed,tz) if parsed.tzinfo is None else parsed).isoformat()
    return validate_item(item)
