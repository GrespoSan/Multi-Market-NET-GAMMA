"""Alpaca GLD options: conservative, read-only experimental source and calculation.

This module is independent of Nasdaq and Serafini SPX. It never submits trades.
It does not provide CME GC options or calculate monetary dealer exposure.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
import math
from zoneinfo import ZoneInfo

import requests

PAPER_API = "https://paper-api.alpaca.markets"
DATA_API = "https://data.alpaca.markets"
MAX_PAGES = 15
MIN_COVERAGE = 0.70


def _number(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _request(session, base, path, headers, params):
    try:
        response = session.get(base + path, headers=headers, params=params, timeout=(8, 35))
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise RuntimeError(f"Alpaca HTTP {status}: verifica API key, autorizzazioni e limiti del feed.") from exc
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Alpaca non raggiungibile o risposta non valida: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Risposta Alpaca non valida (non oggetto JSON).")
    return payload


def _paged(session, base, path, headers, params, collection_key):
    output = {} if collection_key == "snapshots" else []
    seen = set()
    token = None
    for _ in range(MAX_PAGES):
        page_params = dict(params)
        if token:
            page_params["page_token"] = token
        payload = _request(session, base, path, headers, page_params)
        records = payload.get(collection_key)
        if collection_key == "snapshots":
            if not isinstance(records, dict):
                raise ValueError("Alpaca: snapshots assenti o malformati.")
            output.update(records)
        else:
            if not isinstance(records, list):
                raise ValueError("Alpaca: lista contratti assente o malformata.")
            output.extend(records)
        next_token = payload.get("next_page_token")
        if not next_token:
            return output
        if next_token in seen:
            raise ValueError("Alpaca: token di paginazione ripetuto.")
        seen.add(next_token)
        token = next_token
    raise RuntimeError("Alpaca: troppe pagine, acquisizione incompleta; calcolo annullato.")


def next_friday(day):
    delta = (4 - day.weekday()) % 7
    return day + timedelta(days=delta or 7)


def fetch_gld(key, secret, band_pct=3.0, session=None, day=None):
    """Return real Alpaca responses for today's New York expiry and next Friday."""
    if not key or not secret:
        raise ValueError("Credenziali Alpaca mancanti.")
    if not 0 < band_pct <= 10:
        raise ValueError("Fascia GLD non valida.")
    day = day or datetime.now(ZoneInfo("America/New_York")).date()
    if not isinstance(day, date):
        raise TypeError("Data NY non valida.")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    session = session or requests.Session()
    price_data = _request(session, DATA_API, "/v2/stocks/GLD/snapshot", headers, {"feed": "iex"})
    prev_close = _number((price_data.get("prevDailyBar") or {}).get("c"))
    if not prev_close or prev_close <= 0:
        raise ValueError("Close GLD precedente indisponibile: nessun calcolo possibile.")
    lower = round(prev_close * (1 - band_pct / 100), 2)
    upper = round(prev_close * (1 + band_pct / 100), 2)
    expiries = {"0DTE": day, "Weekly": next_friday(day)}
    groups = {}
    for label, expiry in expiries.items():
        params = {"expiration_date": expiry.isoformat(), "strike_price_gte": lower,
                  "strike_price_lte": upper}
        contracts = _paged(session, PAPER_API, "/v2/options/contracts", headers,
                           {"underlying_symbols": "GLD", "status": "active", "limit": 1000, **params},
                           "option_contracts")
        if not contracts:
            groups[label] = {"expiry": expiry.isoformat(), "contracts": [], "snapshots": {}}
            continue
        snapshots = _paged(session, DATA_API, "/v1beta1/options/snapshots/GLD", headers,
                           {"feed": "indicative", "limit": 1000, **params}, "snapshots")
        groups[label] = {"expiry": expiry.isoformat(), "contracts": contracts, "snapshots": snapshots}
    return {"symbol": "GLD", "feed": "indicative", "captured_at": datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds"),
            "as_of_ny": day.isoformat(), "prev_close": prev_close, "band_pct": band_pct,
            "price_latest": (price_data.get("latestTrade") or {}).get("p"),
            "spot_quote": price_data.get("latestQuote") or {}, "groups": groups}


def calculate_profile(group, lower, upper):
    """Reject absent measurements; aggregate only complete call/put strike pairs.

    No missing Greek, OI, volume, or contract side is converted to a synthetic zero.
    """
    expiry = group["expiry"]
    snaps = group.get("snapshots") or {}
    contracts = group.get("contracts") or []
    if not isinstance(snaps, dict) or not isinstance(contracts, list):
        raise ValueError("Catena GLD non valida.")
    pairs = defaultdict(dict)
    missing = defaultdict(int)
    oi_dates = set()
    eligible = 0
    valid = 0
    for contract in contracts:
        if (contract.get("underlying_symbol") != "GLD"
                or contract.get("expiration_date") != expiry
                or contract.get("status") != "active"):
            continue
        strike = _number(contract.get("strike_price"))
        side = contract.get("type")
        symbol = contract.get("symbol")
        if strike is None or not lower <= strike <= upper or side not in ("call", "put") or not symbol:
            continue
        eligible += 1
        snap = snaps.get(symbol) or {}
        greek = _number((snap.get("greeks") or {}).get("gamma"))
        oi = _number(contract.get("open_interest"))
        daily = snap.get("dailyBar") or {}
        volume = _number(daily.get("v"))
        multiplier = _number(contract.get("multiplier"))
        if greek is None:
            missing["gamma"] += 1
        if oi is None:
            missing["OI"] += 1
        if volume is None:
            missing["volume"] += 1
        if multiplier != 100:
            missing["multiplier"] += 1
        if greek is None or oi is None or volume is None or multiplier != 100:
            continue
        valid += 1
        if contract.get("open_interest_date"):
            oi_dates.add(contract["open_interest_date"])
        if side in pairs[strike]:
            raise ValueError("Contratto GLD duplicato per strike/lato: calcolo bloccato.")
        pairs[strike][side] = {"weighted": (oi + volume) * greek, "oi": oi,
                               "volume": volume, "gamma": greek}
    records = []
    for strike, sides in sorted(pairs.items()):
        if not ("call" in sides and "put" in sides):
            missing["lato_incompleto"] += 1
            continue
        c, p = sides["call"], sides["put"]
        records.append({"strike": strike, "call": c["weighted"], "put": p["weighted"],
                        "net": c["weighted"] - p["weighted"],
                        "call_oi": c["oi"], "put_oi": p["oi"],
                        "call_volume": c["volume"], "put_volume": p["volume"]})
    coverage = valid / eligible if eligible else 0
    usable = eligible > 0 and coverage >= MIN_COVERAGE and len(records) >= 2
    return {"expiry": expiry, "rows": records if usable else [], "eligible": eligible,
            "valid_contracts": valid, "complete_strikes": len(records),
            "coverage": coverage, "missing": dict(missing),
            "oi_dates": sorted(oi_dates), "usable": usable}


def calculate_open_interest(group, lower, upper):
    """Strictly OI-only fallback for 0DTE when Alpaca omits Gamma.

    Never calls this GEX, never assumes missing OI is zero, and never
    transforms GLD strikes into GC strikes.
    """
    expiry = group["expiry"]
    contracts = group.get("contracts") or []
    snaps = group.get("snapshots") or {}
    if not isinstance(contracts, list) or not isinstance(snaps, dict):
        raise ValueError("Catena GLD non valida.")
    pairs = defaultdict(dict)
    oi_dates = set()
    eligible = 0
    complete = 0
    missing_oi = 0
    for c in contracts:
        if (c.get("underlying_symbol") != "GLD"
                or c.get("expiration_date") != expiry
                or c.get("status") != "active"):
            continue
        strike = _number(c.get("strike_price"))
        side = c.get("type")
        if strike is None or not lower <= strike <= upper or side not in ("call", "put"):
            continue
        eligible += 1
        oi = _number(c.get("open_interest"))
        if oi is None:
            missing_oi += 1
            continue
        if _number(c.get("multiplier")) != 100:
            continue
        complete += 1
        dated = c.get("open_interest_date")
        if dated:
            oi_dates.add(dated)
        symbol = c.get("symbol")
        if side in pairs[strike]:
            raise ValueError("Contratto GLD duplicato per strike/lato.")
        snap = snaps.get(symbol) or {}
        volume = _number((snap.get("dailyBar") or {}).get("v"))
        pairs[strike][side] = {"oi": oi, "volume": volume}
    rows = []
    for strike, sides in sorted(pairs.items()):
        if "call" not in sides or "put" not in sides:
            continue
        c, p = sides["call"], sides["put"]
        rows.append({"strike": strike, "call_oi": c["oi"], "put_oi": p["oi"],
                     "call_volume": c["volume"], "put_volume": p["volume"]})
    coverage = complete / eligible if eligible else 0.0
    return {"expiry": expiry, "rows": rows if len(rows) >= 2 and coverage >= MIN_COVERAGE else [],
            "complete_pairs": len(rows), "eligible": eligible, "missing_oi": missing_oi,
            "coverage": coverage, "oi_dates": sorted(oi_dates),
            "usable": len(rows) >= 2 and coverage >= MIN_COVERAGE}
