"""Read-only bridge to *official* Serafini SPX archive for unified ES/MES Pine.

Uses original SPX 25+25 core and original visual extension code (local
reference copies from SPX Dashboard). Never writes to SPX, never infers a
download time from the timezone-less Cboe timestamp, never synthesizes data.
Requires a *server-side*, Storage-read-authorized JWT in Streamlit Secrets:
SPX_SUPABASE_READ_KEY; SPX_SUPABASE_URL and SPX_SUPABASE_BUCKET optional.
Do NOT put privileged keys in public client code or GitHub commits.
"""
import json
import math
import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st

from pine_export import _top_gamma_rows, _initial_manual_scale
from v2_pine_capture import pine_capture_clock
from v2_spx_reference_gamma import read_snapshot, profile, visual_profile
from v2_spx_reference_basis import download_and_calculate

ROME = ZoneInfo("Europe/Rome")
# Verified owner project URL: public endpoint identifier, NEVER an API secret.
DEFAULT_SPX_URL = "https://rnpnibdxuqlmuqmcixsd.supabase.co"
SLOT_CRONS = {
    "0730": "30 7 * * 1-5",
    "1550": "50 15 * * 1-5",
    "1700": "0 17 * * 1-5",
    "2030": "30 20 * * 1-5",  # historical only
}
EXPECTED_CLOCK = {"0730": (7, 30), "1550": (15, 50),
                  "1700": (17, 0), "2030": (20, 30)}


class SPXArchiveReadOnly:
    def __init__(self, url, jwt, bucket="spx-snapshots"):
        if not url.startswith("https://") or not jwt or not bucket:
            raise ValueError("Configurazione lettura archivio SPX incompleta.")
        self.url = url.rstrip("/")
        self.jwt = jwt
        self.bucket = bucket

    def _req(self, method, path, data=None):
        headers = {"apikey": self.jwt, "Authorization": "Bearer " + self.jwt}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.url + "/storage/v1" + path, data=data,
                          method=method, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            raise ValueError(f"Archivio SPX: accesso HTTP {exc.code}. "
                             "Controlla credenziale e permessi Storage SELECT.") from None
        except URLError:
            raise ValueError("Archivio SPX non raggiungibile.") from None

    def list(self, prefix):
        entries = []
        offset = 0
        while True:
            body = json.dumps({
                "prefix": prefix, "limit": 100, "offset": offset,
                "sortBy": {"column": "name", "order": "asc"}
            }).encode("utf-8")
            raw = self._req("POST", "/object/list/" + quote(self.bucket, safe=""), body)
            page = json.loads(raw)
            if not isinstance(page, list):
                raise ValueError("Risposta archivio SPX non valida.")
            entries.extend(x for x in page if isinstance(x, dict) and x.get("name"))
            if len(page) < 100:
                return entries
            offset += len(page)
            if offset > 1000:
                raise ValueError("Troppi log SPX: controlla l'indice settimanale.")

    def download(self, path):
        return self._req("GET", "/object/authenticated/" +
                         quote(self.bucket, safe="") + "/" +
                         quote(path, safe="/"))


def _secrets():
    try:
        url = str(st.secrets.get("SPX_SUPABASE_URL", DEFAULT_SPX_URL)).strip()
        token = str(st.secrets.get("SPX_SUPABASE_READ_KEY", "")).strip()
        bucket = str(st.secrets.get("SPX_SUPABASE_BUCKET", "spx-snapshots")).strip()
    except Exception:
        url, token, bucket = DEFAULT_SPX_URL, "", "spx-snapshots"
    if not url or not token:
        raise ValueError("Accesso SPX non configurato: aggiungi nei Secrets "
                         "di Multi-Market SPX_SUPABASE_READ_KEY "
                         "(credenziale server-side autorizzata alla lettura Storage).")
    return url, token, bucket


def _week(day):
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _clock(raw, day):
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if when.tzinfo is None:
            return None
        when = when.astimezone(ROME)
        return when if when.date() == day else None
    except (ValueError, TypeError, OverflowError):
        return None


def _select_logs(logs, day, slots):
    """Exact SPX official schedule IDs, dated logs, original stored file only."""
    selected = {slot: [] for slot in slots}
    for log in logs:
        if (log.get("rome_date") != day.isoformat()
            or log.get("status") not in ("NUOVO", "INVARIATO")
            or not str(log.get("file") or "").startswith(_week(day) + "/snapshots/")):
            continue
        when = _clock(log.get("download_rome") or log.get("download_utc"), day)
        if when is None:
            continue
        for slot in slots:
            if log.get("scheduled_slot") == SLOT_CRONS.get(slot):
                # The original log is authoritative for time and schedule.
                selected[slot].append((when, log))
                break
    return {
        slot: sorted(items, key=lambda item: item[0])
        for slot, items in selected.items()
    }


@st.cache_data(ttl=150, show_spinner=False, max_entries=16)
def _official_captures(day, slots, url, jwt, bucket):
    store = SPXArchiveReadOnly(url, jwt, bucket)
    week = _week(day)
    names = store.list(f"{week}/logs/")
    # UTC filenames have the acquisition date; avoid reading other days'
    # logs whenever possible, without relying on names to classify slots.
    prefix = day.strftime("%Y%m%d")
    logs = []
    for entry in names:
        name = str(entry.get("name") or "")
        if not (name.startswith(prefix) and name.endswith(".json")):
            continue
        try:
            log = json.loads(store.download(f"{week}/logs/{name}"))
            if isinstance(log, dict):
                logs.append(log)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    matches = _select_logs(logs, day, slots)
    results = {}
    for slot, candidates in matches.items():
        for when, log in candidates:
            try:
                raw = store.download(log["file"])
                snap = read_snapshot(raw)
                if not snap.get("data", {}).get("options"):
                    continue
                results[slot] = {
                    "snapshot": snap,
                    # Exact original Cboe bytes already fetched for Serafini:
                    # the independent Edge 0DTE model must use SAME bytes.
                    "raw": raw,
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "download_rome": when.isoformat(timespec="seconds"),
                    "slot_rome": slot,
                    "log": log["file"],
                    "origin": "SPX UFFICIALE",
                }
                break
            except (ValueError, TypeError, KeyError, OSError):
                continue
    return results


def load_official_spx(day, slots):
    if not isinstance(day, date):
        raise ValueError("Data seduta SPX non valida.")
    url, token, bucket = _secrets()
    return _official_captures(day, tuple(slots), url, token, bucket)


@st.cache_data(ttl=3600, max_entries=14, show_spinner=False)
def _auto_basis(day):
    # EXACT original SPX method: previous cash session's synchronized 15m
    # Yahoo ES=F and ^GSPC bars, rounded half-up as displayed by SPX.
    result = download_and_calculate(day)
    raw = float(result["basis"])
    if not math.isfinite(raw):
        raise ValueError("Differenziale ES−SPX non finito.")
    rounded = float(Decimal(str(raw)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))
    return rounded, str(result["reference_date"]), str(result["source"])


def spx_basis(day):
    """Same automatic ES−SPX basis as Serafini SPX; no extra UI controls."""
    value, reference_date, source = _auto_basis(day)
    return value, f"automatico · {source} · seduta {reference_date}"


def _weekly_expiry(day):
    delta = 4 - day.weekday()
    return day + timedelta(days=delta if delta > 0 else 7)


@st.cache_data(ttl=120, max_entries=8, show_spinner=False)
def _cached_verified_official_feed(url, jwt, bucket):
    """One private read of already computed 100-strike GEX metadata."""
    return SPXArchiveReadOnly(url, jwt, bucket).download("mt4/official100.csv")


def _edge_levels_for_same_spx(archive, day, spot, basis):
    """Use Edge 0DTE on the exact chain, with SHA-bound official feed failover.

    If the pinned Edge engine is temporarily unavailable, the already
    published verified MT4 Edge output can supply the SAME 0DTE Wall/Flip.
    No stale date, slot or Cboe SHA is accepted.
    """
    raw = archive.get("raw")
    if not isinstance(raw, bytes) or not raw:
        return None
    digest = hashlib.sha256(raw).hexdigest()
    if digest != archive.get("source_sha256"):
        return None
    try:
        from edge_auto import result_from_snapshot
        edge = result_from_snapshot(raw, 0.0)
        if (edge.get("symbol") == "SPX"
                and edge.get("mode") == "0DTE"
                and edge.get("expiries") == [day.isoformat()]
                and edge.get("quality_sufficient") is True
                and edge.get("sha256") == digest
                and math.isclose(float(edge["spot_spx"]), float(spot),
                                 abs_tol=0.01)):
            levels = {}
            for key in ("call_wall_spx", "put_wall_spx", "gamma_flip_spx"):
                value = edge.get(key)
                try:
                    amount = float(value)
                    if math.isfinite(amount) and amount > 0:
                        levels[key] = amount
                except (ValueError, TypeError, OverflowError):
                    continue
            if levels:
                return levels
    except (ValueError, TypeError, KeyError, RuntimeError, OSError,
            OverflowError, ImportError, AttributeError):
        pass

    # Exact-source, independently verified fallback. A 17:00 feed must NEVER
    # supply levels to the 07:30 or 15:50 export.
    try:
        from gex_official_csv import verified_official_gex_csv
        url, token, bucket = _secrets()
        content = _cached_verified_official_feed(url, token, bucket)
        timestamp = archive["snapshot"]["timestamp"]
        clock = datetime.fromisoformat(archive["download_rome"]).strftime("%H:%M:%S")
        return verified_official_gex_csv(
            content, raw, day, archive["slot_rome"], timestamp, clock)
    except (ValueError, TypeError, KeyError, RuntimeError, OSError,
            OverflowError, ImportError, AttributeError):
        return None

def spx_record(archive, day, basis, *, extension=True):
    """Exact original SPX calculations, original strikes, frozen ES basis."""
    snap = archive["snapshot"]
    reference = float(snap["data"].get("prev_day_close") or 0)
    if not (math.isfinite(reference) and reference > 0):
        raise ValueError("SPX: close precedente originale assente.")
    expiration = _weekly_expiry(day)
    profiles = []
    for expiry in (day, expiration):
        core = profile(snap, expiry, reference)
        if len(core.get("rows") or []) != 50:
            raise ValueError("SPX: profilo 25+25 non disponibile.")
        result = (
            visual_profile(
                snap, core, expiry, reference,
                snap["data"].get("current_price"))
            if extension else core
        )
        rows = result["rows"]
        if len(set(float(r["strike_spx"]) for r in rows)) != len(rows):
            raise ValueError("SPX: strike duplicati.")
        if any(not math.isfinite(float(r["net_gamma"])) for r in rows):
            raise ValueError("SPX: NET GAMMA non finito.")
        profiles.append(rows)
    main, weekly = profiles
    from v2_unified_pine import GAMMA_LIMIT
    if len(main) + len(weekly) > GAMMA_LIMIT:
        raise ValueError("SPX: troppi strike per il Pine unico.")
    scale, _ = _initial_manual_scale([
        ({"rows": [{"net_gamma": r["net_gamma"]} for r in main]}, 100),
        ({"rows": [{"net_gamma": r["net_gamma"]} for r in weekly]}, 200),
    ])
    return {
        "main": main, "weekly": weekly,
        "call": _top_gamma_rows(main, "strike_spx", "net_gamma", positive=True),
        "put": _top_gamma_rows(main, "strike_spx", "net_gamma", positive=False),
        "field_level": "strike_spx", "field_gamma": "net_gamma",
        "scale": scale,
        "main_label": "0DTE", "main_expiry": day,
        "weekly_expiry": expiration,
        "captured": pine_capture_clock(archive["download_rome"]),
        "reference": reference, "basis": float(basis), "source": "SPX",
        # GEX Wall/Flip are NOT Serafini Top 3. Only valid official 0DTE Edge.
        "gex_levels_spx": _edge_levels_for_same_spx(
            archive, day, snap["data"].get("current_price"), basis),
    }
