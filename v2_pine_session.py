"""Time-scoped V2 Pine captures: only genuine same-NY-session archived files.

A slot is the acquisition RUN label, not a forged wall-clock timestamp.
Capture time always comes from the authenticated filename in the decrypted
GitHub Actions archive. EU/US daylight saving is handled by ZoneInfo.
"""
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import re

NY = ZoneInfo("America/New_York")
ROME = ZoneInfo("Europe/Rome")
SLOTS = ("0730", "1550", "2030")
LABELS = {"0730": "07:30", "1550": "15:50", "2030": "20:30"}
FILE = re.compile(
    r"^(NDX|RUT|DJX|GLD|USO)_(\d{8}T\d{6}Z)_(0730|1550|2030)_([0-9a-f]{12})\.json\.gz$"
)


def parse_archived_capture(filename, symbol, market_day):
    """Return attested UTC capture and slot, not the ambiguous Cboe clock."""
    match = FILE.fullmatch(str(filename))
    if not match or match.group(1) != symbol:
        raise ValueError("Nome fotografia V2 originale non valido per il mercato.")
    if not isinstance(market_day, date):
        raise ValueError("Data mercato non valida.")
    captured = datetime.strptime(
        match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if captured.astimezone(NY).date() != market_day:
        raise ValueError("Fotografia di un'altra seduta New York.")
    return {"slot": match.group(3), "utc":captured,
            "rome":captured.astimezone(ROME), "filename":filename}


def compare_capture_pair(previous, current, previous_slot, current_slot):
    """Reject future/reversed/different-day captures and dishonest slot pairs."""
    if (previous_slot, current_slot) not in (
            ("0730", "1550"), ("1550", "2030")):
        raise ValueError("Coppia di rilevamenti non prevista.")
    if (previous["slot"] != previous_slot or current["slot"] != current_slot
            or previous["utc"].astimezone(NY).date() !=
            current["utc"].astimezone(NY).date()
            or previous["utc"] >= current["utc"]):
        raise ValueError("Fotografie non ordinate o di sedute differenti.")
    return True


def artifact_in_session_window(created_at, market_day):
    """Conservative prefilter to avoid downloading month-old ZIPs.

    Includes GitHub workflow delays up to 20h after the US session end;
    the decrypted filename is always verified again after downloading.
    """
    if not isinstance(market_day, date):
        return False
    try:
        made = datetime.fromisoformat(
            str(created_at).replace("Z", "+00:00"))
        if made.tzinfo is None:
            return False
    except (ValueError, TypeError):
        return False
    begin = datetime.combine(market_day, datetime.min.time(), NY)
    end = begin + timedelta(days=2)
    return begin <= made.astimezone(NY) < end
