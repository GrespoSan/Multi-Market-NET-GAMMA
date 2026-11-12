"""Only continuous GC/MGC and CL/MCL Pine exports.

No month selection, Massive API, manual ratio, Yahoo chart fallback,
or stale frozen per-contract mapping. This is the sole ETF Pine interface.
NET GAMMA is always the original Cboe GLD/USO profile.
"""
from __future__ import annotations

import streamlit as st
from v2_pine_timed_exports import render_timed_pine_exports

CONTINUOUS_LABELS = {
    "GLD": "GC1! / MGC1!",
    "USO": "CL1! / MCL1!",
}


def render_etf_pine_exports(symbol, calculated, reference, day,
                            source_sha=None, cboe_stamp=None):
    """Esportazioni orarie GC/CL: nessun doppio Pine della fotografia corrente.

    Il Pine corrente resta disponibile nel modulo di emergenza indipendente.
    Il mapping dei future continui e la logica degli archivi orari
    rimangono di competenza di render_timed_pine_exports().
    """
    if symbol not in CONTINUOUS_LABELS:
        raise ValueError("Mercato ETF non riconosciuto.")
    label = CONTINUOUS_LABELS[symbol]
    st.subheader(f"Esportazione Pine Script v6 · Future continuo {label}")
    st.caption("Gamma originali Cboe GLD/USO · proiezione su future continuo "
               "con rapporto sincronizzato su TradingView. "
               "I file orari utilizzano solo acquisizioni realmente archiviate.")

    band = float(st.session_state.get(f"{symbol.lower()}_cboe_band", 3.0))
    extension = bool(st.session_state.get(
        f"v2_{symbol.lower()}_visual_extension", True))
    st.markdown("**Pine per orari · 07:30 / 15:50 / 20:30**")
    render_timed_pine_exports(
        symbol, day, reference, band, None, extension=extension)
    st.caption("07:30: 0DTE + Weekly · 15:50: confronto 07:30→15:50 · "
               "20:30: confronto 15:50→20:30. "
               "Gli slot senza fotografia valida restano non disponibili. "
               "Pine corrente separato nel modulo di emergenza.")
