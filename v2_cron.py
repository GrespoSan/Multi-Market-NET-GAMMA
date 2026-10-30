"""SPX-style V2 scheduled collections, WITHOUT any Supabase connection.

Three 07:30 Rome / 08:50 Chicago / 13:30 Chicago daily workflow slots.
Actual feeds require separately approved unattended API rights. Cboe's
delayed_quotes webpage endpoints are forbidden for this use and rejected.

Original chains are saved ONLY as Fernet-encrypted GitHub Actions artifacts;
the key is never published. If the source or encryption key is missing,
the runner records NON_CONFIGURATO without making a request.
"""
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

import requests

from v2_schedule import decision, INSTRUMENTS
from ndx_engine import unpack_snapshot, available_expirations, contract_parts
from gld_cboe import read_gld, expirations as expiries_gld
from uso_cboe import read_uso, expirations as expiries_uso

OUT = Path("v2_capture_output")
MAX_SOURCE_BYTES = 80 * 1024 * 1024


def safe_url(url):
    parts = urlsplit(str(url).strip())
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Feed autorizzato HTTPS non valido.")
    host = parts.hostname.lower()
    if (host == "cboe.com" or host.endswith(".cboe.com")) and (
        "delayed_quotes" in parts.path.lower()
    ):
        raise ValueError("Endpoint delayed_quotes Cboe escluso dai download automatici.")
    return str(url)


def fetch_authorized(url, token="", get=None):
    safe_url(url)
    caller = get or requests.get
    headers = {"Accept": "application/json, application/gzip"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with caller(url, headers=headers, stream=True, timeout=(8, 55),
                allow_redirects=True) as res:
        safe_url(res.url)
        res.raise_for_status()
        size = 0
        chunks = []
        for part in res.iter_content(chunk_size=1024*1024):
            if not part:
                continue
            size += len(part)
            if size > MAX_SOURCE_BYTES:
                raise ValueError("La catena supera il limite di dimensione.")
            chunks.append(part)
    if not chunks:
        raise ValueError("Risposta senza contratti.")
    return b"".join(chunks)


def validate_options(symbol, raw):
    if symbol == "NDX":
        doc = unpack_snapshot(raw)
        exp = available_expirations(doc)
        opts = [x for x in doc["data"]["options"]
                if isinstance(x, dict) and contract_parts(x.get("option"))]
    elif symbol == "GLD":
        doc = read_gld(raw)
        exp = expiries_gld(doc)
        opts = doc["data"]["options"]
    elif symbol == "USO":
        doc = read_uso(raw)
        exp = expiries_uso(doc)
        opts = doc["data"]["options"]
    else:
        raise ValueError("Mercato non riconosciuto.")
    complete = 0
    for x in opts:
        try:
            g = float(x["gamma"])
            oi = float(x["open_interest"])
            vol = float(x["volume"])
            if all(math.isfinite(v) and v >= 0 for v in (g, oi, vol)) and g > 0:
                complete += 1
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    if len(exp) < 1 or complete < 2:
        raise ValueError("Scadenze / greche / OI / volume insufficienti.")
    return {"contratti": len(opts), "contratti_gamma_completi": complete,
            "scadenze": len(exp), "timestamp_cboe_originale": doc.get("timestamp", "")}


def run_capture(now=None, env=None, output=None, downloader=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Clock UTC non valido.")
    env = env if env is not None else os.environ
    output = Path(output or OUT)
    output.mkdir(parents=True, exist_ok=True)
    manual = str(env.get("V2_MANUAL_RUN", "")).lower() == "true"
    requested = env.get("V2_REQUESTED_SLOT", "").strip() or None
    event_cron = env.get("V2_EVENT_CRON", "").strip() or None
    slot = decision(now, requested=requested, event_cron=event_cron, manual=manual)
    report = {"download_utc": now.astimezone(timezone.utc).isoformat(),
              "download_rome": slot["rome"].isoformat(),
              "download_chicago": slot["chicago"].isoformat(),
              "slot": slot["slot"], "reason": slot["reason"],
              "schedule_reference": slot["time_zone"],
              "requested_slot": slot.get("requested_slot", ""),
              "markets": {}}
    if not slot["run"]:
        report["status"] = "FUORI_FINESTRA"
    else:
        consent = str(env.get("V2_AUTHORIZED_FEED_CONFIRMED", "")).lower() == "true"
        secret = env.get("V2_ARCHIVE_FERNET_KEY", "")
        for market in INSTRUMENTS:
            url = env.get(f"V2_FEED_{market}_URL", "")
            status = {"status": "NON_CONFIGURATO"}
            if consent and secret and url:
                try:
                    # Do not import cryptography or read data until keys are set.
                    from cryptography.fernet import Fernet
                    encryptor = Fernet(secret.encode("ascii"))
                    raw = (downloader or fetch_authorized)(
                        url, env.get("V2_FEED_TOKEN", ""))
                    details = validate_options(market, raw)
                    if raw.startswith(b"\x1f\x8b"):
                        packed = raw
                    else:
                        packed = gzip.compress(raw, compresslevel=6, mtime=0)
                    encrypted = encryptor.encrypt(packed)
                    digest = hashlib.sha256(raw).hexdigest()
                    file = (f"{market}_{now:%Y%m%dT%H%M%SZ}_"
                            f"{slot['slot'].replace(':','')}_{digest[:12]}.json.gz.enc")
                    (output/file).write_bytes(encrypted)
                    status = {"status": "SCARICATO_CIFRATO", "file": file,
                              "sha256": digest, "source_meta": details}
                except Exception as exc:
                    # Never write exception text: it can contain private URL credentials.
                    status = {"status": "ERRORE", "error_type": type(exc).__name__}
            report["markets"][market] = status
        report["status"] = ("TUTTI_ARCHIVIATI" if all(
            x["status"] == "SCARICATO_CIFRATO" for x in report["markets"].values())
            else "PARZIALE_O_NON_CONFIGURATO")
    (output/"run_status.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"slot": report["slot"], "status": report["status"],
                      "markets": {key: val["status"] for key, val
                                  in report["markets"].items()}}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    run_capture()
