"""Market-neutral Volatilità — seduta precedente, with SPX card styling.

The three-column SPX presentation is preserved. Do not apply the
SPX conditions only with verified per-market term structure and Daily candle.
NQ/GC/CL OHLC 1session and Close/Close from Massive; VXN/GVZ/OVX
volatility indices remain from Yahoo where available. All dates are strictly PRIOR to the reference day.
"""
from datetime import date, timedelta
from html import escape
from math import isfinite

import pandas as pd
import streamlit as st
import yfinance as yf
from massive_futures_daily import previous_sessions, MassiveSourceError

SOURCES = {
    "NASDAQ": ("NQ=F", "^VXN", "VXN · volatilità implicita Nasdaq-100"),
    "GOLD": ("GC=F", "^GVZ", "GVZ · volatilità implicita Gold"),
    "WTI": ("CL=F", "^OVX", "OVX · volatilità implicita Petrolio"),
}


@st.cache_data(ttl=1800, show_spinner=False, max_entries=30)
def fetch_daily(ticker: str, target_day: date):
    if not isinstance(target_day, date):
        raise ValueError("Data Daily non valida.")
    raw = yf.download(ticker, start=(target_day - timedelta(days=22)).isoformat(),
                      end=target_day.isoformat(), interval="1d",
                      auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        raise ValueError("Serie Yahoo Daily assente.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    if any(k not in raw for k in ("High", "Low", "Close")):
        raise ValueError("Daily High/Low/Close non completo.")
    bars = []
    for stamp, row in raw.iterrows():
        day = pd.Timestamp(stamp).date()
        if day >= target_day or day.weekday() >= 5:
            continue
        try:
            hi, lo, close = (float(row[k]) for k in ("High", "Low", "Close"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not all(isfinite(x) for x in (hi, lo, close)) or hi < lo or close <= 0:
            continue
        bars.append({"day": day, "hi": hi, "lo": lo, "close": close})
    bars.sort(key=lambda x: x["day"])
    if not bars or (target_day - bars[-1]["day"]).days > 7:
        raise ValueError("Nessuna chiusura Daily precedente recente.")
    return bars


@st.cache_data(ttl=3600, max_entries=60, show_spinner=False)
def fetch_massive_futures(contract, target_day, api_key):
    """OHLC from one named futures contract; no silent roll."""
    return previous_sessions(contract, target_day, api_key, history_days=75)


def evaluate(future_bars, vol_bars):
    future = future_bars[-1] if future_bars else None
    vol = vol_bars[-1] if vol_bars else None
    previous_vol = vol_bars[-2] if vol_bars and len(vol_bars) >= 2 else None
    if future:
        value = future["hi"] - future["lo"]
        range_text = f"{value:,.2f} pt · {value / future['close'] * 100:.2f}%"
    else:
        range_text = "Non disponibile"
    # A real up/down measurement requires TWO closed Daily sessions.
    # High−Low (range) is always >= 0 and must stay neutral in the UI.
    previous_future = (
        future_bars[-2] if future and len(future_bars) >= 2
        and future_bars[-2]["day"] < future["day"]
        and (future["day"] - future_bars[-2]["day"]).days <= 7
        and future_bars[-2]["close"] > 0 else None
    )
    change_pct = (
        (future["close"] / previous_future["close"] - 1.0) * 100.0
        if previous_future else None
    )
    if future and previous_future:
        current_range_pct = 100.0 * (future["hi"] - future["lo"]) / future["close"]
        previous_range_pct = 100.0 * (previous_future["hi"] - previous_future["lo"]) / previous_future["close"]
        if abs(current_range_pct - previous_range_pct) < 1e-9:
            range_trend = "INVARIATO"
        else:
            range_trend = "ESPANSIONE" if current_range_pct > previous_range_pct else "COMPRESSIONE"
    else:
        previous_range_pct, range_trend = None, "N/D"
    # Legacy signed Close/Close remains informational, not the buffer rule.
    bearish_volatility = None if change_pct is None else round(change_pct, 6) < -1.0
    if vol is None:
        vol_text = "Non disponibile"
    elif previous_vol and previous_vol["close"]:
        diff = (vol["close"] / previous_vol["close"] - 1) * 100
        vol_text = f"{vol['close']:.2f} · {diff:+.2f}%"
    else:
        vol_text = f"{vol['close']:.2f} · variazione N/D"
    return {"range_text": range_text, "vol_text": vol_text,
            "change_pct": change_pct,
            "previous_range_pct": previous_range_pct,
            "range_trend": range_trend,
            "bearish_volatility": bearish_volatility,
            "future_close": future["close"] if future else None,
            "previous_close": (previous_future["close"]
                               if previous_future else None),
            "previous_close_day": (previous_future["day"]
                                   if previous_future else None),
            "future_day": future["day"] if future else None,
            "vol_day": vol["day"] if vol else None}


def signed_daily_heading(change_pct):
    """One explicit Close/Close performance line, distinct from volatility."""
    base = "Andamento e volatilità — seduta precedente"
    if change_pct is None or not isfinite(float(change_pct)):
        value, color = "N/D", "#b6bcc5"
    else:
        value = f"{float(change_pct):+.2f}%".replace(".", ",")
        color = ("#56d49e" if change_pct > 0 else
                 "#ff676d" if change_pct < 0 else "#b6bcc5")
    return (
        f'<h4 style="font-size:1.4rem;font-weight:700">{base}</h4>'
        '<div style="font-size:1.12rem;line-height:1.5;padding:0 0 12px;'
        'color:#dbe2eb;font-weight:600">'
        'Variazione chiusura della seduta: '
        f'<span style="color:{color};font-size:1.2rem;font-weight:800">{value}</span></div>'
    )


def daily_candle_state(future):
    """Open/Close della candela Massive; Close/Close non determina il colore."""
    if not future or future.get("open") is None or future.get("close") is None:
        return "N/D"
    try:
        opening, closing = float(future["open"]), float(future["close"])
        if not (isfinite(opening) and isfinite(closing)):
            return "N/D"
    except (ValueError, TypeError, OverflowError):
        return "N/D"
    return "ROSSA" if closing < opening else ("VERDE" if closing > opening else "DOJI")


def italian_number(value, decimals=2):
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def same_spx_regime(term_structure_pct=None, daily_range_pct=None, daily_candle_red=None):
    """Same SPX OR rule: backwardation OR red Daily with High-Low range > 1%.

    10/low only if both conditions can be verified as false.
    A missing curve never becomes automatic contango.
    """
    def finite_or_none(value):
        if value is None:
            return None
        number = float(value)
        if not isfinite(number):
            raise ValueError("Percentuale non finita")
        return number

    term_pct = finite_or_none(term_structure_pct)
    day_pct = finite_or_none(daily_range_pct)
    if day_pct is not None and day_pct < 0:
        raise ValueError("Range Daily non valido")
    if daily_candle_red is not None and not isinstance(daily_candle_red, bool):
        raise TypeError("Colore Daily non verificato")
    reasons = []
    if term_pct is not None and term_pct < 0:
        reasons.append("Backwardation verificata")
    if day_pct is not None and daily_candle_red is True and day_pct > 1.0:
        reasons.append("Candela Daily rossa e range High-Low > 1%")
    if reasons:
        return {"points": 15, "state": "ALTA", "reason": "; ".join(reasons)}
    if term_pct is not None and day_pct is not None and daily_candle_red is not None:
        return {"points": 10, "state": "BASSA",
                "reason": "Nessuna backwardation né candela rossa con range > 1%"}
    return {"points": None, "state": None,
            "reason": "Backwardation o dati della candela non verificabili"}


def render(market, target_day):
    if market not in SOURCES:
        raise ValueError("Mercato non configurato per il contesto.")
    future_ticker, vol_ticker, vol_name = SOURCES[market]
    product = {"NASDAQ": "NQ", "GOLD": "GC", "WTI": "CL"}[market]
    try:
        key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
        contract = str(st.secrets.get(f"MASSIVE_{product}_CONTRACT", "")).strip().upper()
    except Exception:
        key, contract = "", ""
    future_bars, vol_bars = [], []
    future_error = ""
    if not key or not contract:
        future_error = (
            f"Configura MASSIVE_API_KEY e MASSIVE_{product}_CONTRACT "
            "nei Secrets di questa app. Nessun fallback Yahoo sui futures."
        )
    else:
        try:
            future_bars = fetch_massive_futures(contract, target_day, key)
        except MassiveSourceError as exc:
            future_error = str(exc)
        except Exception:
            future_error = "Massive non disponibile: verifica il piano Futures e il contratto."
    try:
        vol_bars = fetch_daily(vol_ticker, target_day)
    except Exception:
        pass
    result = evaluate(future_bars, vol_bars)
    f_day = result["future_day"].isoformat() if result["future_day"] else "N/D"
    v_day = result["vol_day"].isoformat() if result["vol_day"] else "N/D"
    change = result["change_pct"]
    st.markdown(signed_daily_heading(change), unsafe_allow_html=True)
    if result["previous_range_pct"] is not None:
        prior_day = result["previous_close_day"].strftime("%d/%m/%Y")
        prior_range = f"{result['previous_range_pct']:.2f}".replace(".", ",")
        range_detail = f"{result['range_trend']} · confronto con il {prior_day}: {prior_range}%"
    else:
        range_detail = "Confronto non disponibile"
    if future_error:
        st.warning(future_error)
    latest_future = future_bars[-1] if future_bars else None
    candle_label = daily_candle_state(latest_future)
    candle_color = {"ROSSA":"#ff676d", "VERDE":"#56d49e",
                    "DOJI":"#b6bcc5", "N/D":"#b6bcc5"}[candle_label]
    if latest_future:
        raw_range = latest_future["hi"] - latest_future["lo"]
        range_points = (str(int(round(raw_range)))
                        if abs(raw_range - round(raw_range)) < 0.005
                        else italian_number(raw_range))
        range_value = f"{range_points} pt · {italian_number(raw_range / latest_future['close'] * 100)}%"
        range_detail = (f"{result['range_trend']} · prima "
                        f"{italian_number(result['previous_range_pct'])}%"
                        if result["previous_range_pct"] is not None else
                        "Confronto non disponibile")
    else:
        range_value = "Non disponibile"
    vol_symbol = vol_ticker.removeprefix("^")
    if vol_bars:
        vol_value = italian_number(vol_bars[-1]["close"])
        if len(vol_bars) >= 2 and vol_bars[-2]["close"]:
            variation = 100 * (vol_bars[-1]["close"] / vol_bars[-2]["close"] - 1)
            vol_value += f" ({variation:+.2f}%)".replace(".", ",")
    else:
        vol_value = "Non disponibile"
    # La V2 non possiede una curva a termine per NQ/GC/CL.
    # Gli indici VXN/GVZ/OVX spot non equivalgono al contango futures.
    daily_pct = (100.0 * (latest_future["hi"] - latest_future["lo"])
                 / latest_future["close"] if latest_future else None)
    candle_red = (True if candle_label == "ROSSA" else
                  False if candle_label in ("VERDE", "DOJI") else None)
    market_term_structure_pct = None  # Mancante: non inventare backwardation
    regime = same_spx_regime(market_term_structure_pct, daily_pct, candle_red)
    if regime["state"] == "ALTA":
        buffer_value, buffer_color = "N/D (volatilità alta)", "#ff676d"
    elif regime["state"] == "BASSA":
        buffer_value, buffer_color = "N/D (volatilità bassa)", "#56d49e"
    else:
        buffer_value, buffer_color = "N/D (volatilità da determinare)", "#e5b65c"
    buffer_reason = (f"{regime['reason']}; regola SPX applicata al Daily {product}. "
                     f"Buffer numerico non validato per {product}")
    st.markdown(f"""
<style>
.spx-vol-card {{border:1px solid #34363c;border-radius:13px;padding:14px 18px;
background:#090a0c;color:#f4f5f6;font-family:inherit;}}
.spx-vol-grid {{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:center;}}
.spx-vol-kpi {{padding:5px 18px;min-width:0;border-left:1px solid #292b30;}}
.spx-vol-kpi:first-child {{padding-left:0;border-left:0;}}
.spx-vol-kpi .label {{font-size:.82rem;color:#b6bcc5;margin-bottom:5px;}}
.spx-vol-kpi .number {{font-size:1.15rem;font-weight:740;overflow-wrap:anywhere;}}
.spx-vol-kpi .range-direction {{font-size:.79rem;color:#abb6c4;margin-top:8px;line-height:1.5;}}
.spx-vol-kpi .candle-direction {{font-size:.84rem;font-weight:700;margin-top:7px;line-height:1.4;color:{candle_color};}}
.spx-vol-kpi .buffer {{color:{buffer_color};font-size:1.3rem;}}
.spx-vol-foot {{border-top:1px solid #292b30;padding-top:9px;margin-top:12px;
color:#949ba6;font-size:.74rem;line-height:1.4;}}
@media(max-width:700px){{
.spx-vol-grid {{grid-template-columns:1fr;}}
.spx-vol-kpi {{padding:10px 0;border-left:0;border-top:1px solid #292b30;}}
.spx-vol-kpi:first-child {{border-top:0;}}
}}
</style>
<div class="spx-vol-card">
<div class="spx-vol-grid">
<div class="spx-vol-kpi"><div class="label">Range Daily precedente</div>
<div class="number">{escape(range_value)}</div>
<div class="range-direction">{escape(range_detail)}</div>
<div class="candle-direction">Candela Daily: {escape(candle_label)}</div>
</div>
<div class="spx-vol-kpi"><div class="label">Volatilità implicita {escape(vol_symbol)} precedente</div>
<div class="number">{escape(vol_value)}</div></div>
<div class="spx-vol-kpi"><div class="label">Buffer standard</div>
<div class="number buffer">{escape(buffer_value)}</div></div>
</div>
<div class="spx-vol-foot">Motivo del buffer: {escape(buffer_reason)}.
Futures Massive {escape(contract or 'N/D')} · {escape(f_day)} ·
{escape(vol_symbol)} Yahoo {escape(v_day)}.</div>
</div>""", unsafe_allow_html=True)
    with st.expander("Dettaglio fonti e formule", expanded=False):
        if result["previous_close"] is not None and result["future_close"] is not None:
            st.caption(
                f"Massive Futures {contract} · 1session · Close "
                f"{result['future_day'].isoformat()} = {result['future_close']:,.2f}; "
                f"Close {result['previous_close_day'].isoformat()} = "
                f"{result['previous_close']:,.2f}. "
                "Variazione = (Close / Close precedente − 1) × 100. "
                "Range = (High − Low) / Close × 100. Non si usano i settlement."
            )
        if latest_future:
            if candle_label != "N/D":
                st.caption(
                    f"Candela Daily {product} precedente: Open "
                    f"{italian_number(latest_future['open'])}; Close "
                    f"{italian_number(latest_future['close'])}; {candle_label}; "
                    f"range High-Low "
                    f"{italian_number(100 * (latest_future['hi'] - latest_future['lo']) / latest_future['close'])}%."
                )
            else:
                st.caption("Open/Close non disponibili: colore candela non verificabile.")
        st.caption(
            "Range Daily (%) = (High − Low) / Close × 100. "
            "Espansione/compressione: confronto con il range percentuale "
            "della seduta ancora precedente. "
            "Stessa fonte e serie Massive usata nel Trend Daily."
        )
        st.caption(
            "Criterio SPX sul future selezionato: 15 (alta) se backwardation "
            "verificata oppure candela Daily precedente rossa con "
            "(High-Low)/Close > 1%; 10 (bassa) solo se entrambe le condizioni "
            "sono state verificate ed escluse. Close/Close resta informativo."
        )
        st.caption(
            f"Curva a termine per {product}: dato non disponibile nella V2. "
            "VXN/GVZ/OVX sono indici spot e non permettono di verificare "
            "la backwardation: senza questa verifica la bassa volatilità "
            "non può essere affermata."
        )
        st.caption(
            f"Indice di volatilità implicita: Yahoo Finance {vol_symbol} "
            f"({v_day}). La regola sul range Daily è la stessa della SPX. "
            "I numeri del buffer 10/15 non vengono trasferiti automaticamente "
            "a NQ, GC o CL."
        )
    result["daily_bars"] = future_bars
    result["contract"] = contract or None
    result["daily_error"] = future_error
    return result
