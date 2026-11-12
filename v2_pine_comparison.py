"""Three-profile time-comparison Pine: genuine 0DTE previous/current + Weekly current.

Only display and data selection differ from the single-snapshot exporters.
The original NDX or ETF Gamma, maturity, same-session basis/price mapping,
valid-ticker guard and manual common bar scale are preserved.
"""
from datetime import date
from math import isfinite
import re

from etf_future_pine import make_etf_future_pine
from pine_export import make_pine, _pine_array, _initial_manual_scale
from v2_pine_capture import pine_capture_clock
from v2_pine_session import compare_capture_pair, LABELS
from v2_pine_strike_budget import prepare_comparison_profiles
from v2_pine_header import normalize_indicator_header


def _safe_label(info):
    captured = pine_capture_clock(info["rome"])
    if not captured["verified"]:
        raise ValueError("Ora reale acquisizione non verificabile.")
    return captured["clock"]


def _same_expiry(previous, current):
    return (bool(previous.get("expiry")) and
            previous.get("expiry") == current.get("expiry"))


def make_pine_comparison_v2(symbol, previous, current, weekly,
                            reference_or_mapping, target, previous_info,
                            current_info, previous_slot, current_slot,
                            *, etf_previous_close=None,
                            export_details=None):
    """Make one 3-column comparison for a real earlier/later Cboe capture."""
    if symbol not in ("NDX", "GLD", "USO"):
        raise ValueError("Mercato non valido.")
    compare_capture_pair(previous_info, current_info, previous_slot, current_slot)
    if target != current_info["utc"].astimezone(
            __import__("zoneinfo").ZoneInfo("America/New_York")).date():
        raise ValueError("Data Pine diversa dalla seduta della fotografia.")
    if not _same_expiry(previous, current):
        raise ValueError("0DTE precedenti e correnti: scadenze differenti.")
    if not (current.get("rows") and previous.get("rows") and weekly.get("rows")):
        raise ValueError("Servono i profili originali 0DTE e Weekly reali.")
    if (symbol != "NDX" and
            not all(p.get("usable") for p in (previous, current, weekly))):
        raise ValueError("Gamma opzioni ETF non completo.")
    strike_key, gamma_key = (
        ("strike_index", "net_gamma") if symbol == "NDX" else ("strike", "net"))
    for p in (previous, current, weekly):
        rows = p["rows"]
        levels = [float(x[strike_key]) for x in rows]
        gamma = [float(x[gamma_key]) for x in rows]
        if (len(set(levels)) != len(levels) or
                any(not isfinite(x) or x <= 0 for x in levels) or
                any(not isfinite(x) for x in gamma)):
            raise ValueError("Profilo Cboe: strike duplicati o dati non finiti.")

    # TradingView max_lines_count=500: three complete NDX profiles may
    # exceed it. Keep every Cboe value intact; select only authentic rows
    # for the Pine drawing and report exactly what was omitted.
    original_profiles = (previous, current, weekly)
    previous, current, weekly = original_profiles
    (previous, current, weekly), display_info = prepare_comparison_profiles(
        symbol, previous, current, weekly)
    if export_details is not None:
        export_details.clear()
        if display_info is not None:
            old, shown = display_info["original"], display_info["rendered"]
            export_details["note"] = (
                "Limite TradingView: 0DTE " + LABELS[previous_slot] +
                f" {shown[0]}/{old[0]} strike; 0DTE " +
                LABELS[current_slot] + f" {shown[1]}/{old[1]} strike; " +
                "Weekly " + LABELS[current_slot] +
                f" {shown[2]}/{old[2]} strike. " +
                "Selezione per sola grafica fra strike Cboe reali, "
                "con priorità a Gamma estremi e livelli vicini al prezzo; "
                "nessun NET GAMMA ricalcolato.")
    display_comment = ""
    if display_info is not None:
        old, shown = display_info["original"], display_info["rendered"]
        display_comment = (
            "// ATTENZIONE - selezione grafica per limite 500 linee TradingView: "
            f"precedente {shown[0]}/{old[0]} strike reali; "
            f"corrente {shown[1]}/{old[1]}; Weekly {shown[2]}/{old[2]}. "
            "I restanti strike sono esclusi SOLO dal disegno Pine, "
            "non dai dati Gamma originali.\n"
        )

    main_title = f"0DTE {LABELS[previous_slot]} · Acq {_safe_label(previous_info)}"
    cur_title = f"0DTE {LABELS[current_slot]} · Acq {_safe_label(current_info)}"
    weekly_title = f"Weekly {LABELS[current_slot]} · Acq {_safe_label(current_info)}"
    label = f"{LABELS[previous_slot]} → {LABELS[current_slot]}"
    if symbol == "NDX":
        offset = float(reference_or_mapping)
        if not isfinite(offset):
            raise ValueError("Differenziale NQ-NDX non valido.")
        code = make_pine(
            {"0DTE":current, "Weekly":weekly}, offset, target, label,
            acquisition_time=current_info["rome"])
        previous_level_array = _pine_array(previous["rows"], "strike_index", offset)
    else:
        code = make_etf_future_pine(
            symbol, {"0DTE":current, "Weekly":weekly},
            etf_previous_close, target, label, None,
            acquisition_time=current_info["rome"], continuous=True)
        previous_level_array = _pine_array(previous["rows"], "strike")

    # Enforce both actual slot captures in code. Original Cboe timestamp has
    # unknown timezone, so only verified archive acquisition times are stated.
    insertion = (
        f"// Confronto reale stessa giornata NY: "
        f"{main_title} -> {cur_title}; {weekly_title}.\n"
        f"// Prezzi allineati su UNICO riferimento del Pine corrente; "
        f"Gamma originale di ogni fotografia invariato.\n"
    )
    code = code.replace("//@version=6\n", "//@version=6\n" + insertion + display_comment, 1)
    # Pine inputs appear in source declaration order. Place the previous
    # snapshot toggle immediately above the current snapshot toggle for
    # every comparison (NDX, GLD, USO; afternoon and evening).
    current_toggle = 'showCurrentOdte = input.bool(true, "Mostra 0DTE corrente")'
    if code.count(current_toggle) != 1:
        raise ValueError("Template Pine SPX non compatibile con confronto.")
    code = code.replace(
        current_toggle,
        'showPrevious = input.bool(false, "Mostra 0DTE precedente")\n'
        + current_toggle, 1)
    setting = 'showTitles = input.bool(true, "Mostra intestazioni")'
    if code.count(setting) != 1:
        raise ValueError("Template Pine SPX non compatibile con confronto.")
    code = code.replace(
        setting,
        setting
        + '\noffsetCompare = input.int(95, "Distanza 0DTE corrente dalle precedenti",'
        ' minval=20, maxval=300)', 1)

    anchor = "var array<float> odteLevels = " if symbol == "NDX" else "var array<float> mainStrikesETF = "
    if code.count(anchor) != 1:
        raise ValueError("Array Pine precedente non inseribile.")
    prev_data = (
        f"var array<float> prevLevels = {previous_level_array}\n"
        if symbol == "NDX" else
        f"var array<float> prevStrikesETF = {previous_level_array}\n"
    )
    prev_data += f'var array<float> prevGamma = {_pine_array(previous["rows"], gamma_key)}\n'
    code = code.replace(anchor, prev_data + anchor, 1)

    # Ensure starting manual scale accommodates all three independently
    # computed genuine Gamma profiles; never re-scale the Gamma themselves.
    pairs = [({"rows":[{"net_gamma":x[gamma_key]}
                       for x in p["rows"]]}, center)
             for p, center in ((previous, 100), (current, 195), (weekly, 295))]
    required, step = _initial_manual_scale(pairs)
    # Also allow opposing signs in adjacent columns without overlap.
    def extremes(p):
        values=[float(x[gamma_key]) for x in p["rows"]]
        return max(0.0, max(values)), max(0.0, -min(values))
    a, b, c=map(extremes, (previous, current, weekly))
    needed=max((a[0]+b[1]) / 80.0, (b[0]+c[1]) / 85.0, required)
    default = max(required, needed)
    # Decimal formatting mirrors current SPX visual input precision.
    def n(x):
        return f"{float(x):.8f}".rstrip("0").rstrip(".")
    expr=r'gammaPerCandle = input.float\([^\n]+'
    m=re.search(expr,code)
    if not m:
        raise ValueError("Scala manuale Pine assente.")
    new_scale = (
        f'gammaPerCandle = input.float({n(default)}, '
        f'"Scala MANUALE · Gamma/barra", minval=0.000001, step={n(step)}, '
        'tooltip="Scala comune ai 3 profili originali. NET GAMMA invariato.")'
    )
    code=code[:m.start()]+new_scale+code[m.end():]

    marker=("if barstate.islast and validTicker\n" if symbol == "NDX"
            else "if barstate.islast and validTicker and not na(ratioToDraw)\n")
    if code.count(marker) != 1:
        raise ValueError("Blocco disegno Pine non compatibile.")
    start=code.index(marker)
    # The SPX-style common renderProfile() and inputs remain unchanged.
    # Draw only real triple and verify chart's forward-bar bound per active
    # column, avoiding truncated bars. Price conversion applies to all ETF
    # strikes at exactly the same locked/dynamic ratio.
    make_levels = (
        "    array<float> prevMapped = prevLevels\n"
        if symbol == "NDX" else
        "    array<float> prevMapped = mapETF(prevStrikesETF, ratioToDraw)\n"
    )
    current_levels="odteLevels"
    weekly_levels="weeklyLevels"
    mapped_init = ("" if symbol == "NDX" else
                   "    array<float> odteLevels = mapETF(mainStrikesETF, ratioToDraw)\n"
                   "    array<float> weeklyLevels = mapETF(weeklyStrikesETF, ratioToDraw)\n"
                   "    array<float> topCallFutures = mapETF(topCallStrikesETF, ratioToDraw)\n"
                   "    array<float> topPutFutures = mapETF(topPutStrikesETF, ratioToDraw)\n")
    top3_calls = ("topCallOdteLevels", "topPutOdteLevels") if symbol == "NDX" else ("topCallFutures", "topPutFutures")
    code=code[:start]+f'''{marker}    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
{mapped_init}{make_levels}    float actualScale = gammaPerCandle
    int prevCenter = offsetOdte
    int currentCenter = offsetOdte + (showPrevious ? offsetCompare : 0)
    int weeklyCenter = currentCenter + offsetWeekly
    bool beyondLimit = (showPrevious and prevCenter >= 480) or (showCurrentOdte and currentCenter >= 480) or (showCurrentWeekly and weeklyCenter >= 480)
    float minimumSafe = math.max(showPrevious ? requiredScale(prevGamma, prevCenter) : 0.0, showCurrentOdte ? requiredScale({("odteValues" if symbol=="NDX" else "mainGammaETF")}, currentCenter) : 0.0)
    minimumSafe := math.max(minimumSafe, showCurrentWeekly ? requiredScale({("weeklyValues" if symbol=="NDX" else "weeklyGammaETF")}, weeklyCenter) : 0.0)
    if beyondLimit
        label warn = label.new(bar_index + 10, close, "Distanza profili oltre +500 barre: riduci gli offset.", xloc=xloc.bar_index, style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, warn)
    else if actualScale < minimumSafe * 0.999999
        label warn = label.new(bar_index + 10, close, "Scala manuale troppo piccola; aumenta Gamma/barra.", xloc=xloc.bar_index, style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, warn)
    else
        if showPrevious
            renderProfile(prevMapped, prevGamma, bar_index + prevCenter, "{main_title}", actualScale)
        if showCurrentOdte
            renderProfile({current_levels}, {("odteValues" if symbol=="NDX" else "mainGammaETF")}, bar_index + currentCenter, "{cur_title}", actualScale)
        if showCurrentWeekly
            renderProfile({weekly_levels}, {("weeklyValues" if symbol=="NDX" else "weeklyGammaETF")}, bar_index + weeklyCenter, "{weekly_title}", actualScale)
    // Proietta i Top 3 SOLO della fotografia 0DTE CORRENTE, mai precedente/Weekly.
    if showTop3Odte
        drawOdteTopProjections({top3_calls[0]}, {top3_calls[1]})
'''
    return normalize_indicator_header(code)
