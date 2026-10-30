"""Market-neutral Volatilità — seduta precedente, with SPX card styling.

The three-column SPX presentation is preserved. Do not apply the
SPX-specific VX contango/backwardation buffer rule to other instruments.
NQ/GC/CL daily range from Yahoo futures, Cboe volatility indexes VXN/GVZ/OVX
where available. All dates are strictly PRIOR to the reference day.
"""
from datetime import date, timedelta
from html import escape
from math import isfinite

import pandas as pd
import streamlit as st
import yfinance as yf

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


def evaluate(future_bars, vol_bars):
    future = future_bars[-1] if future_bars else None
    vol = vol_bars[-1] if vol_bars else None
    previous_vol = vol_bars[-2] if vol_bars and len(vol_bars) >= 2 else None
    if future:
        value = future["hi"] - future["lo"]
        range_pct = value / future["close"] * 100
        range_points = value
        range_text = f"{value:,.2f} pt · {range_pct:.2f}%"
    else:
        range_text = "Non disponibile"
        range_pct = None
        range_points = None
    if vol is None:
        vol_text = "Non disponibile"
    elif previous_vol and previous_vol["close"]:
        diff = (vol["close"] / previous_vol["close"] - 1) * 100
        vol_text = f"{vol['close']:.2f} · {diff:+.2f}%"
    else:
        vol_text = f"{vol['close']:.2f} · variazione N/D"
    return {"range_text": range_text, "range_pct": range_pct,
            "range_points": range_points, "vol_text": vol_text,
            "future_day": future["day"] if future else None,
            "vol_day": vol["day"] if vol else None}


def range_percentage_html(pct):
    """Color only the percentage of the Daily range; keep points neutral."""
    if pct is None:
        return '<span class="range-percent-neutral">Non disponibile</span>'
    value = float(pct)
    if not isfinite(value):
        return '<span class="range-percent-neutral">Non disponibile</span>'
    style = ("range-percent-positive" if value > 0 else
             "range-percent-negative" if value < 0 else "range-percent-neutral")
    return f'<span class="{style}">{value:.2f}%</span>'


def render(market, target_day):
    if market not in SOURCES:
        raise ValueError("Mercato non configurato per il contesto.")
    future_ticker, vol_ticker, vol_name = SOURCES[market]
    future_bars, vol_bars = [], []
    try:
        future_bars = fetch_daily(future_ticker, target_day)
    except Exception:
        pass
    try:
        vol_bars = fetch_daily(vol_ticker, target_day)
    except Exception:
        pass
    result = evaluate(future_bars, vol_bars)
    f_day = result["future_day"].isoformat() if result["future_day"] else "N/D"
    v_day = result["vol_day"].isoformat() if result["vol_day"] else "N/D"
    if result["range_points"] is None:
        range_html = "Non disponibile"
    else:
        range_html = (f"{result['range_points']:,.2f} pt · "
                      f"{range_percentage_html(result['range_pct'])}")
    st.markdown(f"""
<style>
.spx-vol-card {{border:1px solid #34363c;border-radius:13px;padding:14px 18px;
background:#090a0c;color:#f4f5f6;font-family:inherit;}}
.spx-vol-grid {{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:center;}}
.spx-vol-kpi {{padding:5px 18px;min-width:0;border-left:1px solid #292b30;}}
.spx-vol-kpi:first-child {{padding-left:0;border-left:0;}}
.spx-vol-kpi .label {{font-size:.82rem;color:#b6bcc5;margin-bottom:5px;}}
.spx-vol-kpi .number {{font-size:1.15rem;font-weight:740;overflow-wrap:anywhere;}}
.spx-vol-kpi .range-percent-positive {{color:#56d49e;}}
.spx-vol-kpi .range-percent-negative {{color:#ff676d;}}
.spx-vol-kpi .range-percent-neutral {{color:#f4f5f6;}}
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
<div class="number">{range_html}</div></div>
<div class="spx-vol-kpi"><div class="label">{escape(vol_name)} precedente</div>
<div class="number">{escape(result['vol_text'])}</div></div>
<div class="spx-vol-kpi"><div class="label">Buffer standard</div>
<div class="number">Non definito</div></div>
</div>
<div class="spx-vol-foot">Yahoo Finance Daily {escape(future_ticker)}: {escape(f_day)} ·
{escape(vol_ticker)}: {escape(v_day)}.
Solo barre precedenti al giorno di riferimento {target_day:%d/%m/%Y}.
{escape(vol_name)} indica volatilità implicita, NON contango dei futures VX.
Il buffer SPX di 10/15 punti non è trasferibile automaticamente a NQ, GC o CL.
Le barre Yahoo possono differire da quelle dei contratti CME/TradingView.</div>
</div>""", unsafe_allow_html=True)
    if not future_bars or not vol_bars:
        st.caption("Una o più fonti Daily non sono disponibili: la sezione "
                   "mostra N/D senza stime né valori inventati.")
    return result
