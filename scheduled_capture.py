"""Multi-Market collection runner for licensed/authorized option-chain feeds.

Cboe delayed_quotes is NOT an authorized unattended feed; URLs pointing to
those endpoints are rejected rather than scraped or circumvented.
Per-run GitHub Actions artifacts always contain a status report. A private,
separate Supabase bucket is optional for persistent Streamlit archives.
"""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from scheduled_slots import INSTRUMENTS, schedule_decision, week_key
from multimarket_archive import read_archive_config
from ndx_engine import unpack_snapshot, available_expirations, contract_parts
from gld_cboe import read_gld, expirations as gld_expirations
from uso_cboe import read_uso, expirations as uso_expirations

OUT = Path("capture_output")
MAX_BYTES = {"NDX": 100 * 1024 * 1024,
             "GLD": 50 * 1024 * 1024,
             "USO": 50 * 1024 * 1024}


def validate_authorized_url(url):
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("L'origine programmata deve essere un endpoint HTTPS valido.")
    host = parsed.hostname.lower()
    if (host == "cboe.com" or host.endswith(".cboe.com")) and (
            "/delayed_quotes/" in parsed.path.lower()
            or "delayed_quotes" in parsed.path.lower()):
        raise ValueError("Il sito Cboe delayed_quotes vieta i download programmati: "
                         "configura una fonte autorizzata diversa.")
    return url


def read_authorized_source(symbol, url, token="", get=None):
    """One request, bounded response, explicit failed status; no fallback scraping."""
    validate_authorized_url(url)
    get = get or requests.get
    headers = {"Accept": "application/json, application/gzip"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    max_bytes = MAX_BYTES[symbol]
    with get(url, headers=headers, timeout=(8, 55), stream=True,
             allow_redirects=True) as response:
        validate_authorized_url(response.url)  # also block redirects to forbidden host
        if response.status_code in (401, 403, 429):
            raise RuntimeError(f"Fonte autorizzata HTTP {response.status_code}; "
                               "controllare la licenza/API.")
        response.raise_for_status()
        parts, size = [], 0
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"{symbol}: limite dimensionale superato.")
            parts.append(chunk)
    if not parts:
        raise ValueError(f"{symbol}: risposta vuota.")
    return b"".join(parts)


def validate_chain(symbol, payload):
    if symbol == "NDX":
        doc = unpack_snapshot(payload)
        expiries = available_expirations(doc)
        options = [x for x in doc["data"]["options"]
                   if isinstance(x, dict) and contract_parts(x.get("option"))]
    elif symbol == "GLD":
        doc = read_gld(payload)
        expiries = gld_expirations(doc)
        options = doc["data"]["options"]
    elif symbol == "USO":
        doc = read_uso(payload)
        expiries = uso_expirations(doc)
        options = doc["data"]["options"]
    else:
        raise ValueError("Mercato non supportato.")
    if not expiries or len(options) < 2:
        raise ValueError("Catena senza scadenze/contratti riconoscibili.")
    complete, nonzero = 0, 0
    for opt in options:
        try:
            gamma, oi, vol = (float(opt[k]) for k in
                              ("gamma", "open_interest", "volume"))
            if all(math.isfinite(x) and x >= 0 for x in (gamma, oi, vol)):
                complete += 1
                if gamma > 0:
                    nonzero += 1
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
    if complete < 2 or nonzero < 1:
        raise ValueError("Gamma/OI/Volume incompleti: file NON archiviabile come valido.")
    return {"timestamp_original": doc.get("timestamp") or "",
            "contratti": len(options), "completi": complete, "gamma_positivi": nonzero,
            "scadenze": len(expiries), "fonte_timestamp_timezone": "non_specificata"}


def gzip_original(raw):
    if raw.startswith(b"\x1f\x8b"):
        return raw
    return gzip.compress(raw, compresslevel=6, mtime=0)


def capture_one(symbol, now, slot, source_url, authorized=False, token="",
                archive=None, get=None, output=OUT):
    local = now.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
    name = f"{local:%Y%m%d}_{slot.replace(':','')}_{now:%H%M%S}"
    root = f"snapshots/{symbol}/{week_key(local)}"
    logs_root = f"logs/{symbol}/{week_key(local)}"
    log = {"market": symbol, "rome_date": local.date().isoformat(),
           "slot": slot, "download_utc": now.isoformat(timespec="seconds"),
           "download_rome": local.isoformat(timespec="seconds"),
           "status": "NON_CONFIGURATO"}
    file_key = ""
    compressed = None
    try:
        if not authorized or not source_url:
            log["note"] = ("Download programmato sospeso: serve un URL di feed "
                           "autorizzato e MM_AUTHORIZED_FEED_CONFIRMED=true. "
                           "NON usare delayed_quotes Cboe.")
        else:
            raw = read_authorized_source(symbol, source_url, token=token, get=get)
            quality = validate_chain(symbol, raw)
            digest = hashlib.sha256(raw).hexdigest()
            file_key = f"{root}/{name}_{digest[:12]}.json.gz"
            compressed = gzip_original(raw)
            log.update(status="SCARICATO", data=quality, sha256_original=digest,
                       "file": file_key, "size_compressed": len(compressed))
            local_path = output / file_key
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(compressed)
            if archive:
                archive.upload(file_key, compressed, "application/gzip")
                log["storage"] = "Supabase privato + artifact GitHub"
            else:
                log["storage"] = "Artifact GitHub Actions"
    except Exception as exc:
        log["status"] = "ERRORE"
        log["note"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        if file_key and compressed and not archive:
            log["note"] += " (file solo in artifact GitHub)"
    log_path = f"{logs_root}/{name}.json"
    data = json.dumps(log, ensure_ascii=False, indent=2).encode("utf-8")
    local_log = output / log_path
    local_log.parent.mkdir(parents=True, exist_ok=True)
    local_log.write_bytes(data)
    if archive:
        try:
            archive.upload(log_path, data, "application/json")
        except Exception as exc:
            log["archive_log_error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
            local_log.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return log


def main(now=None, env=None):
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    manual = str(env.get("MM_MANUAL_RUN", "")).lower() == "true"
    requested = env.get("MM_SLOT", "").strip() or None
    decision = schedule_decision(now, requested=requested, manual=manual)
    local = now.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
    OUT.mkdir(parents=True, exist_ok=True)
    if not decision["run"]:
        result = {"status": "SALTATO", "reason": decision["reason"],
                  "requested_slot": requested, "rome": local.isoformat()}
        (OUT / "run_status.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    archive = read_archive_config(env)
    authorized = str(env.get("MM_AUTHORIZED_FEED_CONFIRMED", "")).lower() == "true"
    logs = []
    for symbol in INSTRUMENTS:
        key = "MM_FEED_" + symbol + "_URL"
        logs.append(capture_one(symbol, now, decision["slot"], env.get(key, ""),
                                authorized=authorized, token=env.get("MM_FEED_TOKEN", ""),
                                archive=archive))
    summary = {"rome": local.isoformat(), "slot": decision["slot"],
               "status": "COMPLETATO" if all(x["status"] == "SCARICATO" for x in logs)
               else "PARZIALE_O_NON_CONFIGURATO", "markets": logs}
    (OUT / "run_status.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({"slot": summary["slot"], "status": summary["status"],
                      "markets": {x["market"]: x["status"] for x in logs}},
                     ensure_ascii=False))
    return 1 if any(x["status"] == "ERRORE" for x in logs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
