"""Read-only forensic audit for CBOE RUT/DJX option strike filtering.

Explains every transition from original OCC records to the existing conservative
paired Call/Put profile. Does not alter Gamma, select expiries, or invent values.
"""
from collections import defaultdict
import math

from v2_universal_cboe import _numeric, parse_contract, profile


def audit_strikes(doc, ticker, expiry, close, band, factor=1.0, basis=None):
    """Return diagnostic counts and strike rows for one actual expiry.

    The principal Pine and charts remain based exclusively on profile().
    One-sided candidates are audit-only and NOT promoted to a NET Gamma
    without an explicit, independently justified policy.
    """
    if ticker not in ("RUT", "DJX"):
        raise ValueError("Audit disponibile per RUT e DJX")
    if not math.isfinite(float(close)) or close <= 0 or not 0 < band <= 25:
        raise ValueError("Riferimento o fascia non validi")
    if basis is not None and not math.isfinite(float(basis)):
        raise ValueError("Basis non valido")
    if factor != (100.0 if ticker == "DJX" else 1.0):
        raise ValueError("Conversione indice/future incoerente")
    lo, hi = close * (1 - band / 100), close * (1 + band / 100)
    all_options = doc["data"]["options"]
    metrics = defaultdict(int)
    by_strike = defaultdict(lambda: {
        "sums": defaultdict(float), "seen_sides": set(),
        "valid_sides": set(), "invalid_sides": set(),
        "roots": set(), "contracts": 0
    })
    seen = set()

    for item in all_options:
        metrics["raw_records"] += 1
        if not isinstance(item, dict):
            metrics["invalid_structures"] += 1
            continue
        parsed = parse_contract(item, ticker)
        if parsed is None:
            metrics["other_or_invalid_occ"] += 1
            continue
        expiry_found, side, strike = parsed
        if expiry_found != expiry:
            metrics["other_expiries"] += 1
            continue
        metrics["selected_expiry_contracts"] += 1
        if not (lo - 1e-9 <= strike <= hi + 1e-9):
            metrics["outside_band_contracts"] += 1
            continue
        metrics["in_band_contracts"] += 1
        key = str(item.get("option", "")).strip().replace(" ", "").upper()
        if key in seen:
            metrics["duplicate_occ"] += 1
            continue
        seen.add(key)
        row = by_strike[strike]
        row["seen_sides"].add(side)
        row["contracts"] += 1
        root = key[:-(6 + 1 + 8)]
        row["roots"].add(root)
        vals = [_numeric(item.get(k)) for k in ("gamma", "open_interest", "volume")]
        if any(v is None for v in vals):
            metrics["incomplete_greeks_oi_volume"] += 1
            row["invalid_sides"].add(side)
            continue
        gamma, oi, volume = vals
        metrics["valid_contracts"] += 1
        if gamma > 0:
            metrics["positive_gamma_contracts"] += 1
        row["valid_sides"].add(side)
        row["sums"][side] += (oi + volume) * gamma

    rows = []
    for strike, item in sorted(by_strike.items()):
        call = item["sums"].get("C")
        put = item["sums"].get("P")
        paired = call is not None and put is not None
        if paired:
            status = "COPPIA_VALIDA"
        elif item["valid_sides"]:
            status = ("ALTRO_LATO_INCOMPLETO" if item["invalid_sides"] else
                      "UN_SOLO_LATO_PRESENTE")
        else:
            status = "NESSUN_LATO_VALIDO"
        metrics["strikes_in_band"] += 1
        metrics[status] += 1
        net = call - put if paired else None
        if paired and net == 0:
            metrics["net_zero"] += 1
        rows.append({
            "strike": strike,
            "future_level": strike * factor + basis if basis is not None else None,
            "call_gamma": call,
            "put_gamma": put,
            "net_gamma": net,
            "status": status,
            "contracts": item["contracts"],
            "roots": ", ".join(sorted(item["roots"])),
            "missing_call": call is None,
            "missing_put": put is None,
        })

    selected = profile(doc, ticker, expiry, close, band)
    paired_rows = [row for row in rows if row["status"] == "COPPIA_VALIDA"]
    if metrics["valid_contracts"] != selected["complete"] or (
        metrics["in_band_contracts"] - metrics["duplicate_occ"] != selected["matched"]
    ):
        raise ValueError("Audit non riconciliato con il motore Gamma originale")
    if selected["usable"]:
        canonical = {row["strike"]: row["net"] for row in selected["rows"]}
        diagnostic = {row["strike"]: row["net_gamma"] for row in paired_rows}
        if canonical != diagnostic:
            raise ValueError("Audit: livelli/Gamma non coincidono con l'output originale")
    elif selected["rows"]:
        raise ValueError("Profilo non utilizzabile ma livelli disegnati")

    metrics["matched_without_duplicates"] = selected["matched"]
    metrics["paired_before_profile_gate"] = len(paired_rows)
    metrics["pine_levels"] = len(selected["rows"])
    metrics["pine_nonzero_bars"] = sum(
        row["net"] != 0 for row in selected["rows"]
    )
    metrics["profile_usable"] = int(selected["usable"])
    metrics["coverage_pct"] = round(selected["coverage"] * 100, 2)
    metrics["low"] = lo
    metrics["high"] = hi
    metrics["expiry"] = expiry.isoformat()
    return {"metrics": dict(metrics), "rows": rows,
            "source_timestamp": doc.get("timestamp"),
            "filter": "coppia Call/Put obbligatoria; Gamma validi; fascia dal close"}
