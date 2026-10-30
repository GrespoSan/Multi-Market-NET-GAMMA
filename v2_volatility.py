"""Market-neutral Volatilità — seduta precedente, with SPX card styling.

The three-column SPX presentation is preserved. Do not apply the
SPX-specific VX contango/backwardation buffer rule to other instruments.
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
    "NASDAQ": ("NQ=F", "^VXN", "VXN · Nasdaq-100"),
    "GOLD": ("GC=F", "^GVZ", "GVZ · opzioni GLD"),
    "WTI": ("CL=F", "^OVX", "OVX · opzioni USO"),
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
    return previous_sessions(contract, target_day, api_key)


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
    # The user-confirmed Serafini warning is a signed DOWN move
    # strictly beyond -1%. It is NOT the always-positive High-Low range.
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
        '<div style="font-size:1rem;padding:0 0 10px;color:#c3cbd5">'
        'Variazione chiusura della seduta (Close/Close): '
        f'<span style="color:{color};font-weight:750">{value}</span></div>'
    )


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
    if result["bearish_volatility"] is True:
        st.markdown('<div style="color:#ff676d;font-weight:750">Alta volatilità da ribasso · Close/Close &lt; −1%</div>',
                    unsafe_allow_html=True)
    elif result["bearish_volatility"] is False:
        st.caption("Ribasso oltre −1% non rilevato: questo non esclude altre cause di alta volatilità.")
    else:
        st.caption("Regime da ribasso: N/D (mancano due chiusure Massive).")
    if result["previous_range_pct"] is not None:
        range_detail = (f"{result['range_trend']} · seduta precedente "
                        f"{result['previous_range_pct']:.2f}%")
    else:
        range_detail = "Confronto non disponibile"
    if result["previous_close"] is not None and result["future_close"] is not None:
        st.caption(
            f"Massive Futures {contract} · 1session · stesso contratto: "
            f"chiusura {result['future_day'].isoformat()} "
            f"{result['future_close']:,.2f}, chiusura "
            f"{result['previous_close_day'].isoformat()} "
            f"{result['previous_close']:,.2f}. "
            "Variazione su trade Close, NON settlement."
        )
    elif future_error:
        st.warning(future_error)
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
.spx-vol-kpi .risk-text {{font-size:1.0rem;font-weight:750;}}
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
<div class="number">{escape(result['range_text'])}</div>
<div class="range-direction">{escape(range_detail)}</div>
</div>
<div class="spx-vol-kpi"><div class="label">{escape(vol_name)} precedente</div>
<div class="number">{escape(result['vol_text'])}</div></div>
<div class="spx-vol-kpi"><div class="label">Regime da ribasso Close/Close</div>
<div class="number risk-text" style="color:{'#ff676d' if result['bearish_volatility'] else '#c4ccd5'}">{'ALTA VOLATILITÀ' if result['bearish_volatility'] else 'N/D' if result['bearish_volatility'] is None else 'Soglia −1% non superata'}</div></div>
</div>
<div class="spx-vol-foot">Futures Massive {escape(contract or 'N/D')}, sessione {escape(f_day)} ·
Indice volatilità Yahoo {escape(vol_ticker)}: {escape(v_day)}.
Stesso contratto e sessione Massive: Close/Close &lt; −1% indica alta volatilità da ribasso;
Range Daily in espansione/compressione rispetto alla seduta ancora precedente.
Questa classificazione NON applica automaticamente il buffer SPX ad altri mercati.
Riferimento {target_day:%d/%m/%Y} · I valori si basano su trade Close, NON settlement.
{escape(vol_name)} non indica contango VX.
Buffer ES di 10/15 punti riservato alla Serafini SPX.
Verificare sempre la scadenza del contratto rispetto a TradingView 1!.</div>
</div>""", unsafe_allow_html=True)
    if not future_bars or not vol_bars:
        st.caption("Una o più fonti Daily non sono disponibili: la sezione "
                   "mostra N/D senza stime né valori inventati.")
    return result
