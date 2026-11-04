"""One-snapshot emergency Pine for the three V2 markets.

Shares the already-loaded Cboe snapshot with ANALISI NET GAMMA: NO second
Cboe download, upload, GitHub archive query, Supabase, or scheduled pairing.
Uses the existing NDX/GLD/USO formulas and existing NQ/GC/CL exporters.
ETF GEX on futures remains an INDICATIVE price projection, not GC/CL options.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from v2_pine_timed_exports import _model
from v2_pine_capture import pine_capture_clock
from v2_visual_extension import expanded_display
from pine_export import make_pine
from etf_future_pine import make_etf_future_pine

NY = ZoneInfo("America/New_York")
ROME = ZoneInfo("Europe/Rome")
MARKET_SYMBOL = {"NASDAQ": ("NDX", "NQ/MNQ"),
                 "GOLD": ("GLD", "GC/MGC"),
                 "WTI": ("USO", "CL/MCL")}
SOURCE_KEYS = {
    "NDX": ("ndx_blob", "ndx_name", "ndx_source", "ndx_capture_rome_iso"),
    "GLD": ("gld_cboe_raw", "gld_cboe_file", "gld_cboe_source", "gld_cboe_import_rome"),
    "USO": ("uso_cboe_raw", "uso_cboe_file", "uso_cboe_source", "uso_cboe_import_rome"),
}


def _number(value, name):
    try:
        v = float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name}: valore non disponibile.") from exc
    if not math.isfinite(v):
        raise ValueError(f"{name}: numero non finito.")
    return v


def _source_near_session(timestamp, trade_day):
    """Date-only conservative safeguard; Cboe clock timezone is unverified.

    UTC source dates can be +/- one calendar day from New York. The
    date check is NOT a certification of data freshness or capture time.
    """
    try:
        source_day = date.fromisoformat(str(timestamp)[:10])
    except (ValueError, TypeError) as exc:
        raise ValueError("Timestamp Cboe mancante: non etichettare il Pine come corrente.") from exc
    if abs((source_day - trade_day).days) > 1:
        raise ValueError(f"Fotografia Cboe del {source_day:%d/%m/%Y}: "
                         f"troppo distante dalla seduta {trade_day:%d/%m/%Y}. "
                         "Importa o acquisisci una fotografia più recente.")
    return source_day


def build_current_pine(symbol, raw, trade_day, reference, conversion, *,
                       band_pct=3.0, extension=True, capture_time=None):
    """Build one static 0DTE+Weekly Pine from ONE supplied original Cboe blob.

    No IO or Streamlit widgets. The caller supplies the actual New York
    session date, existing reference and validated futures conversion.
    """
    if symbol not in SOURCE_KEYS or not isinstance(trade_day, date):
        raise ValueError("Mercato o seduta non riconosciuti.")
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("Fotografia Cboe originale mancante.")
    reference = _number(reference, "Close precedente")
    if reference <= 0:
        raise ValueError("Close precedente non positivo.")
    band_pct = _number(band_pct, "Fascia strike")
    if not 0 < band_pct <= 10:
        raise ValueError("Fascia strike fuori da 0-10%.")
    read, expiries, profile, weekly_target, _, strike_key, gamma_key = _model(symbol)
    doc = read(raw)
    source_day = _source_near_session(doc.get("timestamp"), trade_day)
    present = expiries(doc)
    if trade_day not in present:
        raise ValueError(f"0DTE del {trade_day:%d/%m/%Y} non presente nella fotografia "
                         f"{symbol}; non sostituiamo con una scadenza futura.")
    weekly = weekly_target(trade_day, present)
    if weekly is None or weekly == trade_day:
        raise ValueError("Prossima scadenza Weekly di venerdì non disponibile "
                         "nella catena originale: Pine combinato non generato.")
    spot = _number(doc.get("data", {}).get("current_price"), "Spot Cboe")
    if spot <= 0:
        raise ValueError("Spot Cboe non positivo.")
    selected = {}
    for key, expiry in (("0DTE", trade_day), ("Weekly", weekly)):
        core = profile(doc, expiry, reference, band_pct=band_pct)
        if not core.get("rows") or (symbol != "NDX" and not core.get("usable")):
            raise ValueError(f"{key}: Gamma Cboe incompleti o non utilizzabili.")
        result = core
        if extension:
            maximum = 20.0 if symbol == "NDX" else 10.0
            result, _ = expanded_display(
                core, lambda width, exp=expiry: profile(
                    doc, exp, reference, band_pct=width),
                reference, spot, band_pct, strike_field=strike_key,
                gamma_field=gamma_key, upper_band_limit=maximum)
        if not result.get("rows"):
            raise ValueError(f"{key}: nessuno strike reale da disegnare.")
        selected[key] = result
    # Keep all genuine selected strikes; the existing exporter refuses
    # exceeding TradingView's limit instead of silently dropping data.
    if symbol == "NDX":
        basis = _number(conversion, "Differenziale NQ-NDX")
        script = make_pine(
            selected, basis, trade_day, "EMERGENZA CORRENTE",
            acquisition_time=capture_time)
        conversion_label = f"NQ−NDX {basis:+.2f} punti"
        factor = 1.0
        shift = basis
    else:
        if not isinstance(conversion, dict):
            raise ValueError("Rapporto ETF/future bloccato non disponibile.")
        if conversion.get("etf_symbol") != symbol:
            raise ValueError("Rapporto ETF/future di un altro strumento.")
        ratio = _number(conversion.get("ratio"), "Rapporto ETF/future")
        if ratio <= 0:
            raise ValueError("Rapporto ETF/future non valido.")
        # The existing ETF exporter verifies matched prices and contract.
        script = make_etf_future_pine(
            symbol, selected, reference, trade_day, "EMERGENZA CORRENTE",
            conversion, acquisition_time=capture_time)
        conversion_label = (
            f"{symbol} → {conversion['future_tv_symbol']} · "
            f"rapporto bloccato {ratio:.8f}")
        factor, shift = ratio, 0.0
    if not script.startswith("//@version=6\n") or script.count("indicator(") != 1:
        raise ValueError("Pine v6: intestazione non valida.")
    return {
        "pine": script, "profiles": selected, "trade_day": trade_day,
        "expiry_weekly": weekly, "source_day": source_day,
        "source_stamp": str(doc["timestamp"]), "spot": spot,
        "reference": reference, "sha256": hashlib.sha256(raw).hexdigest(),
        "conversion_label": conversion_label, "factor": factor,
        "shift": shift, "symbol": symbol,
        "contract_count": len(doc["data"]["options"]),
        "strike_key": strike_key, "gamma_key": gamma_key,
    }


def _snapshot_in_session(symbol):
    raw_key, name_key, source_key, capture_key = SOURCE_KEYS[symbol]
    raw = st.session_state.get(raw_key)
    if not isinstance(raw, bytes) or not raw:
        return None
    origin = st.session_state.get(source_key, "origine non documentata")
    # Import time is NOT the original Cboe download time. Archive fallback
    # can also be mere time of loading into Streamlit; ignore it unless
    # independently verified in the archive capture metadata.
    capture = (None if "Importazione manuale" in str(origin) else
               st.session_state.get(f"v2_archive_capture_rome_{symbol}")
               if "Archivio" in str(origin) else
               st.session_state.get(capture_key))
    return {
        "raw": raw, "name": st.session_state.get(name_key, "file senza nome"),
        "source": origin, "capture": capture,
    }


def _current_trading_day(now=None):
    """New York date; after 18:00 NY the next weekday session starts.

    Availability is still verified against the genuine option chain.
    Holidays do not fabricate expiries: missing dates block the export.
    """
    now = now or datetime.now(NY)
    if now.tzinfo is None:
        raise ValueError("Ora New York priva di fuso orario.")
    ny = now.astimezone(NY)
    day = ny.date() + timedelta(days=1) if ny.hour >= 18 else ny.date()
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _profile_chart(group, *, symbol, title, factor, shift, strike_key, gamma_key):
    import plotly.graph_objects as go
    rows = group["rows"]
    y = [float(r[strike_key]) * factor + shift for r in rows]
    x = [float(r[gamma_key]) for r in rows]
    f = go.Figure(go.Bar(
        x=x, y=y, orientation="h",
        marker_color=["#22c55e" if n >= 0 else "#ef4444" for n in x],
        hovertemplate="Prezzo %{y:,.2f}<br>NET GAMMA %{x:+.4f}<extra></extra>",
    ))
    f.add_vline(x=0, line_color="#9ca3af", line_width=1)
    f.update_layout(title=title, template="plotly_dark", height=590,
                    margin=dict(l=20,r=20,t=55,b=45),
                    xaxis_title=f"NET GAMMA {symbol}",
                    yaxis_title=("Prezzo NQ" if symbol == "NDX" else
                                 "Prezzo future equivalente (proiezione ETF)"),
                    showlegend=False)
    return f


def render(market_key):
    if market_key not in MARKET_SYMBOL:
        return
    symbol, future = MARKET_SYMBOL[market_key]
    with st.expander("PINE DI EMERGENZA — NET GAMMA CORRENTE", expanded=False):
        st.caption(
            f"Un solo rilevamento {symbol} per {future}; stessa fotografia già "
            "acquisita/importata in ANALISI NET GAMMA. Nessun secondo download "
            "o upload, nessuna dipendenza dagli slot storici, nessun Supabase "
            "e nessun salvataggio remoto. Il Pine è statico."
        )
        source = _snapshot_in_session(symbol)
        if source is None:
            st.info(f"Nessun file {symbol} disponibile. Apri ANALISI NET GAMMA "
                    "→ Acquisizione Cboe / importazione manuale e scarica o importa "
                    "una fotografia originale. Sarà condivisa automaticamente qui.")
            return
        capture = pine_capture_clock(source["capture"])
        sha = hashlib.sha256(source["raw"]).hexdigest()
        st.markdown(f"**Fotografia condivisa:** {source['name']} · {source['source']}")
        st.caption(f"SHA-256 {sha[:16]}… · Acquisizione: {capture['stamp']} "
                   "(non è l'orario dei dati Cboe).")
        if not capture["verified"]:
            st.warning("Ora acquisizione non verificata. Il file importato potrebbe "
                       "non essere aggiornato; il timestamp Cboe non prova l'ora di download.")
        trade_day = _current_trading_day()
        # Display-only. Do not infer today's date from a historic file or
        # relabel a future expiry as an 0DTE.
        st.caption(f"Scadenza 0DTE attesa per la sessione NY: "
                   f"{trade_day:%d/%m/%Y}. Un 0DTE assente BLOCCA l'esportazione.")
        if symbol == "NDX":
            reference = st.session_state.get("v2_ndx_reference_current")
            if reference is None:
                from ndx_engine import close_from_payload, unpack_snapshot
                try:
                    reference = close_from_payload(unpack_snapshot(source["raw"]))
                except (ValueError, TypeError):
                    reference = None
            conversion = st.session_state.get("ndx_basis_value")
            band = st.session_state.get("ndx_strike_band_percent", 3.0)
            extension = st.session_state.get("v2_ndx_visual_extension", True)
        else:
            reference = st.session_state.get(f"{symbol.lower()}_cboe_reference")
            band = st.session_state.get(f"{symbol.lower()}_cboe_band", 3.0)
            extension = st.session_state.get(f"v2_{symbol.lower()}_visual_extension", True)
            # The existing, snapshot-locked price pair is the ONLY permitted
            # mapping. Never use a stale ratio from another Cboe filename.
            from etf_pine_view import prepare_locked_chart_mapping
            conversion = prepare_locked_chart_mapping(symbol)
            if conversion is None:
                st.warning("Rapporto ETF/future sincronizzato non disponibile "
                           "per questa fotografia. Verifica il calcolo o inserisci "
                           "la coppia manuale nello stesso pannello Pine sopra.")
                return
        try:
            result = build_current_pine(
                symbol, source["raw"], trade_day, reference, conversion,
                band_pct=band, extension=bool(extension),
                capture_time=source["capture"])
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            st.warning("PINE CORRENTE non disponibile: " + str(exc)[:300])
            return

        st.caption(
            f"Timestamp Cboe originale: {result['source_stamp']} "
            "(fuso del campo non certificato) · "
            f"Close precedente {result['reference']:,.2f} · "
            f"Spot {result['spot']:,.2f} · {result['conversion_label']}."
        )
        st.markdown(
            f"**NET GAMMA {symbol} — 0DTE {trade_day:%d/%m} "
            f"e Weekly {result['expiry_weekly']:%d/%m}**"
        )
        cols = st.columns(2, gap="medium")
        for col, kind in zip(cols, ("0DTE", "Weekly")):
            with col:
                fig = _profile_chart(
                    result["profiles"][kind], symbol=symbol, title=kind,
                    factor=result["factor"], shift=result["shift"],
                    strike_key=result["strike_key"], gamma_key=result["gamma_key"])
                st.plotly_chart(fig, use_container_width=True,
                                key=f"v2_emergency_{symbol}_{kind}")
        if symbol != "NDX":
            st.warning(f"Gamma da opzioni ETF {symbol}, NON da opzioni "
                       f"sui futures {future}. I livelli {future} sono "
                       "proiezioni indicative con rapporto bloccato.")
        st.download_button(
            f"Scarica Pine NET GAMMA corrente {future} (.pine)",
            data=result["pine"].encode("utf-8"),
            file_name=f"MultiMarket_{symbol}_NET_GAMMA_corrente_{trade_day:%Y%m%d}.pine",
            mime="text/plain", key=f"v2_emergency_export_{symbol}",
            on_click="ignore", use_container_width=True)
        with st.expander("Mostra codice Pine da copiare"):
            st.code(result["pine"], language="pine")
        st.caption("NET = (OI Call + Volume Call) × Gamma Call − "
                   "(OI Put + Volume Put) × Gamma Put. "
                   "Un nuovo snapshot richiede rigenerare il Pine. "
                   "Il calcolo non indica posizioni dealer osservate.")
