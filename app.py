"""Multi-Market NET GAMMA V1 — suspended.

The V2 development branch is 'v2-spx'.
This entrypoint intentionally does not import or initialize ANY
database client, Supabase storage, remote options downloader or cron.
"""
import streamlit as st

st.set_page_config(page_title="Multi-Market NET GAMMA · Sospesa",
                   page_icon="⏸️", layout="wide")
st.title("Multi-Market · NET GAMMA")
st.warning("Versione V1 temporaneamente sospesa.")
st.info("La nuova V2 è in preparazione su un ramo di sviluppo separato, "
        "basato sulla struttura Serafini SPX. "
        "Questa versione non scarica dati e non accede a Supabase.")
st.stop()
