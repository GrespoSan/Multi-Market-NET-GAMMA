from datetime import datetime
from zoneinfo import ZoneInfo
import re
import streamlit as st
import hmac

st.set_page_config(page_title="Serafini · Analisi CSV", page_icon="📊", layout="wide")

def verifica_password():
    inserita = st.session_state.pop("password_input", "")
    configurata = st.secrets["APP_PASSWORD"]
    st.session_state.accesso = hmac.compare_digest(inserita.encode(), configurata.encode())

def esci():
    st.session_state.clear()

try:
    password_configurata = st.secrets.get("APP_PASSWORD")
except FileNotFoundError:
    password_configurata = None
if not isinstance(password_configurata, str) or not password_configurata.strip():
    st.error("Configura APP_PASSWORD nei Secrets di Streamlit per abilitare l’accesso.")
    st.stop()
if not st.session_state.get("accesso"):
    st.title("Serafini · Accesso")
    with st.form("login"):
        st.text_input("Password", type="password", key="password_input")
        st.form_submit_button("Accedi", on_click=verifica_password)
    if st.session_state.get("accesso") is False:
        st.error("Password errata.")
    st.stop()
st.sidebar.button("Esci", on_click=esci)
from csv_market import MARKETS, render_market
from offline_snapshot import load_local_snapshot, InvalidLocalSnapshot
from cboe_csv_import import InvalidCboeCSV, csv_coverage_warning
from gamma_section import render
from spx_massive_day_cache import purge_expired
try:
    if purge_expired():
        from daily_volatility import _fetch_massive_es
        _fetch_massive_es.clear()
except OSError:
    pass

st.title("Serafini · Analisi CSV")
st.markdown("""
<style>
[data-testid="stMainBlockContainer"],
[data-testid="stAppViewContainer"] .block-container {
    max-width: none !important;
    width: 100% !important;
    box-sizing: border-box;
    padding-left: clamp(1rem, 2vw, 3rem);
    padding-right: clamp(1rem, 2vw, 3rem);
}
</style>
""", unsafe_allow_html=True)


context_slot = st.empty()
photo_day = None
valid_snapshot = False
upload = None
store = None
with st.expander("ANALISI NET GAMMA", expanded=True):
    st.header("NET GAMMA · formula Serafini")
    market = st.selectbox("Mercato", list(MARKETS))
    equity = market == "Azioni"
    symbol = st.text_input("Ticker azione", value="AAPL").strip().upper() if equity else MARKETS[market]
    st.subheader(f"Fotografia opzioni Cboe · {symbol}")
    upload = st.file_uploader("Carica il CSV della catena opzioni Cboe", type=["csv"], key=f"csv_{market}_{symbol}")
    if upload is not None:
        try:
            if equity and not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol):
                raise ValueError("Ticker azione non valido.")
            if market == "SP500":
                store = load_local_snapshot(upload.name, upload.getvalue())
                warning = csv_coverage_warning(store.import_provenance)
                if warning:
                    st.warning(warning)
                valid_snapshot = True
                week = store.week
                snaps = store.list(f"{week}/snapshots/")
                st.session_state[f"serafini_selected_snapshot_{week}"] = store.filename
                render(store, week, snaps, [], show_heading=False, selector_external=True)
            else:
                photo_day = render_market(upload, symbol, equity)
                valid_snapshot = True
        except (InvalidLocalSnapshot, InvalidCboeCSV, ValueError) as exc:
            st.error(str(exc))

with context_slot.container():
    with st.expander("ANALISI DEL CONTESTO — News · Volatilità · Trend Daily", expanded=False):
        left, middle, right = st.columns([2.2, 1, 1], gap="medium", vertical_alignment="bottom")
        iso = (photo_day or datetime.now(ZoneInfo("Europe/Rome")).date()).isocalendar()
        left.text_input("Settimana ISO (AAAA-WNN)", value=store.week if store else f"{iso.year}-W{iso.week:02d}", disabled=True)
        middle.metric("Snapshot distinti", int(valid_snapshot))
        right.metric("Registri", 0)
        context_details_slot = st.empty()
with context_details_slot.container():
    # L'analisi viene visualizzata automaticamente; il download Massive ES
    # viene gestito dalla cache condivisa giornaliera. Anche con expander
    # chiuso il codice esegue, ma i dati Massive già letti non si riscaricano.
    st.markdown('#### News e calendario macroeconomico')
    from macro_calendar import render as render_macro_calendar
    render_macro_calendar()
    st.divider()

    # Il quadro VX e il Daily usano le proprie fonti CBOE/Massive.
    # La data corrente italiana non dipende dalla presenza di snapshot
    # Supabase, dal numero di registri o dal file CBOE selezionato.
    from vix_regime import render as render_vix_context
    trend_day = datetime.now(ZoneInfo('Europe/Rome')).date()
    es_daily_context = None
    daily_error = None
    try:
        context_data = render_vix_context(trend_day, return_context=True)
        es_daily_context = context_data.get('previous_daily_range')
    except Exception:
        st.info('Il quadro volatilità VX non è disponibile per la giornata corrente.')
        # Il Trend Daily conserva la sua fonte Massive anche se la
        # lettura dei settlement CBOE fallisce.
        try:
            from daily_volatility import previous_es_daily_range
            es_daily_context = previous_es_daily_range(trend_day)
        except Exception:
            daily_error = 'Massive ES non disponibile: verificare Secrets e contratto.'
    st.divider()
    from trend_daily_section import render as render_trend_daily
    es_daily_context = es_daily_context or {}
    render_trend_daily(reference_day=trend_day,
                       daily_bars=es_daily_context.get('daily_bars'),
                       contract=es_daily_context.get('ticker'),
                       daily_error=daily_error,
                       modeled_gex=None)
