"""Confronto facoltativo NET GAMMA Nasdaq e prezzi NQ a 5 minuti.

OHLC da Yahoo NQ=F; gli strike NDX+base sono sulla stessa asse y del future.
Non modifica i calcoli NET GAMMA o il differenziale NQ−NDX.
"""
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
import math

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

ROME = ZoneInfo("Europe/Rome")
UTC = timezone.utc


@st.cache_data(ttl=300, show_spinner=False, max_entries=12)
def load_nq_candles(day):
    """Only real closed NQ=F 5m candles in the calendar day, Rome timezone."""
    start = datetime.combine(day, time.min, tzinfo=ROME)
    finish = start + timedelta(days=1)
    current = datetime.now(UTC)
    if (current - start.astimezone(UTC)).days > 59:
        raise ValueError("Lo storico Yahoo 5 minuti non copre oltre 59 giorni.")
    if current <= start.astimezone(UTC):
        raise ValueError("Questa giornata non è ancora iniziata.")
    raw = yf.download(
        "NQ=F", start=(day-timedelta(days=1)).isoformat(),
        end=(day+timedelta(days=2)).isoformat(), interval="5m",
        prepost=True, auto_adjust=False, progress=False, threads=False,
    )
    if raw is None or raw.empty:
        raise ValueError("Yahoo non ha restituito le candele NQ=F.")
    if isinstance(raw.columns, pd.MultiIndex):
        for n in range(raw.columns.nlevels):
            if "Close" in raw.columns.get_level_values(n):
                raw.columns=raw.columns.get_level_values(n)
                break
    fields=("Open","High","Low","Close")
    if raw.index.tz is None or any(field not in raw for field in fields):
        raise ValueError("Barre Yahoo senza orario o campi OHLC.")
    timestamps=raw.index.tz_convert(ROME)+pd.Timedelta(minutes=5)
    bars=pd.DataFrame(
        {name.lower():pd.to_numeric(raw[name],errors="coerce").to_numpy()
         for name in fields},
        index=timestamps,
    )
    bars=bars.loc[(bars.index>=start) & (bars.index<finish) &
                  (bars.index<=pd.Timestamp(current).tz_convert(ROME))]
    bars=bars.dropna(subset=[name.lower() for name in fields])
    if bars.empty:
        raise ValueError("Nessuna candela NQ a 5 minuti chiusa per la giornata.")
    bars.index.name="bar_close"
    return bars.reset_index()


def chart_compare_nq(profile, candles, basis, lower_ndx, upper_ndx, close_nq, kind):
    """NET GAMMA on left, 5m candles on right, exact shared futures-price scale."""
    if not math.isfinite(float(basis)):
        raise ValueError("Differenziale NQ-NDX non valido.")
    rows=profile["rows"]
    if not rows:
        raise ValueError("Profilo NET GAMMA senza strike nella fascia.")
    prices=[float(row["strike_index"])+basis for row in rows]
    net=[float(row["net_gamma"]) for row in rows]
    lower=min(lower_ndx+basis, float(candles["low"].min()),float(close_nq))
    upper=max(upper_ndx+basis, float(candles["high"].max()),float(close_nq))
    pad=max((upper-lower)*0.025, 5.0)
    fig=make_subplots(
        rows=1, cols=2, shared_yaxes=True,
        column_widths=[0.4,0.6], horizontal_spacing=0.04,
        subplot_titles=(f"NET GAMMA {kind}", "PREZZO NQ · 5 minuti"),
    )
    gaps=[b-a for a,b in zip(prices,prices[1:]) if b>a]
    width=min(3.8, min(gaps)*0.8) if gaps else 3.8
    fig.add_trace(go.Bar(
        x=net,y=prices,orientation="h",width=width,
        marker_color=["#21cb82" if x>=0 else "#f34e59" for x in net],
        name="NET GAMMA",
        customdata=[float(row["strike_index"]) for row in rows],
        hovertemplate="NQ %{y:,.2f}<br>NDX %{customdata:,.2f}<br>NET %{x:+.5f}<extra></extra>",
        showlegend=False,
    ),row=1,col=1)
    fig.add_trace(go.Candlestick(
        x=candles["bar_close"],open=candles["open"],
        high=candles["high"],low=candles["low"],close=candles["close"],
        increasing_line_color="#21b77c",decreasing_line_color="#e65353",
        name="NQ=F",showlegend=False,
    ),row=1,col=2)
    for col in (1,2):
        fig.add_hline(y=float(close_nq), line_color="#f0cc65",
                      line_width=1.5,line_dash="dash",row=1,col=col)
        fig.add_hline(y=lower_ndx+basis,line_color="#a1a1aa",
                      opacity=0.45,line_width=1,line_dash="dot",row=1,col=col)
        fig.add_hline(y=upper_ndx+basis,line_color="#a1a1aa",
                      opacity=0.45,line_width=1,line_dash="dot",row=1,col=col)
        fig.update_yaxes(range=[lower-pad,upper+pad], row=1,col=col)
    fig.update_layout(
        height=710,margin=dict(l=35,r=20,t=65,b=45),
        template="plotly_dark",barmode="relative",showlegend=False,
    )
    fig.update_yaxes(title_text="Prezzo NQ",row=1,col=1)
    fig.update_xaxes(title_text="NET GAMMA",row=1,col=1)
    fig.update_xaxes(title_text="Ora Roma",rangeslider_visible=False,row=1,col=2)
    return fig
