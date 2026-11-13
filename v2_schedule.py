"""V2 three-slot scheduler with independent market-local clocks.

07:30 is Europe/Rome. Historic 15:50/17:00 = 08:50/10:00 Chicago.
Starting 16 Nov 2026 new 16:16/17:46 logical IDs = 09:16/10:46 Chicago,
including EU/US DST mismatch weeks. Capture via cron-job.org only.
Historical 20:30 records remain readable; no look-ahead or backdating.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
CHICAGO = ZoneInfo("America/Chicago")
INSTRUMENTS = ("NDX", "RUT", "DJX", "GLD", "USO")
MAX_LAG_SECONDS = 12 * 60
CHANGEOVER = date(2026, 11, 12)
CHANGEOVER_NEW = date(2026, 11, 16)

SLOTS = {
    "07:30": ("Europe/Rome", 7, 30, "30 7 * * 1-5"),
    "15:50": ("America/Chicago", 8, 50, "50 8 * * 1-5"),
    "17:00": ("America/Chicago", 10, 0, "0 10 * * 1-5"),
}
NEW_SLOTS = {
    "07:30": ("Europe/Rome", 7, 30, "30 7 * * 1-5"),
    "16:16": ("America/Chicago", 9, 16, "16 9 * * 1-5"),
    "17:46": ("America/Chicago", 10, 46, "46 10 * * 1-5"),
}
HISTORICAL_2030 = ("America/Chicago", 13, 30, "30 13 * * 1-5")


def slots_on_day(day):
    """Prospective scheduler; historical jobs remain identifiable."""
    return NEW_SLOTS if day >= CHANGEOVER_NEW else SLOTS
SLOT_FOR_CRON = {values[3]: label for label, values in
                 (SLOTS | NEW_SLOTS).items()}
SLOT_FOR_CRON[HISTORICAL_2030[3]] = "20:30"


def decision(now: datetime, requested=None, event_cron=None, manual=False, external=False):
    if now.tzinfo is None:
        raise ValueError("Il timestamp di esecuzione deve avere un fuso orario.")
    roma = now.astimezone(ROME)
    chicago = now.astimezone(CHICAGO)
    # cron-job.org may still dispatch its previously configured 20:30 job.
    # Skip it without producing new captures or falsifying the archive.
    if requested == "20:30" and roma.date() >= CHANGEOVER and not manual:
        return {"run": False, "reason": "SLOT_2030_DISMESSO",
                "slot": requested, "rome": roma, "chicago": chicago,
                "time_zone": "America/Chicago"}
    active = slots_on_day(roma.date())
    if requested and requested not in active and not (
            requested == "20:30" and roma.date() < CHANGEOVER):
        # No ambiguous assignment of old jobs to new time slots.
        # Obsolete cron-job.org triggers are ignored without a Cboe request.
        if requested in (SLOTS | NEW_SLOTS):
            return {"run": False, "reason": "SLOT_STORICO_O_NON_ANCORA_ATTIVO",
                    "slot": requested, "rome": roma, "chicago": chicago,
                    "time_zone": ""}
        raise ValueError("Slot logico non riconosciuto.")
    if external and (manual or event_cron or not requested):
        raise ValueError("cron-job.org richiede uno slot riconosciuto e non manuale.")
    if event_cron:
        # Native GitHub schedules have been removed; reject duplicate jobs.
        raise ValueError("Cron GitHub disabilitato: usare cron-job.org.")
    if manual:
        return {"run": True, "reason": "MANUALE", "slot": "manuale",
                "rome": roma, "chicago": chicago,
                "requested_slot": requested or "", "time_zone": "manuale"}
    if roma.weekday() >= 5:
        return {"run": False, "reason": "WEEKEND", "slot": requested or "",
                "rome": roma, "chicago": chicago, "time_zone": ""}
    eligible = dict(active)
    if roma.date() < CHANGEOVER:
        eligible["20:30"] = HISTORICAL_2030
    candidates = (requested,) if requested else tuple(eligible)
    for label in candidates:
        zone, hour, minute, _ = eligible[label]
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
        if external and requested == label and lag > MAX_LAG_SECONDS:
            if scheduled.date() == clock.date():
                return {"run": True, "reason": "EXTERNAL_DISPATCH_DELAYED",
                        "slot": label, "rome": roma, "chicago": chicago,
                        "requested_slot": label, "time_zone": zone,
                        "scheduled_local": scheduled.isoformat(),
                        "lag_seconds": int(lag)}
    return {"run": False,
            "reason": "FUORI_FINESTRA" if requested else "NESSUNO_SLOT",
            "slot": requested or "", "rome": roma, "chicago": chicago,
            "requested_slot": requested or "", "time_zone": (
                eligible[requested][0] if requested else "")}
