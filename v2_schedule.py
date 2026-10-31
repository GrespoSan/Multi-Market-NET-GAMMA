"""SPX-equivalent three-slot V2 scheduler with explicit Rome/Chicago zones.

Keep historical logical labels 15:50 and 20:30, but use US-market-clock
08:50 and 13:30 America/Chicago, including DST mismatches.
07:30 remains 07:30 Europe/Rome. A run delayed beyond 12 minutes is
logged, never backdated to an official snapshot.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
CHICAGO = ZoneInfo("America/Chicago")
INSTRUMENTS = ("NDX", "GLD", "USO")
MAX_LAG_SECONDS = 12 * 60

SLOTS = {
    "07:30": ("Europe/Rome", 7, 30, "30 7 * * 1-5"),
    "15:50": ("America/Chicago", 8, 50, "50 8 * * 1-5"),
    "20:30": ("America/Chicago", 13, 30, "30 13 * * 1-5"),
}
SLOT_FOR_CRON = {values[3]: label for label, values in SLOTS.items()}


def decision(now: datetime, requested=None, event_cron=None, manual=False):
    if now.tzinfo is None:
        raise ValueError("Il timestamp di esecuzione deve avere un fuso orario.")
    roma = now.astimezone(ROME)
    chicago = now.astimezone(CHICAGO)
    if requested and requested not in SLOTS:
        raise ValueError("Slot logico non riconosciuto.")
    if event_cron:
        canonical = SLOT_FOR_CRON.get(event_cron)
        if not canonical:
            raise ValueError("Evento cron GitHub non riconosciuto.")
        if requested and requested != canonical:
            raise ValueError("Slot richiesto incoerente con evento GitHub.")
        requested = canonical
    if manual:
        return {"run": True, "reason": "MANUALE", "slot": "manuale",
                "rome": roma, "chicago": chicago,
                "requested_slot": requested or "", "time_zone": "manuale"}
    if roma.weekday() >= 5:
        return {"run": False, "reason": "WEEKEND", "slot": requested or "",
                "rome": roma, "chicago": chicago, "time_zone": ""}
    candidates = (requested,) if requested else tuple(SLOTS)
    for label in candidates:
        zone, hour, minute, _ = SLOTS[label]
        clock = roma if zone == "Europe/Rome" else chicago
        scheduled = clock.replace(hour=hour, minute=minute,
                                  second=0, microsecond=0)
        lag = (clock - scheduled).total_seconds()
        if 0 <= lag <= MAX_LAG_SECONDS:
            return {"run": True, "reason": "IN_WINDOW", "slot": label,
                    "rome": roma, "chicago": chicago,
                    "requested_slot": requested or label,
                    "time_zone": zone,
                    "scheduled_local": scheduled.isoformat(),
                    "lag_seconds": int(lag)}
        # GitHub schedules were delayed by 5+ hours on Oct 30: the old
        # 12-minute hard stop caused success status but ZERO option files.
        # A scheduled EVENT may capture its *actual* timestamp if delayed,
        # on the same market calendar day. NEVER backdate the observation.
        # Manual/non-cron invocations still require the normal window.
        if event_cron and requested == label and lag > MAX_LAG_SECONDS:
            if scheduled.date() == clock.date():
                return {"run": True, "reason": "GITHUB_SCHEDULE_DELAYED",
                        "slot": label, "rome": roma, "chicago": chicago,
                        "requested_slot": label, "time_zone": zone,
                        "scheduled_local": scheduled.isoformat(),
                        "lag_seconds": int(lag)}
    return {"run": False,
            "reason": "FUORI_FINESTRA" if requested else "NESSUNO_SLOT",
            "slot": requested or "", "rome": roma, "chicago": chicago,
            "requested_slot": requested or "", "time_zone": (
                SLOTS[requested][0] if requested else "")}
