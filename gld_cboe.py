"""Read-only Cboe GLD original JSON/.json.gz parser and NET GAMMA engine.

This module deliberately performs no automated Cboe HTTP requests.
It does not alter the Serafini SPX or Nasdaq NDX projects.
"""
from collections import defaultdict
from datetime import date, timedelta
import gzip
import json
import math
import re

GLD_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json"
GLD_OCC = re.compile(r"^GLD(\d{6})([CP])(\d{8})$")
MAX_RAW_BYTES = 50 * 1024 * 1024
MIN_VALID_COVERAGE = 0.70


def read_gld(blob: bytes) -> dict:
    if not isinstance(blob, bytes) or not blob or len(blob) > MAX_RAW_BYTES:
        raise ValueError("File GLD assente o troppo grande (max 50 MB).")
    if blob[:2] == b"\x1f\x8b":
        # Bound inflated gzip size to prevent excessively large uploads.
        with gzip.GzipFile(fileobj=__import__("io").BytesIO(blob)) as f:
            blob = f.read(MAX_RAW_BYTES + 1)
        if len(blob) > MAX_RAW_BYTES:
            raise ValueError("JSON GLD decompresso troppo grande.")
    try:
        doc = json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Il file non contiene JSON Cboe valido.") from exc
    if not isinstance(doc, dict):
        raise ValueError("Il file Cboe deve contenere un oggetto JSON.")
    symbol = str(doc.get("symbol") or "").strip().upper().lstrip("_")
    if symbol != "GLD":
        raise ValueError(f"Atteso GLD Cboe, trovato {symbol or 'simbolo assente'}.")
    inner = doc.get("data")
    if not isinstance(inner, dict) or not isinstance(inner.get("options"), list):
        raise ValueError("Catena opzioni GLD assente o malformata.")
    if not inner["options"]:
        raise ValueError("Catena GLD vuota.")
    return doc


def parse_contract(code):
    match = GLD_OCC.fullmatch(str(code or "").replace(" ", "").strip().upper())
    if not match:
        return None
    raw_date, cp, raw_strike = match.groups()
    try:
        exp = date(2000 + int(raw_date[:2]), int(raw_date[2:4]), int(raw_date[4:6]))
    except ValueError:
        return None
    return exp, ("call" if cp == "C" else "put"), int(raw_strike) / 1000.0


def expirations(doc):
    return sorted({parts[0] for item in doc["data"]["options"]
                   if isinstance(item, dict)
                   if (parts := parse_contract(item.get("option"))) is not None})


def next_weekly(day, available):
    delta = (4 - day.weekday()) % 7 or 7
    chosen = day + timedelta(days=delta)
    return chosen if chosen in available else None


def _measure(value):
    try:
        if value is None or value == "":
            return None
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) and n >= 0 else None


def close_previous(doc):
    value = _measure(doc["data"].get("prev_day_close"))
    return value if value is not None and value > 0 else None


def current_price(doc):
    value = _measure(doc["data"].get("current_price"))
    return value if value is not None and value > 0 else None


def profile(doc, expiry, reference, band_pct=3.0):
    """Use real GLD strikes in previous-close ±%, without 25+25 SPX limit.

    Missing Gamma/OI/volume is EXCLUDED rather than silently filled with zero.
    Genuine zero values are permitted when supplied explicitly. Individual
    missing sides and incompleteness are reported.
    """
    if not isinstance(expiry, date):
        raise ValueError("Scadenza GLD non valida.")
    if not isinstance(reference, (float, int)) or not math.isfinite(reference) or reference <= 0:
        raise ValueError("Close precedente GLD non valido.")
    if not isinstance(band_pct, (int, float)) or not math.isfinite(band_pct) or not 0 < band_pct <= 10:
        raise ValueError("Fascia GLD non valida.")
    low = reference * (1 - band_pct / 100.0)
    high = reference * (1 + band_pct / 100.0)
    matched = 0
    complete = 0
    seen = set()
    positive_gammas = 0
    missing = defaultdict(int)
    pairs = defaultdict(dict)
    for item in doc["data"]["options"]:
        if not isinstance(item, dict):
            continue
        parts = parse_contract(item.get("option"))
        if parts is None or parts[0] != expiry:
            continue
        exp, side, strike = parts
        if not low - 1e-8 <= strike <= high + 1e-8:
            continue
        matched += 1
        code = str(item.get("option") or "").replace(" ", "").upper()
        if code in seen or side in pairs[strike]:
            raise ValueError("Catena GLD con contratto/strike/lato duplicato.")
        seen.add(code)
        gamma = _measure(item.get("gamma"))
        oi = _measure(item.get("open_interest"))
        volume = _measure(item.get("volume"))
        if gamma is None:
            missing["Gamma"] += 1
        if oi is None:
            missing["Open Interest"] += 1
        if volume is None:
            missing["Volume"] += 1
        if gamma is None or oi is None or volume is None:
            continue
        complete += 1
        if gamma > 0:
            positive_gammas += 1
        pairs[strike][side] = {"weighted": (oi + volume) * gamma, "gamma": gamma,
                               "oi": oi, "volume": volume}
    rows = []
    for strike, sides in sorted(pairs.items()):
        if "call" not in sides or "put" not in sides:
            missing["Strike senza entrambi i lati"] += 1
            continue
        c, p = sides["call"], sides["put"]
        rows.append({"strike": strike, "call": c["weighted"], "put": p["weighted"],
                     "net": c["weighted"] - p["weighted"],
                     "call_oi": c["oi"], "put_oi": p["oi"],
                     "call_volume": c["volume"], "put_volume": p["volume"],
                     "call_gamma": c["gamma"], "put_gamma": p["gamma"]})
    coverage = complete / matched if matched else 0.0
    usable = (matched > 0 and positive_gammas > 0
              and coverage >= MIN_VALID_COVERAGE and len(rows) >= 2)
    return {"expiry": expiry.isoformat(), "rows": rows if usable else [],
            "eligible": matched, "valid_contracts": complete,
            "complete_strikes": len(rows), "coverage": coverage,
            "missing": dict(missing), "positive_gammas": positive_gammas,
            "usable": usable, "lower": low, "upper": high,
            "source": "Cboe GLD · Gamma presente nella fonte", "approximate": False}
