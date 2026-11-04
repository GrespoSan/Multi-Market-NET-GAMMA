"""One-snapshot emergency Pine for the three V2 markets.

Matches SPX emergency's explicit manual download/import interface.
The manual snapshot is shared with the regular NET GAMMA analysis, while
archived snapshots do not auto-populate this panel.
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
        if conversion is None:
            # Continuous alternative: never invent an initial conversion.
            tv = ("COMEX:GC1!/COMEX_MINI:MGC1!" if symbol == "GLD"
                  else "NYMEX:CL1!/NYMEX:MCL1!")
            script = make_etf_future_pine(
                symbol, selected, reference, trade_day, "EMERGENZA CONTINUO",
                None, acquisition_time=capture_time, continuous=True)
            conversion_label = (
                f"{symbol} → {tv}: rapporto dinamico interno TradingView; "
                "anteprima sui soli strike ETF originali")
            factor, shift = 1.0, 0.0
        else:
            if not isinstance(conversion, dict):
                raise ValueError("Rapporto ETF/future non valido.")
            if conversion.get("etf_symbol") != symbol:
                raise ValueError("Rapporto ETF/future di un altro strumento.")
            ratio = _number(conversion.get("ratio"), "Rapporto ETF/future")
            if ratio <= 0:
                raise ValueError("Rapporto ETF/future non valido.")
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
        "projected": symbol == "NDX" or conversion is not None,
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


def _profile_chart(group, *, symbol, title, factor, shift, strike_key, gamma_key,
                   projected=True):
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
    f.update_layout(title=title, template="plotly_dark", height=680,
                    margin=dict(l=20,r=20,t=55,b=45),
                    xaxis_title=f"NET GAMMA {symbol}",
                    yaxis_title=("Prezzo NQ" if symbol == "NDX" else
                                 "Prezzo future equivalente (proiezione ETF)"
                                 if projected else
                                 f"Strike ETF {symbol} · USD (NON prezzi future)"),
                    showlegend=False)
    return f


def _manual_ratio_panel(symbol, trade_day, sha):
    """SPX-like explicit fallback when same-time ETF/future pairing is unavailable."""
    import streamlit as st
    from future_ratio import CONTRACTS, manual_pair
    key = f"v2_emergency_manual_ratio_{symbol}"
    saved = st.session_state.get(key)
    if saved and saved.get("_source_token") != f"{sha}|{trade_day}":
        st.session_state.pop(key, None)
        saved = None
    with st.expander("Inserisci manualmente due prezzi allo stesso orario (alternativa)",
                     expanded=False):
        st.caption("Solo prezzi ETF e future osservati nella STESSA barra a 5 minuti. "
                   "La corrispondenza è dichiarata dall'utente, non verificata.")
        selection = st.selectbox("Contratto future specifico",
                                 list(CONTRACTS[symbol]["contracts"]),
                                 key=f"v2_emergency_contract_{symbol}")
        a, b, c = st.columns(3)
        with a:
            etf_px = st.number_input(f"Prezzo ETF {symbol}", min_value=0.0,
                                     value=0.0, format="%.4f",
                                     key=f"v2_emergency_etf_px_{symbol}")
        with b:
            fut_px = st.number_input("Prezzo future", min_value=0.0, value=0.0,
                                     format="%.4f",
                                     key=f"v2_emergency_fut_px_{symbol}")
        with c:
            time_ny = st.text_input("Ora New York HH:MM", value="15:30",
                                    key=f"v2_emergency_ny_time_{symbol}")
        if st.button("Conferma e blocca coppia manuale",
                     key=f"v2_emergency_lock_manual_{symbol}"):
            try:
                pair = manual_pair(etf_px, fut_px, symbol, selection,
                                   trade_day, time_ny)
                pair["_source_token"] = f"{sha}|{trade_day}"
                st.session_state[key] = pair
                saved = pair
                st.success("Rapporto manuale bloccato per questa fotografia.")
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Coppia manuale non utilizzabile: {str(exc)[:250]}")
    return saved


def _calculate_basis_explicitly(day, key):
    import streamlit as st
    from ndx_basis import fetch_basis
    try:
        try:
            massive_key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
        except Exception:
            massive_key = ""
        result = fetch_basis(day, massive_key)
        st.session_state[key] = f"{result['basis']:.4f}"
        st.session_state.pop(key + "_error", None)
        st.session_state[key + "_details"] = result
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        st.session_state[key + "_error"] = str(exc)[:240]


def render(market_key):
    """Mirror SPX emergency: explicit, independent user click before any charts.

    A new manual Cboe file is then shared with ANALISI NET GAMMA. The
    existing archive never automatically populates this emergency section.
    """
    if market_key not in MARKET_SYMBOL:
        return
    import streamlit as st
    from v2_emergency_acquisition import (
        STORE_PREFIX, download_current_snapshot, use_uploaded_snapshot)

    symbol, future = MARKET_SYMBOL[market_key]
    store_key = STORE_PREFIX + symbol
    with st.expander("PINE DI EMERGENZA — NET GAMMA CORRENTE", expanded=False):
        st.caption(
            "Rilevamento singolo: download CBOE richiesto manualmente o importazione "
            "ZIP/JSON. Nessun Supabase, nessun confronto storico, nessun salvataggio remoto."
        )
        left, right = st.columns(2, gap="medium")
        with left:
            if st.button("Scarica CBOE adesso",
                         key=f"v2_emergency_download_{symbol}",
                         use_container_width=True):
                st.session_state.pop(store_key, None)
                try:
                    with st.spinner("Scaricamento diretto CBOE (solo manuale)..."):
                        active = download_current_snapshot(symbol)
                        st.session_state[f"v2_emergency_pending_activation_{symbol}"] = active
                        st.session_state[store_key] = active
                        st.session_state[f"{store_key}_success"] = (
                            f"Fotografia {symbol} scaricata e validata.")
                    st.rerun()
                except Exception as exc:
                    st.error("Download CBOE non riuscito: " +
                             f"{type(exc).__name__}: {str(exc)[:180]}")
        with right:
            uploaded = st.file_uploader(
                "In alternativa importa ZIP / JSON / JSON.GZ",
                type=["zip", "json", "gz"],
                key=f"v2_emergency_uploader_{symbol}")
            if st.button("Usa file importato",
                         key=f"v2_emergency_import_{symbol}",
                         disabled=uploaded is None, use_container_width=True):
                st.session_state.pop(store_key, None)
                try:
                    active = use_uploaded_snapshot(
                        symbol, uploaded.name, uploaded.getvalue())
                    st.session_state[f"v2_emergency_pending_activation_{symbol}"] = active
                    st.session_state[store_key] = active
                    st.session_state[f"{store_key}_success"] = (
                        f"Fotografia {symbol} importata e validata.")
                    st.rerun()
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    st.error(f"Importazione non valida: {str(exc)[:260]}")

        pending_error = st.session_state.pop(
            f"v2_emergency_activation_error_{symbol}", None)
        if pending_error:
            st.error("Fotografia condivisa non applicabile: " + pending_error)
        active = st.session_state.get(store_key)
        if not active:
            st.info("Scarica una fotografia CBOE oppure importa un file "
                    "per calcolare il Pine corrente.")
            return
        if st.session_state.pop(f"{store_key}_success", None):
            st.success(f"Fotografia {symbol} caricata per il Pine di emergenza.")

        try:
            read, _expiry, _profile, _weekly, close_func, *_ = _model(symbol)
            doc = read(active["content"])
            reference = close_func(doc)
            if reference is None:
                raise ValueError("Chiusura precedente assente nel file Cboe.")
            trade_day = _current_trading_day()
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            st.error(f"Fotografia CBOE non utilizzabile: {str(exc)[:240]}")
            return

        captured = pine_capture_clock(active.get("download_rome"))
        st.markdown(
            f"**Fonte:** {active['source']} · **Data CBOE:** "
            f"{str(active['timestamp'])[:10]} · **timestamp originale:** "
            f"{active['timestamp']} (fuso non dichiarato)"
        )
        if captured["verified"]:
            st.caption("Download effettuato alle " + captured["stamp"] +
                       "; il timestamp CBOE non identifica quell'ora.")
        else:
            st.caption("File importato: l'ora effettiva del download originario "
                       "non è verificabile.")
        sha = hashlib.sha256(active["content"]).hexdigest()

        if symbol == "NDX":
            key = f"v2_emergency_basis_{symbol}_{sha[:16]}"
            if key not in st.session_state:
                existing = str(st.session_state.get("ndx_basis_value", "")).strip()
                st.session_state[key] = existing
            st.markdown("**Differenziale NQ − NDX (chiusure M15 cash precedente)**")
            basis_left, basis_right = st.columns([2.5, 1], gap="small")
            with basis_left:
                text_basis = st.text_input(
                    "Differenziale automatico, correggibile manualmente",
                    key=key, placeholder="Inserisci differenziale NQ−NDX",
                    help="Usa lo stesso riferimento NQ−NDX della V2. "
                         "Controlla il contratto future su TradingView.")
            with basis_right:
                st.markdown('<div style="height:29px"></div>',
                            unsafe_allow_html=True)
                st.button("Ricalcola", key=f"v2_emergency_basis_refresh_{symbol}",
                          on_click=_calculate_basis_explicitly,
                          args=(trade_day, key), use_container_width=True)
            info = st.session_state.get(key + "_details")
            if info:
                st.caption(f"Differenziale ricalcolato {info['basis']:+.4f} punti · "
                           f"contratto {info.get('tv_contract', 'NQ')} · "
                           f"seduta {info.get('reference_date', 'N/D')}.")
            if st.session_state.get(key + "_error"):
                st.warning("Differenziale automatico non disponibile: " +
                           st.session_state[key + "_error"] +
                           ". Puoi inserire un valore verificato manualmente.")
            if not text_basis.strip():
                st.info("Inserisci un differenziale NQ−NDX verificato "
                        "per generare il Pine NQ/MNQ.")
                return
            try:
                conversion = _number(text_basis, "Differenziale NQ−NDX")
            except ValueError as exc:
                st.error(str(exc))
                return
            band = st.session_state.get("ndx_strike_band_percent", 3.0)
            extension = st.session_state.get("v2_ndx_visual_extension", True)
        else:
            from etf_pine_view import prepare_locked_chart_mapping
            band = st.session_state.get(f"{symbol.lower()}_cboe_band", 3.0)
            extension = st.session_state.get(f"v2_{symbol.lower()}_visual_extension", True)
            conversion = prepare_locked_chart_mapping(symbol)
            manual = _manual_ratio_panel(symbol, trade_day, sha)
            if manual is not None:
                conversion = manual
            if conversion is None:
                tv = ("COMEX:GC1!/COMEX_MINI:MGC1!" if symbol == "GLD"
                      else "NYMEX:CL1!/NYMEX:MCL1!")
                st.info(
                    f"Rapporto bloccato {symbol}/future non disponibile. "
                    f"Il Pine sarà comunque generato per {tv}: "
                    "TradingView calcola la conversione su due barre M5 "
                    "sincronizzate e CHIUSE. Se mancano, non disegna livelli. "
                    "I grafici di anteprima qui restano sugli strike ETF originali.")
            else:
                st.markdown(f"**Rapporto {symbol} / future bloccato:** "
                            f"{conversion['ratio']:.8f} · "
                            f"{conversion['future_tv_symbol']}")
                if conversion.get("mode") == "manual-attested":
                    st.caption("Coppia inserita dall'utente: sincronizzazione "
                               "NON verificata indipendentemente.")

        try:
            result = build_current_pine(
                symbol, active["content"], trade_day, reference, conversion,
                band_pct=band, extension=bool(extension),
                capture_time=active.get("download_rome"))
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            st.error(f"NET GAMMA o Pine non generabile: {str(exc)[:300]}")
            return
        st.caption(
            f"Chiusura precedente {symbol} {result['reference']:,.2f} · "
            f"spot CBOE {result['spot']:,.2f} · "
            f"{result['conversion_label']} · "
            f"0DTE {trade_day:%d/%m/%Y} · "
            f"Weekly {result['expiry_weekly']:%d/%m/%Y}."
        )
        left_chart, right_chart = st.columns(2, gap="medium")
        with left_chart:
            st.plotly_chart(
                _profile_chart(result["profiles"]["0DTE"],
                               symbol=symbol, title="NET GAMMA 0DTE · corrente",
                               factor=result["factor"], shift=result["shift"],
                               strike_key=result["strike_key"],
                               gamma_key=result["gamma_key"],
                               projected=result["projected"]),
                use_container_width=True,
                key=f"v2_emergency_{symbol}_odte")
        with right_chart:
            st.plotly_chart(
                _profile_chart(result["profiles"]["Weekly"],
                               symbol=symbol, title="NET GAMMA Weekly · corrente",
                               factor=result["factor"], shift=result["shift"],
                               strike_key=result["strike_key"],
                               gamma_key=result["gamma_key"],
                               projected=result["projected"]),
                use_container_width=True,
                key=f"v2_emergency_{symbol}_weekly")
        if symbol != "NDX":
            st.caption(
                f"Gamma dalle opzioni ETF {symbol}, NON da opzioni sui futures "
                f"{future}. Il Pine continuo converte su TradingView; "
                "nessun rapporto o livello future viene inventato.")
        st.download_button(
            ("Scarica Pine NET GAMMA CONTINUO GC1!/MGC1! o CL1!/MCL1! (.pine)"
             if symbol != "NDX" and conversion is None else
             "Scarica Pine NET GAMMA corrente (.pine)"),
            data=result["pine"].encode("utf-8"),
            file_name=(f"MultiMarket_{symbol}_NET_GAMMA_CONTINUO_{trade_day:%Y%m%d}.pine"
                       if symbol != "NDX" and conversion is None else
                       f"MultiMarket_{symbol}_NET_GAMMA_corrente_{trade_day:%Y%m%d}.pine"),
            mime="text/plain", key=f"v2_emergency_export_{symbol}",
            on_click="ignore", use_container_width=True)
        with st.expander("Mostra codice Pine da copiare"):
            st.code(result["pine"], language="pine")
        st.caption(
            f"Indicatore statico solo {future}: riacquisisci e rigenera "
            "il Pine per aggiornare i livelli. NET GAMMA = "
            "(OI Call + Vol Call) × Gamma Call − (OI Put + Vol Put) × Gamma Put."
        )
