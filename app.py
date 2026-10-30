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
from v2_market_engine import render_selected_market

st.set_page_config(page_title="Serafini · Multi-Market NET GAMMA V2",
                   page_icon="📊", layout="wide")

# Same SPX-style wide interface and reserved access, but separate credentials.
st.title("Serafini · Multi-Market — NET GAMMA V2")
st.caption("NDX / NQ · GLD / GC · USO / CL · 0DTE / Weekly · interfaccia SPX")

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
    if st.button("Esci", key="v2_logout"):
        st.session_state.pop("v2_role", None)
        st.rerun()
    st.caption("V2 indipendente · nessun collegamento Supabase")

col_market, col_info = st.columns([1.2, 2.8], gap="medium",
                                  vertical_alignment="bottom")
with col_market:
    market_key = st.selectbox(
        "Sottostante", list(MARKETS),
        format_func=lambda key: MARKETS[key].label,
        key="v2_market_selected",
    )
with col_info:
    market = MARKETS[market_key]
    st.caption(f"Opzioni: {market.options} · Futuro: {market.futures} · "
               f"Metodo: {market.basis}")
st.divider()

context_initial = datetime.now(ZoneInfo("Europe/Rome")).hour < 13
with st.expander("ANALISI DEL CONTESTO — News · Volatilità · Trend Daily",
                 expanded=context_initial):
    st.markdown("#### Contesto dello strumento")
    st.caption("La struttura della sezione segue SPX. Gli indicatori di contesto "
               "specifici SPX (VIX, ES e range asiatico) non vengono applicati "
               "artificialmente a GLD e USO.")
    st.write(f"**Mercato selezionato:** {MARKETS[market_key].label}")
    st.info("Contesto News/volatilità/trend specifico di ciascun mercato "
            "ancora da integrare e validare: nessun segnale inventato.")

with st.expander("ANALISI NET GAMMA", expanded=True):
    render_selected_market(market_key)

# No GEX EDGE, REPLAY E CONFRONTO, or REPORT GIORNALIERO AI.
# Cboe snapshot management stays inside the market-specific gamma analysis
# via v2_storage_off.archive_panel, not via Supabase.
