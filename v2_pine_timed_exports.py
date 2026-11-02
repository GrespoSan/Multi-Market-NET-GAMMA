"""SPX-style scheduled Cboe snapshot Pine exports for NDX, GLD and USO V2.

07:30: original 0DTE + Weekly.
15:50: 07:30 0DTE + 15:50 0DTE + 15:50 Weekly.
20:30: 15:50 0DTE + 20:30 0DTE + 20:30 Weekly.

No missing 13:30 slot is forged: unlike SPX, V2 only schedules 3 slots.
No external futures/ETF quote downloads here: mapping is supplied and frozen.
"""
from datetime import date
from time import monotonic

import streamlit as st

from v2_pine_session import SLOTS, LABELS
from v2_pine_capture import pine_capture_clock
from v2_storage_off import load_pine_slot_captures
from v2_pine_comparison import make_pine_comparison_v2
from pine_export import make_pine
from etf_future_pine import make_etf_future_pine
from v2_visual_extension import expanded_display

EXPLANATIONS = {
    "0730": "07:30 · 0DTE + Weekly",
    "1550": "07:30 0DTE → 15:50 0DTE + Weekly",
    "2030": "15:50 0DTE → 20:30 0DTE + Weekly",
}


def _model(symbol):
    if symbol == "NDX":
        from ndx_engine import (unpack_snapshot as read, available_expirations,
                                profile, weekly_target, close_from_payload)
        return read, available_expirations, profile, weekly_target, close_from_payload, "strike_index", "net_gamma"
    if symbol == "GLD":
        from gld_cboe import read_gld, expirations, profile, next_weekly, close_previous
        return read_gld, expirations, profile, next_weekly, close_previous, "strike", "net"
    if symbol == "USO":
        from uso_cboe import read_uso, expirations, profile, next_weekly, close_previous
        return read_uso, expirations, profile, next_weekly, close_previous, "strike", "net"
    raise ValueError("Mercato sconosciuto.")


def build_slot_profiles(symbol, captures, day, reference, band,
                        extension=True):
    """Recalculate exactly the existing formula on each genuine archived JSON.

    Every 0DTE is guaranteed to be the same NY market day and expiry.
    Weekly is the same actual next Friday expiry when available. Missing,
    incomplete or different-date profiles are reported, not fabricated.
    """
    read, expiries, profile, weekly_target, close_from_payload, strike_key, gamma_key = _model(symbol)
    result = {}
    issues = {}
    for slot, capture in captures.items():
        try:
            doc = read(capture["raw"])
            actual = expiries(doc)
            if day not in actual:
                raise ValueError("0DTE non presente nella catena Cboe reale.")
            friday = weekly_target(day, actual)
            if friday is None:
                raise ValueError("Weekly successiva non disponibile nella catena.")
            core_main = profile(doc, day, reference, band_pct=band)
            core_week = profile(doc, friday, reference, band_pct=band)
            if not core_main.get("rows") or not core_week.get("rows"):
                raise ValueError("Gamma 0DTE/Weekly incompleti.")
            if symbol != "NDX" and not (
                    core_main.get("usable") and core_week.get("usable")):
                raise ValueError("Catena ETF: Gamma incompleti o coverage insufficiente.")
            main, week = core_main, core_week
            if extension:
                spot = doc.get("data", {}).get("current_price")
                spot = float(spot) if spot not in (None, "") else reference
                max_band = 20.0 if symbol == "NDX" else 10.0
                main, _ = expanded_display(
                    core_main, lambda width: profile(
                        doc, day, reference, band_pct=width),
                    reference, spot, band,
                    strike_field=strike_key, gamma_field=gamma_key,
                    upper_band_limit=max_band)
                week, _ = expanded_display(
                    core_week, lambda width: profile(
                        doc, friday, reference, band_pct=width),
                    reference, spot, band,
                    strike_field=strike_key, gamma_field=gamma_key,
                    upper_band_limit=max_band)
            observed_close = close_from_payload(doc)
            result[slot] = {"0DTE": main, "Weekly": week,
                            "capture": capture, "close": observed_close}
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            issues[slot] = str(exc)[:190]
    return result, issues


def produce_timed_scripts(symbol, day, captures, reference, band,
                          basis_or_mapping, *, extension=True,
                          macro_news=None):
    """Pure (except supplied Cboe parse) deterministic schedule -> scripts."""
    if not isinstance(day, date):
        raise ValueError("Data della seduta non valida.")
    profiles, issues = build_slot_profiles(
        symbol, captures, day, reference, band, extension=extension)
    scripts = {}
    for slot in SLOTS:
        if slot not in profiles:
            issues.setdefault(slot, "Fotografia Cboe di questo slot non disponibile.")
            continue
        now = profiles[slot]
        try:
            if slot == "0730":
                if symbol == "NDX":
                    script = make_pine(
                        {"0DTE":now["0DTE"], "Weekly":now["Weekly"]},
                        float(basis_or_mapping), day, EXPLANATIONS[slot],
                        acquisition_time=now["capture"]["rome"])
                else:
                    script = make_etf_future_pine(
                        symbol, {"0DTE":now["0DTE"], "Weekly":now["Weekly"]},
                        reference, day, EXPLANATIONS[slot],
                        basis_or_mapping, acquisition_time=now["capture"]["rome"])
            else:
                prev_slot = "0730" if slot == "1550" else "1550"
                if prev_slot not in profiles:
                    raise ValueError(f"Manca 0DTE precedente {LABELS[prev_slot]}.")
                prev = profiles[prev_slot]
                details = {}
                script = make_pine_comparison_v2(
                    symbol, prev["0DTE"], now["0DTE"], now["Weekly"],
                    basis_or_mapping, day, prev["capture"], now["capture"],
                    prev_slot, slot,
                    etf_previous_close=reference if symbol != "NDX" else None,
                    export_details=details)
                if details.get("note"):
                    now["pine_display_note"] = details["note"]
            if macro_news and symbol == "NDX":
                from pine_news_overlay import append_news
                script = append_news(script, macro_news)
            scripts[slot] = script
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            issues[slot] = str(exc)[:190]
    return scripts, issues, profiles


def render_timed_pine_exports(symbol, day, reference, band, basis_or_mapping,
                              *, extension=True, macro_news=None):
    """Use only the authenticated 30-day V2 artifact archive, not live Cboe."""
    st.caption("Come in SPX: Pine 07:30, confronto 07:30→15:50 e confronto "
               "15:50→20:30; ogni confronto usa soltanto fotografie reali "
               "della stessa seduta di New York. Gli orari effettivi sono "
               "indicati in CET/CEST. Nessun Gamma inventato.")
    # First view loads same-day GitHub archives automatically just like SPX.
    # Subsequent Streamlit reruns reuse the session and underlying 20min cache;
    # refresh requires an explicit click and never touches Massive quota.
    key = f"v2_pine_times_{symbol}_{day.isoformat()}"
    state = st.session_state.get(key)
    refresh = st.button("Aggiorna Pine per orari", key=f"refresh_{key}")
    # When later scheduled captures arrive, a normal rerun can discover
    # them without a manual refresh. Only archive APIs, never Massive.
    loaded_at = st.session_state.get(key + "_loaded_at", 0.0)
    incomplete = state is None or len(state) < len(SLOTS)
    stale = incomplete and monotonic() - loaded_at >= 180
    if state is None or refresh or stale:
        try:
            with st.spinner("Lettura rilevamenti cifrati 07:30 / 15:50 / 20:30..."):
                captures = load_pine_slot_captures(symbol, day)
            state = {slot: {**capture} for slot, capture in captures.items()}
            st.session_state[key] = state
            st.session_state[key + "_loaded_at"] = monotonic()
        except Exception as exc:
            st.warning("Archivio temporaneamente non disponibile: "
                       + str(exc)[:180])
            state = None
    if state is None:
        st.info("Non riesco a leggere le fotografie orarie dall'archivio "
                "GitHub. Nessun profilo o confronto viene simulato.")
        return

    scripts, issues, profiles = produce_timed_scripts(
        symbol, day, state, reference, band, basis_or_mapping,
        extension=extension, macro_news=macro_news)

    cols = st.columns(3, gap="small")
    for col, slot in zip(cols, SLOTS):
        with col:
            if slot in scripts:
                script = scripts[slot]
                st.download_button(
                    "Scarica Pine · " + EXPLANATIONS[slot],
                    data=script.encode("utf-8"),
                    file_name=f"{symbol}_NET_GAMMA_{day:%Y%m%d}_{slot}.pine",
                    mime="text/plain", on_click="ignore",
                    key=f"{symbol}_timed_{day}_{slot}",
                    use_container_width=True)
                clock = pine_capture_clock(profiles[slot]["capture"]["rome"])
                st.caption(f"Acquisizione reale: {clock['stamp']}")
                if profiles[slot].get("pine_display_note"):
                    st.warning(profiles[slot]["pine_display_note"])
            else:
                st.button("Pine " + EXPLANATIONS[slot] + " · non disponibile",
                          disabled=True, key=f"{symbol}_missing_{day}_{slot}",
                          use_container_width=True)
                st.caption(issues.get(slot, "Fotografia non disponibile."))

    if scripts:
        with st.expander("Mostra codice Pine da copiare e incollare"):
            selected = st.selectbox(
                "Pine orario", list(scripts),
                format_func=lambda slot: EXPLANATIONS[slot],
                key=f"v2_timed_code_{symbol}_{day}")
            st.code(scripts[selected], language="pine")
    else:
        st.warning("Nessuna esportazione oraria possibile: verifica le "
                   "fotografie effettivamente presenti nell'archivio GitHub.")
