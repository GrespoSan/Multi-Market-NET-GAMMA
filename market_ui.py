"""One shared Streamlit layout for Nasdaq, Gold and Petrolio.

Keep only market-specific metadata different. Acquisition, import, archive
position, title sizes, spacing and empty states are deliberately identical.
No Cboe calculations, price mapping or Pine generation in this module.
"""
import streamlit as st

MARKET_DISPLAY = {
    "NASDAQ": (
        "Nasdaq 100 · NDX",
        "Opzioni NDX/NDXP Cboe  ·  Grafici NQ/MNQ con differenziale NQ−NDX",
    ),
    "GOLD": (
        "Gold · GLD",
        "Opzioni ETF GLD Cboe  ·  Pine GC/MGC con rapporto ETF/future bloccato (proiezione indicativa)",
    ),
    "WTI": (
        "Petrolio · USO",
        "Opzioni ETF USO Cboe  ·  Pine CL/MCL con rapporto ETF/future bloccato (proiezione indicativa)",
    ),
}

UPLOAD_KEYS = {
    "NDX": "ndx_upload",
    "GLD": "gld_cboe_upload",
    "USO": "uso_cboe_upload",
}

PAGE_STYLE = """
<style>
/* One responsive page width and vertical rhythm for every market. */
[data-testid="stAppViewContainer"] .block-container {
    max-width: 1460px;
    padding-top: 2.25rem;
    padding-bottom: 3.5rem;
}
@media (max-width: 800px) {
    [data-testid="stAppViewContainer"] .block-container {
        padding-top: 1.15rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
}
</style>
"""


def render_dashboard_header(markets):
    """The same title/selector block, irrespective of the current market."""
    st.markdown(PAGE_STYLE, unsafe_allow_html=True)
    st.title("Multi-Market · NET GAMMA")
    st.caption("RADAR OPZIONI  ·  NDX / GLD / USO  ·  0DTE & WEEKLY  ·  modello di studio Serafini")
    left, right = st.columns([1.35, 2.65], gap="large")
    with left:
        key = st.selectbox(
            "Sottostante", list(markets),
            format_func=lambda k: markets[k].label,
            key="mm_market",
        )
    with right:
        _, description = MARKET_DISPLAY[key]
        st.caption(description)
    st.divider()
    return key


def render_acquisition_controls(symbol, source_url):
    """Reusable acquisition UI: primary button, collapsed import, source notice.

    Returns only UI intent; market-specific caller does ALL validation/state
    updates and may keep the last usable snapshot if a request fails.
    The archive panel follows immediately afterward in all three callers.
    """
    if symbol not in UPLOAD_KEYS:
        raise ValueError("Sottostante grafico non riconosciuto.")
    st.subheader(f"Fotografia opzioni Cboe · {symbol}")
    clicked = st.button(
        f"Aggiorna fotografia {symbol} da Cboe",
        type="primary",
        key=f"{symbol.lower()}_cboe_fetch",
    )
    with st.expander("Importazione manuale JSON originale", expanded=False):
        st.link_button(f"Apri file {symbol}.json su Cboe", source_url)
        uploaded = st.file_uploader(
            f"Carica file {symbol} (.json o .json.gz)",
            type=["json", "gz"], key=UPLOAD_KEYS[symbol],
        )
    st.caption(
        "Fonte: Cboe delayed quotes · Il timestamp originale è mostrato senza "
        "attribuire un fuso orario non documentato. "
        "I rilevamenti programmati richiedono un feed autorizzato."
    )
    return clicked, uploaded


def render_empty_snapshot(symbol):
    if symbol not in UPLOAD_KEYS:
        raise ValueError("Sottostante non riconosciuto.")
    st.info(f"Nessuna fotografia {symbol} caricata. Acquisisci da Cboe, "
            "importa il JSON originale oppure seleziona un rilevamento "
            "dall'archivio, se disponibile.")
