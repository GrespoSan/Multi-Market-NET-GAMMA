"""Optional archive browser: load authorized scheduled snapshots from private storage.

No service-role key is sent to the browser. The archive only appears when
the owner has configured Streamlit secrets and the separate private bucket.
"""
from datetime import datetime, timedelta
import hmac
from zoneinfo import ZoneInfo

import streamlit as st

from multimarket_archive import read_archive_config
from scheduled_slots import week_key

ROME = ZoneInfo("Europe/Rome")


def archive_panel(symbol):
    """Returns (original_gz, filename) only when user explicitly selects Load."""
    key = symbol.lower()
    with st.expander("Archivio automatico · 07:30 / 15:50 / 20:30",
                     expanded=False):
        st.caption("Le fotografie si archiviano soltanto quando è configurato "
                   "un feed autorizzato. I vecchi rilevamenti non vengono "
                   "ricreati retroattivamente.")
        try:
            config = read_archive_config(st.secrets)
        except Exception:
            config = None
        if config is None:
            st.info("Archivio privato non collegato a Streamlit: configura i secret "
                    "SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY e il bucket "
                    "multi-market-snapshots. I log delle esecuzioni sono comunque "
                    "visibili in GitHub Actions.")
            return None
        try:
            expected_code = str(st.secrets.get("MM_ARCHIVE_ACCESS_CODE", ""))
        except Exception:
            expected_code = ""
        if not expected_code:
            st.warning("Accesso all'archivio sospeso: configura MM_ARCHIVE_ACCESS_CODE "
                       "nei secret Streamlit per proteggere i dati di mercato privati.")
            return None
        if not st.session_state.get("mm_archive_unlocked", False):
            entered = st.text_input("Codice accesso archivio privato",
                                    type="password", key="mm_archive_passphrase")
            if st.button("Sblocca archivio", key=f"{key}_archive_unlock"):
                if hmac.compare_digest(entered, expected_code):
                    st.session_state["mm_archive_unlocked"] = True
                    st.rerun()
                else:
                    st.error("Codice archivio non valido.")
            return None
        if not st.button("Elenca fotografie archiviate", key=f"{key}_archive_list"):
            # Avoid a hidden network call on every Streamlit rerun.
            stored = st.session_state.get(f"{key}_archive_options", [])
        else:
            try:
                weeks = [week_key(datetime.now(ROME)),
                         week_key(datetime.now(ROME) - timedelta(days=7))]
                found = []
                for week in dict.fromkeys(weeks):
                    prefix = f"snapshots/{symbol}/{week}/"
                    for item in config.list(prefix):
                        name = item["name"]
                        if name.endswith(".json.gz"):
                            found.append((name, prefix + name))
                stored = sorted(set(found), reverse=True)[:60]
                st.session_state[f"{key}_archive_options"] = stored
            except Exception as exc:
                st.warning(f"Archivio non accessibile: {type(exc).__name__}. "
                           "Controllare le credenziali server e il bucket privato.")
                return None
        if not stored:
            st.caption("Nessuna fotografia disponibile nell'archivio delle ultime due settimane.")
            return None
        paths = [p for _, p in stored]
        selected = st.selectbox("Rilevamento", paths,
                                format_func=lambda p: p.split("/")[-1].replace("_", " "),
                                key=f"{key}_archive_choice")
        if st.button("Carica questa fotografia", type="secondary",
                     key=f"{key}_archive_load"):
            try:
                raw = config.download(selected)
                return raw, selected.split("/")[-1]
            except Exception as exc:
                st.error(f"Impossibile leggere la fotografia: {type(exc).__name__}.")
    return None
