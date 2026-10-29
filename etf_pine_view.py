"""Streamlit Pine v6 export for GLD→GC/MGC and USO→CL/MCL.

The Cboe original profiles remain unchanged. Never equate ETF option
strike levels or ETF Gamma with native futures options.
"""
import streamlit as st
from etf_future_pine import ASSETS, make_etf_future_pine


def render_etf_pine_exports(symbol, calculated, reference, day):
    if symbol not in ASSETS:
        raise ValueError("Modulo Pine non supportato.")
    market = ASSETS[symbol]["label"]
    st.subheader(f"Esportazione Pine Script v6 · {market}")
    st.caption(
        f"Il Pine è utilizzabile solo sui futures {market}. "
        f"Gamma e strike originali provengono dalle opzioni ETF {symbol}, "
        "non dalle opzioni del future. Il Gamma non viene ricalcolato."
    )
    st.warning(
        "ATTENZIONE · Gli strike dell'ETF non coincidono con i prezzi del future. "
        "Per visualizzarli sul future usiamo una mappatura percentuale "
        "(strike ETF / close ETF precedente) × riferimento future. "
        "Non è un differenziale fisso né un supporto/resistenza future validato."
    )
    st.caption(
        "Nel Pine, riferimento future manuale = 0 usa automaticamente il close "
        "Daily precedente del future visualizzato su TradingView. Questo riferimento "
        "può cambiare alla nuova seduta e non essere sincronizzato con l'ETF. "
        "Per fissare i livelli dello snapshot inserisci nelle impostazioni Pine "
        "un prezzo future della stessa sessione del close ETF e verificalo."
    )
    usable = {k: v for k, v in calculated.items()
              if k in ("0DTE", "Principale", "Weekly") and v.get("usable") and v.get("rows")}
    if not usable:
        st.info("Esportazione Pine non disponibile: serve almeno un profilo "
                "NET GAMMA Cboe valido con dati completi.")
        return
    main_key = "0DTE" if "0DTE" in usable else "Principale"
    choices = []
    if main_key in usable:
        choices.append((f"Solo {main_key}", {main_key: usable[main_key]}))
    if "Weekly" in usable:
        choices.append(("Solo Weekly", {"Weekly": usable["Weekly"]}))
    if main_key in usable and "Weekly" in usable:
        choices.append((f"{main_key} + Weekly", usable))

    exports = {}
    for title, selected in choices:
        try:
            script = make_etf_future_pine(
                symbol, selected, reference, day, title
            )
            exports[title] = script
        except Exception as exc:
            st.warning(f"Esportazione {title} non disponibile: {str(exc)[:250]}")
    if not exports:
        return

    cols = st.columns(len(exports))
    for col, (title, script) in zip(cols, exports.items()):
        with col:
            file_part = title.replace(" ", "_").replace("+", "e")
            st.download_button(
                f"Scarica Pine · {title}",
                data=script.encode("utf-8"),
                file_name=f"{symbol}_{market.split()[1].replace('/', '_')}_{day:%Y%m%d}_{file_part}.pine",
                mime="text/plain", on_click="ignore",
                use_container_width=True,
                key=f"{symbol.lower()}_pine_{file_part}",
            )
    with st.expander("Mostra codice Pine da copiare e incollare"):
        choice = st.selectbox("Pine da copiare", list(exports),
                              key=f"{symbol.lower()}_pine_choice")
        st.code(exports[choice], language="javascript")
    st.caption("Il file Pine è statico rispetto ai Gamma della fotografia selezionata; "
               "scarica nuovamente dopo ogni nuovo rilevamento Cboe. "
               "Il controllo sul ticker impedisce il disegno su strumenti diversi "
               "dai futures previsti.")
