"""Only continuous GC/MGC and CL/MCL Pine exports.

No month selection, Massive API, manual ratio, Yahoo chart fallback,
or stale frozen per-contract mapping. This is the sole ETF Pine interface.
NET GAMMA is always the original Cboe GLD/USO profile.
"""
from __future__ import annotations

import streamlit as st
from etf_future_pine import make_etf_future_pine
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
    # USO/GLD possono NON avere una vera 0DTE nella data dello snapshot.
    # In quel caso il profilo principale resta utile, ma non va etichettato
    # 0DTE o simulato come una delle tre acquisizioni temporali.
    if "0DTE" not in calculated and "Principale" in calculated:
        valid = {
            name: group for name, group in calculated.items()
            if name in ("Principale", "Weekly")
            and group.get("usable") and group.get("rows")
        }
        if "Principale" in valid:
            st.info(
                "Nessuna scadenza 0DTE nella fotografia selezionata. "
                "Il profilo Principale è una scadenza futura reale: "
                "i confronti 0DTE non sono utilizzabili. "
                "È disponibile separatamente il Pine Principale / Weekly."
            )
            try:
                capture = st.session_state.get(f"{symbol.lower()}_cboe_import_rome")
                script = make_etf_future_pine(
                    symbol, valid, reference, day, "PRINCIPALE NON 0DTE",
                    None, acquisition_time=capture, continuous=True)
                # Il codice Pine conserva la data reale delle scadenze:
                # non aggiungiamo notizie storiche senza ora certificata.
                if capture is not None:
                    try:
                        from macro_events import events_for_pine
                        from pine_news_overlay import append_news
                        from v2_pine_capture import pine_capture_clock
                        if pine_capture_clock(capture)["verified"]:
                            script = append_news(
                                script, events_for_pine(day),
                                captured_at=capture)
                    except Exception:
                        pass
                st.download_button(
                    f"Scarica Pine · {label} · Principale + Weekly (non 0DTE)",
                    data=script.encode("utf-8"),
                    file_name=f"{symbol}_PRINCIPALE_WEEKLY_{day:%Y%m%d}.pine",
                    mime="text/plain", on_click="ignore",
                    key=f"v2_{symbol.lower()}_principal_pine_{day:%Y%m%d}",
                    use_container_width=True)
                with st.expander("Mostra codice Pine Principale + Weekly da copiare"):
                    st.code(script, language="pine")
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                st.warning("Pine del profilo principale non disponibile: "
                           + str(exc)[:220])

    st.markdown("**Pine per orari · 07:30 / 15:50 / 20:30**")
    render_timed_pine_exports(
        symbol, day, reference, band, None, extension=extension)
    st.caption("07:30: 0DTE + Weekly · 15:50: confronto 07:30→15:50 · "
               "20:30: confronto 15:50→20:30. "
               "Gli slot senza fotografia valida restano non disponibili. "
               "Pine corrente separato nel modulo di emergenza.")
