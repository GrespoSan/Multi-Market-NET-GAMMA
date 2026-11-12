"""V2 scheduler: new third capture 17:00 Europe/Rome.
Historical 20:30 records are readable but no longer acquired. 15:50 remains
anchored to 08:50 America/Chicago, including the DST mismatch weeks.
GitHub's UTC cron is accepted only if it corresponds to 17:00 Rome for
that date. No acquisition is ever backdated to a logical slot.
"""
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
CHICAGO = ZoneInfo("America/Chicago")
INSTRUMENTS = ("NDX", "RUT", "DJX", "GLD", "USO")
MAX_LAG_SECONDS = 12 * 60
CHANGEOVER = date(2026, 11, 12)

SLOTS = {
    "07:30": ("Europe/Rome", 7, 30, "30 7 * * 1-5"),
    "15:50": ("America/Chicago", 8, 50, "50 8 * * 1-5"),
    "17:00": ("Europe/Rome", 17, 0, "0 17 * * 1-5"),
}
HISTORICAL_2030 = ("America/Chicago", 13, 30, "30 13 * * 1-5")
SLOT_FOR_CRON = {values[3]: label for label, values in SLOTS.items()}
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
    if requested and requested not in SLOTS and not (
            requested == "20:30" and roma.date() < CHANGEOVER):
        raise ValueError("Slot logico non riconosciuto.")
    if external and (manual or event_cron or not requested):
        raise ValueError("cron-job.org richiede uno slot riconosciuto e non manuale.")
    if event_cron:
        # Two UTC schedule entries cover CET and CEST, but ONLY the one
        # representing 17:00 in Rome is allowed to download. No duplicate.
        if event_cron in ("0 15 * * 1-5", "0 16 * * 1-5"):
            expected_utc = datetime.combine(roma.date(), datetime.min.time(), ROME).replace(hour=17).astimezone(timezone.utc)
            requested_utc_hour = 15 if event_cron.startswith("0 15 ") else 16
            if expected_utc.hour != requested_utc_hour:
                return {"run": False, "reason": "DST_NON_CORRISPONDENTE", "slot": "17:00",
                        "rome": roma, "chicago": chicago, "time_zone": "Europe/Rome"}
            canonical = "17:00"
        else:
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
    eligible = dict(SLOTS)
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
        if (event_cron or external) and requested == label and lag > MAX_LAG_SECONDS:
            if scheduled.date() == clock.date():
                return {"run": True, "reason": (
                            "EXTERNAL_DISPATCH_DELAYED" if external else
                            "GITHUB_SCHEDULE_DELAYED"),
                        "slot": label, "rome": roma, "chicago": chicago,
                        "requested_slot": label, "time_zone": zone,
                        "scheduled_local": scheduled.isoformat(),
                        "lag_seconds": int(lag)}
    return {"run": False,
            "reason": "FUORI_FINESTRA" if requested else "NESSUNO_SLOT",
            "slot": requested or "", "rome": roma, "chicago": chicago,
            "requested_slot": requested or "", "time_zone": (
                eligible[requested][0] if requested else "")}
