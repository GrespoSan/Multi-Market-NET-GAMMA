"""Timezone-safe Multi-Market scheduled collection of *authorized* option feeds.

NOTE: Cboe delayed_quotes pages explicitly prohibit automated extraction.
This module NEVER uses their public delayed-quote endpoint for scheduled jobs.
Feed URLs and authorization must be configured separately by the owner.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
SLOTS = ("07:30", "15:50", "20:30")
INSTRUMENTS = ("NDX", "GLD", "USO")
MAX_LAG_SECONDS = 12 * 60


def schedule_decision(now: datetime, requested: str | None = None, manual: bool = False):
    if now.tzinfo is None:
        raise ValueError("Scheduled acquisitions require timezone-aware timestamps.")
    local = now.astimezone(ROME)
    if local.weekday() > 4:
        if manual:
            return {"run": True, "reason": "MANUALE_WEEKEND", "slot": "manuale",
                    "rome": local, "requested": requested or ""}
        return {"run": False, "reason": "WEEKEND", "slot": "", "rome": local}
    eligible = []
    for slot in SLOTS:
        hour, minute = map(int, slot.split(":"))
        planned = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = (local - planned).total_seconds()
        if 0 <= delta <= MAX_LAG_SECONDS:
            eligible.append(slot)
    if requested and requested not in SLOTS:
        raise ValueError("Slot richiesto non previsto.")
    if manual:
        return {"run": True, "reason": "MANUALE",
                "slot": "manuale", "rome": local, "requested": requested or ""}
    if requested in eligible:
        return {"run": True, "reason": "IN_WINDOW", "slot": requested, "rome": local}
    if requested:
        return {"run": False, "reason": "LATE_OR_WRONG_SLOT",
                "slot": requested, "rome": local}
    if eligible:
        return {"run": True, "reason": "IN_WINDOW", "slot": eligible[0], "rome": local}
    return {"run": False, "reason": "OUT_OF_WINDOW", "slot": "", "rome": local}


def week_key(local: datetime) -> str:
    year, week, _ = local.isocalendar()
    return f"{year}-W{week:02d}"
