"""NQ-NDX previous *cash-session* basis; not valid for contract-specific NQ futures.
Uses the same aligned 15-minute-session principle as the SPX project,
without claiming equivalence to a specific broker's future contract.
"""
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas as pd

NY=ZoneInfo('America/New_York')


def aligned_basis(nq: pd.Series, ndx: pd.Series, day:date):
    if nq.empty or ndx.empty or nq.index.tz is None or ndx.index.tz is None:
        raise ValueError('Dati NQ/NDX vuoti o senza fuso orario')
    x=nq.copy();y=ndx.copy()
    x.index=x.index.tz_convert(NY);y.index=y.index.tz_convert(NY)
    values=pd.concat([pd.to_numeric(x,errors='coerce').rename('NQ'),
                      pd.to_numeric(y,errors='coerce').rename('NDX')],axis=1).dropna().sort_index()
    values=values[~values.index.duplicated(keep='last')]
    values=values[(values.index.time>=time(9,30)) & (values.index.time<time(16))]
    values=values[values.index.date<day]
    dates=sorted(set(values.index.date))
    if not dates:
        raise ValueError('Nessuna seduta precedente comune')
    selected=dates[-1]
    bars=values[values.index.date==selected]
    if len(bars)<20 or bars.index[0].time()>time(9,45) or bars.index[-1].time()<time(15,30):
        raise ValueError(f'Seduta {selected}: dati insufficienti ({len(bars)} barre comuni)')
    delta=bars['NQ']-bars['NDX']
    return {'reference_date':selected,'basis':float(delta.mean()),
            'minimum':float(delta.min()),'maximum':float(delta.max()),
            'last':float(delta.iloc[-1]),'bar_count':len(delta),
            'source':'Yahoo Finance NQ=F / ^NDX · 15m allineati seduta cash precedente'}


def _close(frame, ticker):
    if frame is None or frame.empty:
        raise ValueError(f'Serie Yahoo assente: {ticker}')
    if isinstance(frame.columns,pd.MultiIndex):
        for k in [('Close',ticker),(ticker,'Close')]:
            if k in frame.columns:return frame[k].dropna()
        found=[c for c in frame.columns if 'Close' in c]
        if not found:raise ValueError('Chiusura non trovata')
        return frame[found[0]].dropna()
    return frame['Close'].dropna()


def fetch_basis(day:date):
    import yfinance as yf
    today=datetime.now(NY).date()
    if day > today + timedelta(days=1) or day < today - timedelta(days=50):
        raise ValueError('Data fuori dalla finestra Yahoo a 15 minuti (circa 50 giorni)')
    start=str(day-timedelta(days=10))
    end=str(min(today+timedelta(days=1),day+timedelta(days=1)))
    series={}
    for ticker in ('NQ=F','^NDX'):
        data=yf.download(ticker,start=start,end=end,interval='15m',auto_adjust=False,
                         prepost=False,progress=False,threads=False)
        series[ticker]=_close(data,ticker)
    return aligned_basis(series['NQ=F'],series['^NDX'],day)
