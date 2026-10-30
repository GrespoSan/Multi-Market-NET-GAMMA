"""V2 snapshot reader: NO Supabase connection, no remote storage calls.

Scheduled encrypted GitHub Actions artifacts may be imported manually.
The private Fernet key lives only in V2 Streamlit Secrets, never in GitHub.
"""
import streamlit as st


def archive_panel(symbol: str):
    with st.expander("RILEVAMENTI CBOE · 07:30 / 15:50 / 20:30", expanded=False):
        st.caption(
            "Fotografie programmate V2: disponibili solo con feed autorizzato. "
            "Non sono collegate al bucket SPX né al bucket V1."
        )
        st.info("Supabase completamente disattivato. Le fotografie cifrate "
                "possono essere scaricate dagli artifact GitHub Actions e "
                "importate qui, oppure si può usare il download manuale Cboe.")
        try:
            secret = str(st.secrets.get("V2_ARCHIVE_FERNET_KEY", "")).strip()
        except Exception:
            secret = ""
        if not secret:
            st.caption("Per leggere gli artifact cifrati, configura "
                       "V2_ARCHIVE_FERNET_KEY nei Secrets di questa app.")
            return None
        if st.session_state.get("v2_role") != "admin":
            st.caption("L'importazione degli archivi è riservata all'amministratore.")
            return None
        uploaded = st.file_uploader(
            f"Carica fotografia {symbol} cifrata (.json.gz.enc)",
            type=["enc"], key=f"v2_{symbol.lower()}_encrypted",
        )
        if not uploaded:
            return None
        if st.button("Decifra e carica questa fotografia", key=f"v2_{symbol.lower()}_decrypt"):
            try:
                from cryptography.fernet import Fernet
                if uploaded.size > 120 * 1024 * 1024:
                    raise ValueError("File archivio troppo grande.")
                packed = Fernet(secret.encode("ascii")).decrypt(uploaded.getvalue())
                if len(packed) > 80 * 1024 * 1024:
                    raise ValueError("File decifrato supera il limite previsto.")
                if not packed.startswith(b"\x1f\x8b"):
                    raise ValueError("Il contenuto non è un originale JSON gzip.")
                return packed, uploaded.name.removesuffix(".enc")
            except Exception:
                st.error("Impossibile decifrare o validare l'archivio. "
                         "Controlla file e chiave V2 senza divulgarla.")
    return None
