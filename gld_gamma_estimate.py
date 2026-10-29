"""Experimental GLD 0DTE Black-Scholes Gamma, never CME GC Gamma.

Alpaca does not supply same-day Greeks. We solve an indicative midquote IV
where feasible, and optionally borrow same-strike/same-side NEXT FRIDAY
implied volatility as an explicitly labeled proxy. These are NOT official
Greeks or observed dealer inventory. GLD ETF options are American-style;
European Black-Scholes is only an approximation, especially near expiry.
"""
from collections import Counter, defaultdict
from datetime import datetime, time, timezone, timedelta
from math import exp, erf, isfinite, log, pi, sqrt
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
SECONDS_PER_YEAR = 365.0 * 86400.0
MIN_IV, MAX_IV = 0.05, 3.0
MIN_CONTRACT_COVERAGE = 0.70
MIN_MATCHED_STRIKES = 3


def _positive(raw, allow_zero=False):
    try:
        val = float(raw)
        if not isfinite(val) or val < 0 or (not allow_zero and val == 0):
            return None
        return val
    except (TypeError, ValueError):
        return None


def _stamp(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return t if t.tzinfo is not None else None
    except ValueError:
        return None


def _cdf(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def bs_price_gamma(spot, strike, rate, years, iv, side):
    """European BSM, zero dividend yield. Price and gamma per GLD share."""
    if not all(isfinite(x) for x in (spot, strike, rate, years, iv)):
        raise ValueError("Non-finite model input.")
    if spot <= 0 or strike <= 0 or years <= 0 or iv <= 0 or side not in ("call", "put"):
        raise ValueError("Invalid model input.")
    root = iv * sqrt(years)
    d1 = (log(spot / strike) + (rate + 0.5 * iv * iv) * years) / root
    d2 = d1 - root
    if side == "call":
        price = spot * _cdf(d1) - strike * exp(-rate * years) * _cdf(d2)
    else:
        price = strike * exp(-rate * years) * _cdf(-d2) - spot * _cdf(-d1)
    gamma = exp(-0.5 * d1 * d1) / (spot * root * sqrt(2 * pi))
    return max(0.0, price), gamma


def infer_iv_from_mid(spot, strike, rate, years, side, bid, ask):
    """Price-calibrated IV, rejecting crossed, wide, or too-small quotes."""
    bid, ask = _positive(bid), _positive(ask)
    if bid is None or ask is None or ask < bid:
        return None
    mid = (bid + ask) / 2
    if mid < 0.08 or (ask - bid) / mid > 0.50:
        return None
    lo_val = bs_price_gamma(spot, strike, rate, years, MIN_IV, side)[0]
    hi_val = bs_price_gamma(spot, strike, rate, years, MAX_IV, side)[0]
    if mid < lo_val - 0.005 or mid > hi_val + 0.005:
        return None
    if mid <= lo_val:
        return None
    lo, hi = MIN_IV, MAX_IV
    for _ in range(90):
        guess = (lo + hi) / 2
        val = bs_price_gamma(spot, strike, rate, years, guess, side)[0]
        if val < mid:
            lo = guess
        else:
            hi = guess
    iv = (lo + hi) / 2
    if abs(bs_price_gamma(spot, strike, rate, years, iv, side)[0] - mid) > 0.005:
        return None
    return iv


def _fresh_quote(snap, ref_time, limit_seconds=180):
    quote = snap.get("latestQuote") or {}
    t = _stamp(quote.get("t"))
    if t is None or abs((ref_time - t).total_seconds()) > limit_seconds:
        return None
    return quote


def _oi_and_volume(contract, snap, day):
    oi = _positive(contract.get("open_interest"), allow_zero=True)
    bar = snap.get("dailyBar") or {}
    volume = _positive(bar.get("v"), allow_zero=True)
    bar_t = _stamp(bar.get("t"))
    if (oi is None or volume is None or bar_t is None
            or bar_t.astimezone(NY).date() != day):
        return None
    if _positive(contract.get("multiplier")) != 100:
        return None
    return oi, volume


def estimate_0dte(data, annual_rate=0.035, use_weekly_proxy=True, close_hour=16, close_minute=15):
    """Estimate 0DTE Greeks from a synchronized quote or next-Friday IV.

    Every missing contract/leg is excluded, never replaced with zero.
    The proxy is labeled by each leg and is opt-in/out in Streamlit.
    """
    if not 0 <= annual_rate <= 0.15:
        raise ValueError("Tasso annuo non valido (0-15%).")
    if (close_hour, close_minute) not in ((16, 15), (13, 15)):
        raise ValueError("Orario chiusura GLD supportato: 16:15 o 13:15 NY.")
    groups = data.get("groups") or {}
    d0 = groups.get("0DTE") or {}
    later = groups.get("Weekly") or {}
    expiry = d0.get("expiry")
    if not expiry:
        raise ValueError("Scadenza 0DTE assente.")
    day = datetime.fromisoformat(expiry).date()
    ny_expiry = datetime.combine(day, time(close_hour, close_minute), tzinfo=NY)

    captured = _stamp(data.get("captured_at"))
    spot_quote = data.get("spot_quote") or {}
    spot_time = _stamp(spot_quote.get("t"))
    bid, ask = _positive(spot_quote.get("bp")), _positive(spot_quote.get("ap"))
    status = Counter()
    base = {"expiry": expiry, "rows": [], "eligible": 0, "valid_contracts": 0,
            "complete_strikes": 0, "coverage": 0.0, "usable": False,
            "sources": {}, "excluded": {}, "oi_dates": [], "spot_used": None,
            "minutes_left": None, "asof_ny": None, "approximate": True}
    if captured is None or spot_time is None or bid is None or ask is None or ask < bid:
        base["excluded"] = {"spot_or_clock_missing": 1}
        return base
    ny_time = spot_time.astimezone(NY)
    base["asof_ny"] = ny_time.isoformat(timespec="seconds")
    if ((captured - spot_time).total_seconds() > 300 or
            (captured - spot_time).total_seconds() < -15):
        base["excluded"] = {"stale_spot": 1}
        return base
    if ny_time.date() != day or not time(9, 30) <= ny_time.time() < time(close_hour, close_minute):
        base["excluded"] = {"out_of_session": 1}
        return base
    remaining = (ny_expiry - spot_time).total_seconds()
    # 15 minutes before expiration IV/Gamma become too unstable for this feed.
    if remaining < 900:
        base["excluded"] = {"less_than_15_min_to_close": 1}
        return base
    years = remaining / SECONDS_PER_YEAR
    spot = (bid + ask) / 2
    base["spot_used"] = spot
    base["minutes_left"] = remaining / 60

    weekly_contracts = {c.get("symbol"): c for c in (later.get("contracts") or [])}
    weekly_snapshots = later.get("snapshots") or {}
    weekly_by_key = {}
    for c in weekly_contracts.values():
        if c.get("underlying_symbol") != "GLD" or c.get("status") != "active":
            continue
        k = _positive(c.get("strike_price"))
        if k is not None and c.get("type") in ("call", "put"):
            s = weekly_snapshots.get(c["symbol"]) or {}
            iv = _positive(s.get("impliedVolatility"))
            if iv is not None and MIN_IV <= iv <= MAX_IV and _fresh_quote(s, spot_time):
                weekly_by_key[(k, c["type"])] = iv
    pair = defaultdict(dict)
    oi_dates = set()
    sources = Counter()
    eligible = valid = 0
    lower = data["prev_close"] * (1 - data["band_pct"] / 100)
    upper = data["prev_close"] * (1 + data["band_pct"] / 100)
    for contract in d0.get("contracts") or []:
        if (contract.get("underlying_symbol") != "GLD"
                or contract.get("expiration_date") != expiry
                or contract.get("status") != "active"):
            continue
        k = _positive(contract.get("strike_price"))
        side = contract.get("type")
        symbol = contract.get("symbol")
        if k is None or not lower - 0.001 <= k <= upper + 0.001 or side not in ("call", "put") or not symbol:
            continue
        eligible += 1
        snap = (d0.get("snapshots") or {}).get(symbol) or {}
        oiv = _oi_and_volume(contract, snap, day)
        if oiv is None:
            status["oi_volume_multiplier_or_date_missing"] += 1
            continue
        quote = _fresh_quote(snap, spot_time)
        if quote is None:
            status["stale_or_missing_option_quote"] += 1
            continue
        iv = _positive(snap.get("impliedVolatility"))
        method = None
        if iv is not None and MIN_IV <= iv <= MAX_IV:
            method = "Alpaca IV"
        else:
            iv = infer_iv_from_mid(spot, k, annual_rate, years, side, quote.get("bp"), quote.get("ap"))
            if iv is not None:
                method = "0DTE mid"
        if iv is None and use_weekly_proxy:
            iv = weekly_by_key.get((k, side))
            if iv is not None:
                method = "Weekly IV proxy"
        if iv is None:
            status["iv_unavailable"] += 1
            continue
        g = bs_price_gamma(spot, k, annual_rate, years, iv, side)[1]
        if not isfinite(g) or g < 0:
            status["invalid_gamma"] += 1
            continue
        if side in pair[k]:
            raise ValueError("Contratto duplicato per strike/lato 0DTE.")
        oi, volume = oiv
        pair[k][side] = {"weighted": (oi + volume) * g, "gamma": g,
                         "oi": oi, "volume": volume, "iv": iv, "method": method}
        if contract.get("open_interest_date"):
            oi_dates.add(contract["open_interest_date"])
        sources[method] += 1
        valid += 1
    rows = []
    for strike, sides in sorted(pair.items()):
        if "call" not in sides or "put" not in sides:
            status["incomplete_strike"] += 1
            continue
        c, p = sides["call"], sides["put"]
        rows.append({"strike": strike, "call": c["weighted"], "put": p["weighted"],
                     "net": c["weighted"] - p["weighted"],
                     "call_gamma": c["gamma"], "put_gamma": p["gamma"],
                     "call_iv": c["iv"], "put_iv": p["iv"],
                     "call_method": c["method"], "put_method": p["method"],
                     "call_oi": c["oi"], "put_oi": p["oi"],
                     "call_volume": c["volume"], "put_volume": p["volume"]})
    coverage = valid / eligible if eligible else 0
    usable = len(rows) >= MIN_MATCHED_STRIKES and coverage >= MIN_CONTRACT_COVERAGE
    base.update({"rows": rows if usable else [], "eligible": eligible,
                 "valid_contracts": valid, "complete_strikes": len(rows),
                 "coverage": coverage, "usable": usable, "sources": dict(sources),
                 "excluded": dict(status), "oi_dates": sorted(oi_dates)})
    return base
