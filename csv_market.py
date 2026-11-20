import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from cboe_csv_import import csv_to_snapshot
from mercati.v2_market_engine import render_selected_market
from mercati.v2_universal_cboe import render_equity

MARKETS = {"SP500": "SPX", "Nasdaq": "NDX", "Russell": "RUT", "Dow Jones": "DJX",
           "Gold": "GLD", "Petrolio": "USO", "Azioni": None}
ENGINES = {"NDX": "NASDAQ", "RUT": "RUSSELL", "DJX": "DOW", "GLD": "GOLD", "USO": "WTI"}

@st.cache_data(max_entries=8, show_spinner=False)
def parse_csv(payload, ticker):
    return csv_to_snapshot(payload, ticker)

def render_market(upload, symbol, equity):
    doc = parse_csv(upload.getvalue(), symbol)
    stamp = datetime.fromisoformat(doc["timestamp"]).replace(tzinfo=timezone.utc)
    day = stamp.astimezone(ZoneInfo("America/New_York")).date()
    rome = stamp.astimezone(ZoneInfo("Europe/Rome")).isoformat()
    raw = json.dumps(doc).encode()
    state = st.session_state
    digest = doc["_import_provenance"]["original_csv_sha256"]
    if state.get("chain_identity") != (symbol, digest):
        for key in list(state):
            if key.startswith(("ndx_", "gld_", "uso_", "universal_", "v2_primary_", "v2_ndx_")):
                del state[key]
        state["chain_identity"] = (symbol, digest)
    if equity:
        render_equity(doc, symbol, day)
        return day
    state[f"v2_archive_capture_nyday_{symbol}"] = day
    if symbol == "NDX":
        state.update(ndx_blob=raw, ndx_name=upload.name, ndx_download_rome=rome,
                     ndx_source="CSV Cboe", ndx_capture_rome_iso=rome)
    elif symbol in ("RUT", "DJX"):
        state[f"v2_primary_{symbol.lower()}_active"] = {"raw": raw, "origin": upload.name, "stamp": rome}
    else:
        prefix = symbol.lower() + "_cboe_"
        for key, value in {"raw": raw, "source": "CSV Cboe", "import_rome": rome,
                           "file": upload.name, "sha256": digest}.items():
            state[prefix + key] = value
    render_selected_market(ENGINES[symbol])
    return day
