"""Unpack ONE original Cboe JSON or JSON.GZ from a manually uploaded ZIP.

No extraction on disk, no archive or remote access. The market-specific
existing parser remains the final source and symbol validator.
"""
from __future__ import annotations

import io
from pathlib import PurePosixPath
import zipfile

MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 80 * 1024 * 1024
SYMBOLS = ("NDX", "GLD", "USO")


def normalize_manual_upload(filename: str, raw: bytes, symbol: str):
    """Return (Cboe file bytes, original inner basename) for one market.

    ZIP can carry unrelated notes. Reject archives with multiple candidate
    chains for one ticker rather than silently choosing a stale snapshot.
    No gzip decompression or mutation of the genuine Cboe file.
    """
    if symbol not in SYMBOLS:
        raise ValueError("Sottostante Cboe non supportato.")
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("File caricato vuoto.")
    name = str(filename or "").strip()
    if not name:
        raise ValueError("Nome del file assente.")
    if not name.lower().endswith(".zip"):
        if not name.lower().endswith((".json", ".json.gz", ".gz")):
            raise ValueError("Sono consentiti JSON, JSON.GZ e ZIP.")
        return raw, name
    if len(raw) > MAX_ZIP_BYTES:
        raise ValueError("Archivio ZIP troppo grande.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            candidates = []
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if (info.is_dir() or path.is_absolute() or
                        ".." in path.parts or "\\" in info.filename):
                    if not info.is_dir():
                        raise ValueError("Percorso ZIP non sicuro.")
                    continue
                leaf = path.name.lower()
                if not leaf.endswith((".json", ".json.gz")):
                    continue
                # Only original chains of the selected underlying, never
                # a combined report or a file for another instrument.
                identifiers = (symbol.lower() + ".", symbol.lower() + "_",
                               "_" + symbol.lower() + ".", "_" + symbol.lower() + "_")
                if not leaf.startswith(identifiers):
                    continue
                if info.file_size <= 0 or info.file_size > MAX_MEMBER_BYTES:
                    raise ValueError("Fotografia Cboe ZIP vuota o troppo grande.")
                candidates.append(info)
            if len(candidates) != 1:
                raise ValueError(f"ZIP: serve un'unica fotografia originale {symbol} "
                                 f"(trovate {len(candidates)}).")
            member = candidates[0]
            with archive.open(member, "r") as inp:
                body = inp.read(MAX_MEMBER_BYTES + 1)
            if len(body) > MAX_MEMBER_BYTES:
                raise ValueError("Fotografia estratta oltre limite.")
            return body, PurePosixPath(member.filename).name
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise ValueError("ZIP Cboe non leggibile o danneggiato.") from exc
