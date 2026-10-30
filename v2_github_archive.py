"""Read encrypted V2 GitHub Actions artifacts without touching Supabase.

GitHub token is read only from private Streamlit secrets and used server-side.
Only encrypted .json.gz.enc is extracted from the artifact ZIP.
"""
import io
import re
import zipfile

import requests

API = "https://api.github.com/repos/GrespoSan/Multi-Market-NET-GAMMA"
MAX_ARCHIVE = 220 * 1024 * 1024
MAX_ENCRYPTED_FILE = 110 * 1024 * 1024


def _get(url, token, session=None):
    if not token:
        raise ValueError("V2_GITHUB_TOKEN mancante.")
    getter = session or requests
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    response = getter.get(url, headers=headers, timeout=(8, 65),
                          stream=True, allow_redirects=True)
    try:
        response.raise_for_status()
        size = 0
        chunks = []
        for block in response.iter_content(1024 * 1024):
            if block:
                size += len(block)
                if size > MAX_ARCHIVE:
                    raise ValueError("Archivio GitHub troppo grande.")
                chunks.append(block)
        return b"".join(chunks)
    finally:
        response.close()


def list_v2_artifacts(token, session=None):
    raw = _get(API + "/actions/artifacts?per_page=100", token, session)
    import json
    result = json.loads(raw)
    found = []
    for item in result.get("artifacts", []):
        title = str(item.get("name", ""))
        url = str(item.get("archive_download_url", ""))
        if (not item.get("expired") and title.startswith("v2-multi-market-")
                and re.fullmatch(r"v2-multi-market-\d+", title)
                and re.fullmatch(
                    re.escape(API) + r"/actions/artifacts/\d+/zip", url)):
            found.append({"name": title, "url": url,
                          "created_at": item.get("created_at", "")})
    return sorted(found, key=lambda x: x["created_at"], reverse=True)


def extract_encrypted_artifact(zip_bytes, symbol):
    if symbol not in ("NDX", "GLD", "USO"):
        raise ValueError("Mercato sconosciuto.")
    matches = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            name = info.filename
            basename = name.rsplit("/", 1)[-1]
            if (not info.is_dir()
                    and re.fullmatch(
                        rf"{symbol}_\d{{8}}T\d{{6}}Z_(?:0730|1550|2030|manuale)_[a-f0-9]{{12}}\.json\.gz\.enc",
                        basename)
                    and info.file_size <= MAX_ENCRYPTED_FILE):
                matches.append((name, info))
        if not matches:
            raise ValueError("Questo rilevamento non contiene una fotografia cifrata "
                             f"valida per {symbol}.")
        selected, info = max(matches, key=lambda item: item[0])
        contents = zf.read(info)
        if len(contents) > MAX_ENCRYPTED_FILE:
            raise ValueError("Il file cifrato supera il limite consentito.")
        return contents, selected.rsplit("/", 1)[-1]


def decrypt_encrypted(data, key):
    from cryptography.fernet import Fernet, InvalidToken
    if len(data) > MAX_ENCRYPTED_FILE:
        raise ValueError("File cifrato troppo grande.")
    try:
        compressed = Fernet(key.encode("ascii")).decrypt(data)
    except (ValueError, InvalidToken, TypeError) as exc:
        raise ValueError("Chiave V2 non valida o archivio non autentico.") from exc
    if not compressed.startswith(b"\x1f\x8b"):
        raise ValueError("Il documento decifrato non è JSON gzip.")
    return compressed


def fetch_artifact_snapshot(url, symbol, token, key, session=None):
    if not re.fullmatch(re.escape(API) + r"/actions/artifacts/\d+/zip", url):
        raise ValueError("URL archivio non appartenente al repository V2.")
    archive = _get(url, token, session)
    encrypted, filename = extract_encrypted_artifact(archive, symbol)
    return decrypt_encrypted(encrypted, key), filename.removesuffix(".enc")
