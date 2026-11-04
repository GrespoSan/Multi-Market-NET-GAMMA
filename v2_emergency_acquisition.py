"""SPX-style manual Cboe acquisition for V2 emergency Pine.

One manual acquisition point for NDX/GLD/USO. Files stay in memory.
Once validated, the SAME original bytes feed the main NET GAMMA analysis.
No Supabase, no background polling, no hidden archive snapshot adoption.
"""
from __future__ import annotations

from datetime import datetime
import gzip
from zoneinfo import ZoneInfo

from v2_manual_import import normalize_manual_upload
from v2_pine_timed_exports import _model

ROME = ZoneInfo("Europe/Rome")
SOURCES = ("NDX", "GLD", "USO")
STORE_PREFIX = "v2_emergency_manual_snapshot_"


def _validated(symbol, raw, name, *, source, download_rome=None):
    if symbol not in SOURCES:
        raise ValueError("Sottostante Cboe non riconosciuto.")
    read, expiries, *_ = _model(symbol)
    doc = read(raw)
    if not expiries(doc):
        raise ValueError(f"Fotografia {symbol}: nessuna scadenza valida.")
    return {
        "name": name, "content": bytes(raw), "source": source,
        "download_rome": download_rome,
        "timestamp": doc.get("timestamp"),
    }


def download_current_snapshot(symbol):
    """ONLY on explicit button press; reuse current approved V2 downloaders."""
    if symbol == "NDX":
        from data_sources import download_ndx
        raw = download_ndx()
    elif symbol == "GLD":
        from gld_cboe import download_gld
        raw = download_gld()
    elif symbol == "USO":
        from uso_cboe import download_uso
        raw = download_uso()
    else:
        raise ValueError("Sottostante Cboe non riconosciuto.")
    original = _validated(symbol, raw, symbol + "_CBOE_corrente.json",
                          source="Download manuale CBOE")
    if not raw.startswith(b"\x1f\x8b"):
        raw = gzip.compress(raw, compresslevel=6, mtime=0)
    return _validated(symbol, raw, symbol + "_CBOE_corrente.json.gz",
                      source="Download manuale CBOE",
                      download_rome=datetime.now(ROME).isoformat(timespec="seconds"))


def use_uploaded_snapshot(symbol, filename, raw):
    """Accept original ZIP/JSON/JSON.GZ; never assign a fake download clock."""
    original, inner_name = normalize_manual_upload(filename, raw, symbol)
    return _validated(symbol, original, inner_name, source="Importazione locale")


def activate_for_analysis(symbol, active):
    """One validated shared snapshot for both UI sections.

    The existing analysis references and archive read semantics stay intact.
    Manual acquisition explicitly overrides an archived selection.
    """
    if symbol not in SOURCES:
        raise ValueError("Sottostante Cboe non riconosciuto.")
    verified = _validated(symbol, active["content"], active["name"],
                           source=active["source"],
                           download_rome=active.get("download_rome"))
    from v2_storage_off import prefer_manual_source
    if symbol == "NDX":
        import streamlit as st
        state = st.session_state
        state["ndx_blob"] = verified["content"]
        state["ndx_name"] = verified["name"]
        state["ndx_source"] = (
            "Acquisizione diretta su richiesta"
            if verified["download_rome"] else "Importazione manuale")
        state["ndx_download_rome"] = (
            datetime.fromisoformat(verified["download_rome"]).strftime(
                "%d/%m/%Y %H:%M:%S Roma") if verified["download_rome"] else None)
        state["ndx_capture_rome_iso"] = verified["download_rome"]
        state.pop("v2_ndx_reference_current", None)
    else:
        from gld_cboe_view import _save_snapshot as save_gld
        from uso_cboe_view import _save_snapshot as save_uso
        save = save_gld if symbol == "GLD" else save_uso
        save(verified["content"], verified["name"],
             "Acquisizione diretta su richiesta" if verified["download_rome"]
             else "Importazione manuale")
        if not verified["download_rome"]:
            import streamlit as st
            # Loading a file today never proves its original Cboe capture clock.
            st.session_state[f"{symbol.lower()}_cboe_import_rome"] = None
    prefer_manual_source(symbol)
    return verified
