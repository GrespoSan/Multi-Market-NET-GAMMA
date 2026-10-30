"""V2 three-slot unattended Cboe original option-chain acquisitions.

User requested direct public Cboe CDN downloads notwithstanding provider
automated-access restrictions. This runner does not bypass rate limits,
authentication, access denials, CAPTCHAs or other technical controls.
One bounded HTTPS GET per market per scheduled run; on HTTP 401/403/429
the market is marked failed with no retry or workaround.

Three schedules: 07:30 Rome / 08:50 and 13:30 Chicago. Each successfully
validated original JSON is gzip-compressed and Fernet-encrypted inside
GitHub Actions artifacts, never written as plaintext or to Supabase.
V2_ARCHIVE_FERNET_KEY is required for a durable archived capture.
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
CBOE_PUBLIC_URLS = {
    "NDX": "https://cdn.cboe.com/api/global/delayed_quotes/options/_NDX.json",
    "GLD": "https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json",
    "USO": "https://cdn.cboe.com/api/global/delayed_quotes/options/USO.json",
}


def safe_url(url):
    parts = urlsplit(str(url).strip())
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Sorgente HTTPS non valida.")
    if parts.hostname.lower().endswith(".cboe.com"):
        # Only three known, unmodified public CDN paths are eligible;
        # do not use alternate hosts/paths to evade provider restrictions.
        if url not in CBOE_PUBLIC_URLS.values():
            raise ValueError("Endpoint CDN Cboe diverso dai tre JSON previsti.")
    return str(url)


def fetch_authorized(url, token="", get=None):
    safe_url(url)
    caller = get or requests.get
    headers = {
        "User-Agent": "MultiMarketNetGammaV2/1.0 (single scheduled snapshot)",
        "Accept": "application/json, application/gzip",
    }
    if token and url not in CBOE_PUBLIC_URLS.values():
        headers["Authorization"] = "Bearer " + token
    with caller(url, headers=headers, stream=True, timeout=(8, 55),
                allow_redirects=True) as res:
        safe_url(res.url)
        if res.status_code in (401, 403, 429):
            raise RuntimeError(f"HTTP {res.status_code}: provider accesso negato/limitato.")
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
            override_url = str(env.get(f"V2_FEED_{market}_URL", "")).strip()
            # Public Cboe paths are used without any additional endpoint secret.
            # A licensed custom feed is an optional explicit override.
            url = override_url or CBOE_PUBLIC_URLS[market]
            is_public_cboe = url == CBOE_PUBLIC_URLS[market]
            status = {"status": "NON_CONFIGURATO", "source":
                      "CBOE_PUBLIC_CDN" if is_public_cboe else "CUSTOM_FEED"}
            if secret and (is_public_cboe or consent):
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
                              "source": "CBOE_PUBLIC_CDN" if is_public_cboe
                                        else "CUSTOM_FEED",
                              "sha256": digest, "source_meta": details}
                except Exception as exc:
                    # Never write exception text: it can contain private URL credentials.
                    status = {"status": "ERRORE", "error_type": type(exc).__name__,
                              "source": "CBOE_PUBLIC_CDN" if is_public_cboe
                                        else "CUSTOM_FEED"}
            elif not secret:
                status["reason"] = "V2_ARCHIVE_FERNET_KEY non configurata"
            elif not is_public_cboe and not consent:
                status["reason"] = "Feed esterno: consenso/licenza non confermati"
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
