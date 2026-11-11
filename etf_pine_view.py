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
    if symbol not in CONTINUOUS_LABELS:
        raise ValueError("Mercato ETF non riconosciuto.")
    label = CONTINUOUS_LABELS[symbol]
    st.subheader(f"Pine Script v6 · Future continuo {label}")
    st.caption("Gamma delle opzioni Cboe invariati. Conversione degli strike "
               "effettuata direttamente su TradingView, con rapporto da due "
               "barre M5 chiuse con identico timestamp. "
               "Non vengono usati Massive o contratti a scadenza.")
    valid = {name: group for name, group in calculated.items()
             if name in ("0DTE", "Principale", "Weekly")
             and group.get("usable") and group.get("rows")}
    if not valid:
        st.caption("Nessun profilo Cboe completo disponibile per l'esportazione.")
        return

    try:
        script = make_etf_future_pine(
            symbol, valid, reference, day, "CONTINUO",
            None,
            acquisition_time=st.session_state.get(
                f"{symbol.lower()}_cboe_import_rome"),
            continuous=True)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        st.caption(f"Pine non generabile da questa fotografia: {str(exc)[:210]}")
        return

    # SPX parity: same verified BLS+FinanceCalendar news, only after
    # the actual Cboe capture. Manually imported files have no verified
    # acquisition instant and must NOT acquire fictitious future-only news.
    source = str(st.session_state.get(f"{symbol.lower()}_cboe_source") or "")
    captured = st.session_state.get(f"{symbol.lower()}_cboe_import_rome")
    if ("Archivio privato" in source or "Acquisizione diretta" in source):
        try:
            from macro_events import events_for_pine
            from pine_news_overlay import append_news
            from v2_pine_capture import pine_capture_clock
            if pine_capture_clock(captured)["verified"]:
                script = append_news(script, events_for_pine(day),
                                     captured_at=captured)
        except Exception:
            # News source outage never changes validated Gamma levels.
            st.caption("News macro non verificabili: Pine senza linee news; "
                       "i livelli NET GAMMA rimangono invariati.")

    st.download_button(
        f"Scarica Pine NET GAMMA · {label} (.pine)",
        script.encode("utf-8"),
        file_name=f"{symbol}_NET_GAMMA_CONTINUO_{day:%Y%m%d}.pine",
        mime="text/plain", on_click="ignore",
        key=f"v2_only_continuous_pine_{symbol}_{day}",
        use_container_width=True)
    with st.expander("Mostra codice Pine continuo da copiare"):
        st.code(script, language="pine")

    st.caption("TradingView: TF 1m/5m. Se manca una coppia ETF/future "
               "sincronizzata, il Pine non disegna livelli non verificati.")
    band = float(st.session_state.get(f"{symbol.lower()}_cboe_band", 3.0))
    extension = bool(st.session_state.get(
        f"v2_{symbol.lower()}_visual_extension", True))
    with st.expander("Pine per orari · 07:30 / 15:50 / 20:30", expanded=False):
        render_timed_pine_exports(
            symbol, day, reference, band, None, extension=extension)
