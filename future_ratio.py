"""Synchronized, read-only Yahoo 5-minute ETF/future reference prices.

One pair is frozen per original Cboe snapshot and chosen dated futures contract.
A shared timestamp is mandatory. These are *price-ratio projections*, NOT
native options-on-futures strikes or CME Greeks.
"""
from datetime import date, datetime, timedelta, timezone, time
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
INTRADAY_MINUTES = 5
MAX_QUOTE_AGE_MINUTES = 60
CONTRACTS = {
    "GLD": {
        "etf_yahoo": "GLD",
        "etf_tv": "AMEX:GLD",
        "contracts": {
            "GCZ26 · dicembre 2026": ("GCZ26.CMX", "COMEX:GCZ2026"),
            "GCG27 · febbraio 2027": ("GCG27.CMX", "COMEX:GCG2027"),
        },
    },
    "USO": {
        "etf_yahoo": "USO",
        "etf_tv": "AMEX:USO",
        "contracts": {
            "CLZ26 · dicembre 2026": ("CLZ26.NYM", "NYMEX:CLZ2026"),
            "CLF27 · gennaio 2027": ("CLF27.NYM", "NYMEX:CLF2027"),
        },
    },
}


def choose_contract(symbol: str, selection: str):
    if symbol not in CONTRACTS or selection not in CONTRACTS[symbol]["contracts"]:
        raise ValueError("Contratto future non autorizzato: seleziona un mese quotato.")
    return CONTRACTS[symbol]["contracts"][selection]


def normalize_bars(frame):
    """Canonical UTC close prices keyed by the opening time of 5m bars."""
    if frame is None or getattr(frame, "empty", True):
        raise ValueError("Nessuna candela intraday fornita dal mercato.")
    if "Close" not in frame.columns:
        raise ValueError("Close mancante nei dati di mercato.")
    idx = pd.DatetimeIndex(frame.index)
    if idx.tz is None:
        raise ValueError("Timestamp senza fuso: impossibile sincronizzare.")
    series = pd.Series(pd.to_numeric(frame["Close"], errors="coerce").to_numpy(),
                       index=idx.tz_convert("UTC"))
    series = series[~series.index.duplicated(keep="last")]
    return series.sort_index()


def synchronized_pair(etf_bars, future_bars, etf_symbol, future_yahoo_ticker,
                      future_tv_symbol, target: date, now=None):
    """Last common *completed* 5m bar within ETF regular NY session of target.

    Rejects mismatched timestamps, stale intraday pairs, null/zero price,
    and stale/future bars. No nearest-neighbor matching (no false sync).
    """
    if not isinstance(target, date):
        raise ValueError("Data fotografia Cboe non valida.")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Orologio senza timezone.")
    now = now.astimezone(timezone.utc)
    etf = normalize_bars(etf_bars)
    fut = normalize_bars(future_bars)
    both = etf.index.intersection(fut.index)
    valid = []
    for stamp in both:
        dt = stamp.to_pydatetime().astimezone(timezone.utc)
        ny = dt.astimezone(NY)
        if ny.date() != target or not time(9, 30) <= ny.time() < time(16, 0):
            continue
        if dt + timedelta(minutes=INTRADAY_MINUTES) > now:
            continue
        e, f = float(etf.loc[stamp]), float(fut.loc[stamp])
        if not (isfinite(e) and e > 0 and isfinite(f) and f > 0):
            continue
        valid.append((dt, e, f))
    if not valid:
        raise ValueError("Nessuna coppia di barre GLD/GC o USO/CL con lo stesso "
                         "timestamp, completata e nella seduta ETF della data selezionata.")
    dt, ep, fp = max(valid, key=lambda v: v[0])
    # Reject delayed, stale or prior-session bars DURING today's ETF cash session.
    now_ny = now.astimezone(NY)
    if target == now_ny.date() and time(9, 30) <= now_ny.time() < time(16, 0):
        age = (now - (dt + timedelta(minutes=INTRADAY_MINUTES))).total_seconds() / 60
        if age > MAX_QUOTE_AGE_MINUTES:
            raise ValueError(f"Barre ETF/future troppo vecchie ({age:.0f} min): "
                             "fotografia sincronizzata annullata.")
    return {"etf_symbol": etf_symbol, "future_yahoo_ticker": future_yahoo_ticker,
            "future_tv_symbol": future_tv_symbol, "etf_price": ep, "future_price": fp,
            "ratio": fp / ep, "bar_utc": dt.isoformat(timespec="seconds"),
            "bar_ny": dt.astimezone(NY).isoformat(timespec="seconds"),
            "target_date": target.isoformat(), "interval": "5m",
            "source": "Yahoo Finance · 5m same-timestamp completed bars",
            "mode": "automatic-synchronized"}


def fetch_pair(symbol, selection, target: date, now=None, yf_module=None):
    """Fetch two selected Yahoo series; never silently switch future months."""
    ticker, tv = choose_contract(symbol, selection)
    if yf_module is None:
        import yfinance as yf
        yf_module = yf
    etf_ticker = CONTRACTS[symbol]["etf_yahoo"]
    etf = yf_module.Ticker(etf_ticker).history(
        period="5d", interval="5m", prepost=False, auto_adjust=False)
    future = yf_module.Ticker(ticker).history(
        period="5d", interval="5m", prepost=False, auto_adjust=False)
    return synchronized_pair(etf, future, symbol, ticker, tv, target, now=now)


def manual_pair(etf_price, future_price, symbol, selection, target, clock_ny):
    """Explicitly user-attested same-time reference pair, never labeled verified."""
    ticker, tv = choose_contract(symbol, selection)
    try:
        e, f = float(etf_price), float(future_price)
    except (ValueError, TypeError) as exc:
        raise ValueError("Prezzi manuali non numerici.") from exc
    if not all(isfinite(v) and v > 0 for v in (e, f)):
        raise ValueError("Prezzi manuali non validi.")
    try:
        t = datetime.fromisoformat(f"{target.isoformat()}T{clock_ny}")
        if not time(9,30) <= t.time() <= time(16,0):
            raise ValueError()
        stamp = t.replace(tzinfo=NY)
    except (ValueError, TypeError) as exc:
        raise ValueError("Indicare HH:MM New York nella sessione ETF 09:30–16:00.") from exc
    return {"etf_symbol": symbol, "future_yahoo_ticker": ticker,
            "future_tv_symbol": tv, "etf_price": e, "future_price": f,
            "ratio": f/e, "bar_utc": stamp.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "bar_ny": stamp.isoformat(timespec="seconds"),
            "target_date": target.isoformat(), "interval": "manual",
            "source": "Prezzi inseriti dall'utente; sincronizzazione dichiarata NON verificata",
            "mode": "manual-attested"}
