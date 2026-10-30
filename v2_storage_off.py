"""Private V2 snapshot selection, visually aligned with Serafini SPX.

Read encrypted GitHub Actions artifacts via read-only API token and Fernet.
Both admin and authenticated friend may view snapshots (SPX-style readers).
The latest available artifact is selected automatically; users can select
another capture or keep an explicitly requested manual Cboe file instead.
No Supabase, unattended delayed_quotes scraping, or plaintext persistence.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from v2_github_archive import (
    list_v2_artifacts, fetch_artifact_snapshot, decrypt_encrypted,
)

ROME = ZoneInfo("Europe/Rome")
AVAILABLE_MARKETS = ("NDX", "GLD", "USO")
SLOTS = {"0730": "Mattina 07:30 Roma",
         "1550": "Pomeriggio 08:50 Chicago",
         "2030": "Sera 13:30 Chicago",
         "manuale": "Rilevamento manuale"}


def prefer_manual_source(symbol):
    """Explicit button/upload takes priority over automatic archive selection."""
    if symbol not in AVAILABLE_MARKETS:
        raise ValueError("Mercato V2 non valido.")
    st.session_state[f"v2_archive_choice_{symbol.lower()}"] = "manuale"


@st.cache_data(ttl=180, show_spinner=False, max_entries=8)
def _cached_artifacts(github_token):
    return list_v2_artifacts(github_token)


@st.cache_data(ttl=1200, show_spinner=False, max_entries=18)
def _cached_snapshot(url, symbol, github_token, key):
    return fetch_artifact_snapshot(url, symbol, github_token, key)


def _archive_label(item):
    stamp = str(item.get("created_at") or "")
    try:
        instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        when = instant.astimezone(ROME).strftime("%d/%m/%Y · %H:%M Roma")
    except ValueError:
        when = "ora non verificabile"
    return f"{when} · {item.get('name', 'rilevamento')}"


def archive_panel(symbol: str):
    """Visible SPX-like capture select, newest automatically; encrypted-only."""
    if symbol not in AVAILABLE_MARKETS:
        raise ValueError("Mercato V2 non valido.")
    try:
        key = str(st.secrets.get("V2_ARCHIVE_FERNET_KEY", "")).strip()
        github_token = str(st.secrets.get("V2_GITHUB_TOKEN", "")).strip()
    except Exception:
        key, github_token = "", ""
    if not github_token or not key:
        with st.expander("RILEVAMENTI PROGRAMMATI · archivio V2", expanded=False):
            st.caption("Tre slot GitHub Actions: 07:30 Roma, 08:50 e 13:30 Chicago. "
                       "La configurazione dell'archivio richiede V2_GITHUB_TOKEN "
                       "(Actions Read) e V2_ARCHIVE_FERNET_KEY nei Secrets della V2. "
                       "Le catene restano importabili manualmente.")
        return None

    col_select, col_refresh = st.columns([3.2, 0.8], gap="small",
                                          vertical_alignment="bottom")
    try:
        artifacts = _cached_artifacts(github_token)
    except Exception:
        st.warning("Archivio V2 non raggiungibile: verifica il token GitHub Actions "
                   "di sola lettura. Rimane disponibile l'importazione manuale.")
        return None

    # "ultimo" is stable across reruns: if a new photograph appears, it
    # automatically follows the newest one. Selecting a historical URL pins it.
    options = (["ultimo", "manuale"] + [item["url"] for item in artifacts[1:]]
               if artifacts else ["manuale"])
    labels = {item["url"]: _archive_label(item) for item in artifacts}
    choice_key = f"v2_archive_choice_{symbol.lower()}"
    if st.session_state.get(choice_key) not in options:
        st.session_state[choice_key] = "ultimo" if artifacts else "manuale"

    with col_select:
        chosen = st.selectbox(
            "Snapshot originale opzioni · archivio automatico",
            options, key=choice_key,
            format_func=lambda url: (
                "ULTIMO rilevamento automatico · " + _archive_label(artifacts[0])
                if url == "ultimo" and artifacts else
                "Fotografia manuale / acquisizione diretta"
                if url == "manuale" else labels.get(url, url)),
            help="Le fotografie programmate sono archiviate cifrate su GitHub "
                 "per 30 giorni. L'ultima è proposta per impostazione predefinita.",
        )
    with col_refresh:
        if st.button("Aggiorna elenco", key=f"v2_{symbol.lower()}_gh_refresh",
                     use_container_width=True):
            _cached_artifacts.clear()
            st.session_state[choice_key] = "ultimo" if artifacts else "manuale"
            st.rerun()

    if chosen == "manuale":
        st.caption("Modalità manuale: i file caricati o scaricati su richiesta "
                   "non vengono sovrascritti dall'archivio.")
    else:
        try:
            chosen_url = artifacts[0]["url"] if chosen == "ultimo" else chosen
            packed, filename = _cached_snapshot(
                chosen_url, symbol, github_token, key)
            parts = filename.split("_")
            slot = next((SLOTS.get(p, "") for p in parts if p in SLOTS), "")
            # Filename carries the REAL capture UTC time; unlike GitHub
            # artifact created_at it records acquisition, not upload time.
            from datetime import timezone
            stamp = datetime.strptime(parts[1], "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc)
            st.session_state[f"v2_archive_capture_rome_{symbol}"] = stamp.astimezone(
                ROME).isoformat(timespec="seconds")
            st.session_state[f"v2_archive_capture_nyday_{symbol}"] = stamp.astimezone(
                ZoneInfo("America/New_York")).date()
            st.session_state[f"v2_archive_slot_{symbol}"] = slot or "Slot non verificabile"
            st.caption(f"Fotografia archivio V2: {slot or 'slot non verificabile'} · "
                       f"acquisita {stamp.astimezone(ROME):%d/%m/%Y %H:%M} Roma · "
                       f"file {filename} · conservata cifrata su GitHub.")
            return packed, filename
        except Exception:
            st.warning("Il rilevamento selezionato non contiene un JSON cifrato "
                       f"{symbol} utilizzabile. Il job potrebbe essere partito "
                       "senza una fonte opzioni autorizzata; seleziona un altro "
                       "rilevamento o la modalità manuale.")

    if st.session_state.get("v2_role") == "admin":
        with st.expander("Importazione eccezionale di file cifrato (.enc)",
                         expanded=False):
            st.caption("Usare solo file cifrati provenienti dalla V2; la chiave "
                       "privata rimane nei Secrets Streamlit.")
            uploaded = st.file_uploader(
                f"File {symbol} (.json.gz.enc)", type=["enc"],
                key=f"v2_{symbol.lower()}_encrypted",
            )
            if uploaded is not None and st.button(
                    "Decifra file", key=f"v2_{symbol.lower()}_decrypt"):
                try:
                    packed = decrypt_encrypted(uploaded.getvalue(), key)
                    prefer_manual_source(symbol)
                    return packed, uploaded.name.removesuffix(".enc")
                except Exception:
                    st.error("File o chiave archivio V2 non validi.")
    return None
