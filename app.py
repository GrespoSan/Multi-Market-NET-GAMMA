"""Multi-Market NET GAMMA V2 · SPX dashboard architecture.

Visual/navigation shell adapted from Serafini-SPX-Dashboard/app.py.
Removed by design: GEX EDGE, Replay e confronto, Report giornaliero AI.
Market-specific NDX/GLD/USO engines are preserved in v2_market_engine.py.
No Supabase connection, credentials, storage imports or scheduled fetches.
"""
import hmac
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from markets import MARKETS
from market_ui import PAGE_STYLE
from v2_market_engine import render_selected_market
from v2_massive_day_cache import purge_expired, invalidate_ratio_sessions

st.set_page_config(page_title="Serafini · Multi-Market NET GAMMA V2",
                   page_icon="📊", layout="wide")

# On the first UI event after Rome midnight, delete yesterday's temporary
# disk cache and session-frozen ratios. NEVER touch Cboe GitHub artifacts.
try:
    cache_day_changed = purge_expired()
except OSError:
    cache_day_changed = False  # Read-through if host temp disk unavailable.
if invalidate_ratio_sessions(st.session_state) or cache_day_changed:
    # Streamlit's separate 1h Daily/NQ caches must not outlive Rome midnight.
    st.cache_data.clear()
    from future_ratio import _cl_cached_json
    _cl_cached_json.cache_clear()

# Same SPX-style wide interface and reserved access, but separate credentials.
st.markdown(PAGE_STYLE, unsafe_allow_html=True)
st.title("Serafini · Multi-Market — NET GAMMA")

def _secret(name):
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""

admin_password = _secret("V2_ADMIN_PASSWORD")
viewer_password = _secret("V2_FRIENDS_PASSWORD")
if not admin_password or not viewer_password or hmac.compare_digest(
        admin_password.encode(), viewer_password.encode()):
    st.error("V2 in preparazione: configura nei Secrets della NUOVA app "
             "V2_ADMIN_PASSWORD e V2_FRIENDS_PASSWORD (distinte). "
             "Non riutilizzare o copiare le chiavi Supabase della SPX.")
    st.stop()

@st.cache_resource
def login_limiter():
    return {"failures": {}, "lock": threading.Lock()}


def check_password(candidate, expected):
    return hmac.compare_digest(candidate.encode("utf-8"),
                               expected.encode("utf-8"))


if st.session_state.get("v2_role") not in ("admin", "friend"):
    st.subheader("Accesso riservato")
    with st.form("v2_auth", clear_on_submit=True):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Accedi")
    if submitted:
        limiter = login_limiter()
        if "v2_login_id" not in st.session_state:
            import secrets
            st.session_state["v2_login_id"] = secrets.token_hex(16)
        key = st.session_state["v2_login_id"]
        now = time.monotonic()
        with limiter["lock"]:
            n, deadline = limiter["failures"].get(key, (0, 0.0))
            locked = now < deadline
        if locked:
            st.error("Troppi tentativi. Riprova più tardi.")
        else:
            role = ("admin" if check_password(password, admin_password) else
                    "friend" if check_password(password, viewer_password) else None)
            if role:
                with limiter["lock"]:
                    limiter["failures"].pop(key, None)
                st.session_state["v2_role"] = role
                st.rerun()
            else:
                with limiter["lock"]:
                    n += 1
                    limiter["failures"][key] = (n, now + 300 if n >= 5 else 0)
                st.error("Password non corretta.")
    st.stop()

role = st.session_state["v2_role"]
with st.sidebar:
    st.write("**Accesso:** " + ("Amministratore" if role == "admin" else "Lettore"))
    # Identico a Serafini SPX: entrambi i ruoli autorizzati possono rileggere
    # le fonti senza uscire o perdere password, selezioni e fotografie manuali.
    if st.button("🔄 Aggiorna dati", key="v2_sidebar_refresh",
                 use_container_width=True,
                 help="Aggiorna archivi, dati recenti e Pine UNICO senza nuovo login o download Cboe."):
        from v2_refresh import refresh_multimarket_data
        refresh_multimarket_data(st.session_state)
        st.toast("Aggiornamento richiesto: ricarico i dati disponibili.", icon="🔄")
    if st.button("Esci", key="v2_logout"):
        st.session_state.pop("v2_role", None)
        st.rerun()
    st.caption("V2 indipendente · nessun collegamento Supabase")

st.subheader("01 · MERCATI PRINCIPALI")
st.caption("NDX / NQ · RUT / RTY · DJX / YM · GLD / GC · USO / CL · 0DTE / Weekly")

# Two independent functional areas. The market selector controls only
# NDX/GLD/USO panels; the universal CBOE tool has its own ticker input.
with st.container(border=True):
    st.caption("Seleziona il mercato. Analisi, differenziale ed export riguardano solo lo strumento scelto.")
    col_market, col_info = st.columns([1.2, 2.8], gap="medium",
                                      vertical_alignment="bottom")
    with col_market:
        market_key = st.selectbox(
            "Mercato da analizzare", list(MARKETS),
            format_func=lambda key: MARKETS[key].label,
            key="v2_market_selected",
        )
    with col_info:
        market = MARKETS[market_key]
        st.caption(f"Opzioni: {market.options} · Futuro: {market.futures} · "
                   f"Metodo: {market.basis}")
    
    # The emergency controls are below the main analysis, so their callbacks
    # cannot modify main widgets after those widgets have been instantiated.
    # Apply pending manual Cboe capture at the START of the next rerun.
    symbol_for_market = {"NASDAQ": "NDX", "GOLD": "GLD", "WTI": "USO", "RUSSELL": "RUT", "DOW": "DJX"}[market_key]
    activation_key = f"v2_emergency_pending_activation_{symbol_for_market}"
    pending = st.session_state.pop(activation_key, None) if market_key in ("NASDAQ", "GOLD", "WTI") else None
    if pending is not None:
        try:
            from v2_emergency_acquisition import activate_for_analysis
            activate_for_analysis(symbol_for_market, pending)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            from v2_emergency_acquisition import STORE_PREFIX
            st.session_state.pop(STORE_PREFIX + symbol_for_market, None)
            st.session_state[f"v2_emergency_activation_error_{symbol_for_market}"] = str(exc)[:260]
    
    # Preserve CONTEXTO above NET GAMMA visually, but execute its optional
    # Massive requests AFTER Gamma's reference mapping. A collapsed expander still
    # runs all its code in Streamlit; this ordering prioritizes the trading panel.
    context_slot = st.empty()
    context_initial = False
    
    with st.expander("ANALISI NET GAMMA", expanded=False):
        st.header("NET GAMMA · formula Serafini")
        with st.expander("Note metodologiche · differenze rispetto alla SPX",
                         expanded=False):
            if market_key == "NASDAQ":
                st.caption("Opzioni NDX/NDXP · proiezione indicativa su NQ/MNQ mediante "
                           "differenziale NQ−NDX. Formula Call/Put invariata.")
            elif market_key in ("RUSSELL", "DOW"):
                st.caption(
                    "Opzioni originali " + ("RUT/RUTW" if market_key == "RUSSELL" else "DJX/DJXW") +
                    " · differenziale future/indice verificato. "
                    "DJX: conversione strike ×100 prima del differenziale YM−DJIA. "
                    "NET GAMMA CBOE invariato, non rappresenta opzioni sui futures.")
            else:
                st.caption("Opzioni ETF " + ("GLD" if market_key == "GOLD" else "USO")
                           + " · profili Gamma sui veri strike dell'ETF. "
                           "La mappatura percentuale su future è indicativa e NON "
                           "trasforma queste opzioni in opzioni su GC o CL.")
            st.caption("0DTE e Weekly: stesso criterio grafico della Serafini SPX; "
                       "Gamma da (OI + Volume) × Gamma, non GEX monetario. "
                       "Le proporzioni 60%/23% citate per SPX non sono "
                       "automaticamente valide per NDX, GLD e USO.")
        render_selected_market(market_key)
    
    # A collapsed Streamlit expander still executes its body. External macro,
    # Yahoo and Massive requests run only when this market's context is enabled.
    # The shared Daily caches and Roma-midnight invalidation remain unchanged.
    with context_slot.container():
        context_key = f"v2_context_requested_{market_key}"
        if market_key in ("RUSSELL", "DOW"):
            with st.expander("ANALISI DEL CONTESTO — News macro USA",
                             expanded=context_initial):
                if st.toggle("Carica calendario macro USA",
                             key=context_key, value=False,
                             help="Disattiva per evitare richieste esterne nei successivi aggiornamenti della pagina."):
                    from macro_calendar import render as render_macro_calendar
                    render_macro_calendar()
                    st.caption("Trend e volatilità specifici di Russell/Dow non ancora verificati; "
                               "nessun dato di un altro mercato viene attribuito a questi indici.")
                else:
                    st.caption("Calendario in pausa: attiva il caricamento quando serve.")
        else:
            with st.expander("ANALISI DEL CONTESTO — News · Volatilità · Trend Daily",
                             expanded=context_initial):
                if st.toggle("Carica News · Volatilità · Trend Daily",
                             key=context_key, value=False,
                             help="Disattiva per sospendere le richieste Massive, Yahoo e macro quando la sezione non serve."):
                    from v2_context import render as render_market_context
                    render_market_context(market_key)
                else:
                    st.caption("Contesto in pausa: attiva il caricamento quando serve.")

    # One shared snapshot per market: the emergency export reuses the same
    # session-state photograph; no redundant download/import widgets.
    if market_key in ("NASDAQ", "GOLD", "WTI"):
        from v2_emergency_pine import render as render_v2_emergency_pine
        render_v2_emergency_pine(market_key)
    else:
        st.caption("Pine dedicato Russell/Dow disponibile nella sezione Analisi Net Gamma dopo aver verificato il basis.")

st.write("")
# Independent 07:30 experimental unified export. No changes to the
# five existing per-market Pine export sections or gamma engines.
from v2_unified_pine import render as render_unified_0730
render_unified_0730()

st.subheader("02 · NET GAMMA UNIVERSALE — CBOE")
st.caption("Strumento indipendente: inserisci qualsiasi ticker CBOE supportato, senza cambiare il mercato principale.")

# Independent ticker-input CBOE engine; never touches selected market state.
from v2_universal_cboe import render as render_universal_cboe
render_universal_cboe()

# No GEX EDGE, REPLAY E CONFRONTO, or REPORT GIORNALIERO AI.
# Cboe snapshot management stays inside the market-specific gamma analysis
# via v2_storage_off.archive_panel, not via Supabase.
