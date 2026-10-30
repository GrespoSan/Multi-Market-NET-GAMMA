"""No-Supabase V2 snapshot browser, matching SPX archived-capture workflow.

Only encrypted GitHub Actions artifacts are loaded (server-side Github read
token + Fernet key); never access Supabase or its credentials.
"""
import streamlit as st

from v2_github_archive import (
    list_v2_artifacts, fetch_artifact_snapshot, decrypt_encrypted,
)


def archive_panel(symbol: str):
    with st.expander("RILEVAMENTI CBOE · 07:30 Roma / 08:50 e 13:30 Chicago",
                     expanded=False):
        st.caption("Archivio indipendente dalla SPX e dalla V1: "
                   "fotografie V2 cifrate, conservate negli artifact GitHub "
                   "(30 giorni). Nessuna connessione Supabase.")
        if st.session_state.get("v2_role") != "admin":
            st.caption("Archivio riservato all'amministratore.")
            return None
        try:
            key = str(st.secrets.get("V2_ARCHIVE_FERNET_KEY", "")).strip()
            github_token = str(st.secrets.get("V2_GITHUB_TOKEN", "")).strip()
        except Exception:
            key, github_token = "", ""
        if not key:
            st.info("Per aprire le fotografie cifrate, configura "
                    "V2_ARCHIVE_FERNET_KEY nei Secrets della V2.")
            return None

        if github_token:
            if st.button("Elenca rilevamenti GitHub", key=f"v2_{symbol.lower()}_gh_list"):
                try:
                    with st.spinner("Lettura elenco delle fotografie cifrate..."):
                        st.session_state["v2_github_artifacts"] = list_v2_artifacts(
                            github_token)
                except Exception:
                    st.error("Elenco GitHub non accessibile: verifica token Actions "
                             "di sola lettura e permessi sul repository.")
            options = st.session_state.get("v2_github_artifacts", [])
            if options:
                selected = st.selectbox(
                    "Rilevamento programmato",
                    options,
                    format_func=lambda x: f"{x['created_at']} · {x['name']}",
                    key=f"v2_{symbol.lower()}_gh_selected",
                )
                if st.button("Carica fotografia " + symbol + " da GitHub",
                             key=f"v2_{symbol.lower()}_gh_download"):
                    try:
                        with st.spinner("Lettura e decifratura in memoria..."):
                            packed, name = fetch_artifact_snapshot(
                                selected["url"], symbol, github_token, key)
                        st.success("Fotografia " + symbol + " caricata dall'archivio.")
                        return packed, name
                    except Exception as exc:
                        st.warning("Questo artifact non contiene una fotografia "
                                   f"{symbol} utilizzabile o non è accessibile. "
                                   "L'acquisizione del relativo slot potrebbe "
                                   "essere stata saltata.")
        else:
            st.caption("Per elencare e caricare direttamente i rilevamenti, "
                       "aggiungi V2_GITHUB_TOKEN (fine-grained PAT con "
                       "Actions: Read) nei Secrets Streamlit.")

        with st.expander("Caricamento manuale di un artifact cifrato",
                         expanded=False):
            uploaded = st.file_uploader(
                f"File {symbol} (.json.gz.enc) dall'artifact GitHub",
                type=["enc"], key=f"v2_{symbol.lower()}_encrypted",
            )
            if uploaded is not None and st.button(
                    "Decifra e carica file", key=f"v2_{symbol.lower()}_decrypt"):
                try:
                    packed = decrypt_encrypted(uploaded.getvalue(), key)
                    st.success("Fotografia cifrata caricata.")
                    return packed, uploaded.name.removesuffix(".enc")
                except Exception:
                    st.error("File o chiave V2 non validi. Non condividere "
                             "la chiave di decifratura.")
    return None
