"""Faithful Serafini SPX ANALISI DEL CONTESTO layout for Multi-Market V2.

Uses SPX macro calendar / M7 source modules and the same Daily trend engine,
with market-specific futures, VXN/GVZ/OVX and no Supabase. Displays only
verified archive counts, never SPX historical numbers attributed to V2.
"""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from v2_volatility import render as render_volatility, SOURCES
from v2_trend_daily import render as render_trend_daily

ROME = ZoneInfo("Europe/Rome")


def week_choice():
    today = datetime.now(ROME).date()
    iso = today.isocalendar()
    choice = st.text_input("Settimana ISO (AAAA-WNN)",
                           value=f"{iso.year}-W{iso.week:02d}",
                           key="v2_context_iso_week")
    if not re.fullmatch(r"\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])", choice):
        st.error("Settimana ISO non valida (AAAA-WNN).")
        st.stop()
    year, week = int(choice[:4]), int(choice[-2:])
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        st.error("La settimana ISO non esiste nell'anno scelto.")
        st.stop()
    return choice


def selected_snapshot_day(market):
    if market not in SOURCES:
        return None
    if market == "NASDAQ":
        raw = st.session_state.get("ndx_blob")
        if not raw:
            return None
        try:
            from ndx_engine import unpack_snapshot
            stamp = str(unpack_snapshot(raw).get("timestamp") or "")
        except Exception:
            return None
    else:
        symbol = "gld" if market == "GOLD" else "uso"
        stamp = str(st.session_state.get(f"{symbol}_cboe_timestamp") or "")
        if not stamp:
            # The original Cboe timestamp may not yet have been persisted to
            # session_state if analysis was never opened.
            raw = st.session_state.get(f"{symbol}_cboe_raw")
            if raw:
                try:
                    from gld_cboe import read_gld
                    from uso_cboe import read_uso
                    parser = read_gld if symbol == "gld" else read_uso
                    stamp = str(parser(raw).get("timestamp") or "")
                except Exception:
                    return None
    try:
        return date.fromisoformat(stamp[:10])
    except ValueError:
        return None


@st.cache_data(ttl=300, show_spinner=False, max_entries=20)
def _artifact_registers(token, week):
    from v2_github_archive import list_v2_artifacts
    rows = list_v2_artifacts(token)
    matched = []
    for row in rows:
        try:
            created = datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ).astimezone(ROME)
            iso = created.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
            if key == week:
                matched.append(row)
        except (TypeError, ValueError, KeyError):
            continue
    return matched


def render(market):
    # Identical top row and heading hierarchy to SPX app.py.
    col_week, col_snapshots, col_logs = st.columns(
        [2.2, 1, 1], gap="medium", vertical_alignment="bottom")
    with col_week:
        week = week_choice()

    source_day = selected_snapshot_day(market)
    local_today = datetime.now(ROME).date()
    reference_day = source_day or local_today
    display_day = reference_day.strftime("%d/%m/%Y")

    with col_snapshots:
        # An encrypted GitHub artifact can contain 0, 1, 2 or 3 markets;
        # therefore artifact count MUST NEVER be called snapshot count.
        st.metric("Snapshot distinti", "—")
    with col_logs:
        try:
            github_token = str(st.secrets.get("V2_GITHUB_TOKEN", "")).strip()
        except Exception:
            github_token = ""
        if github_token:
            try:
                registers = _artifact_registers(github_token, week)
                st.metric("Registri", len(registers))
            except Exception:
                st.metric("Registri", "—")
        else:
            st.metric("Registri", "—")
    st.caption("Snapshot distinti: conteggio globale non ancora verificabile "
               "nell'archivio cifrato V2. I registri, se disponibili, indicano "
               "esecuzioni GitHub e non garantiscono l'acquisizione di una catena.")
    st.markdown("#### News e calendario macroeconomico")
    from macro_calendar import render as render_macro_calendar
    render_macro_calendar()
    st.divider()
    st.markdown("#### Volatilità — seduta precedente")
    if source_day is None:
        st.caption("Nessuna fotografia Cboe selezionata: si utilizza la data odierna "
                   f"{display_day} come riferimento per le barre Daily precedenti.")
    else:
        st.caption(f"Fotografia di riferimento: {display_day} (data Cboe originale, "
                   "fuso non documentato).")
    render_volatility(market, reference_day)
    st.divider()
    symbol, _, _ = SOURCES[market]
    names = {
        "NASDAQ": "Nasdaq 100 / NQ",
        "GOLD": "Gold / GC",
        "WTI": "Petrolio WTI / CL",
    }
    render_trend_daily(reference_day=reference_day, ticker=symbol,
                       market_name=names[market])
