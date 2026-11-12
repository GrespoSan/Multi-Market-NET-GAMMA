"""One-chart unified Pine engine for NDX RUT DJX GLD USO and SPX.

Original individual exporters remain untouched. For each supported futures root
the same original Cboe rows are embedded, and only that root is rendered.
No missing 0DTE is fabricated. ETF projections use matched, CLOSED 5-minute
ETF/futures bars on TradingView exactly as in etf_future_pine.py.
"""
from datetime import date, datetime
from math import isfinite
from zoneinfo import ZoneInfo

import streamlit as st

from v2_storage_off import load_pine_slot_captures
from v2_pine_session import slots_for_day
from v2_pine_capture import pine_capture_clock
from v2_visual_extension import expanded_display
from pine_export import _pine_array, _top_gamma_rows, _initial_manual_scale
from pine_spx_visual import SPX_RENDER_FUNCTIONS

NY = ZoneInfo("America/New_York")
MARKETS = ("NDX", "RUT", "DJX", "GLD", "USO", "SPX")
ROOTS = {
    "NDX": ("NQ", "MNQ"),
    "RUT": ("RTY", "M2K"),
    "DJX": ("YM", "MYM"),
    "GLD": ("GC", "MGC"),
    "USO": ("CL", "MCL"),
    "SPX": ("ES", "MES"),
}
FACTORS = {"NDX": 1.0, "RUT": 1.0, "DJX": 100.0, "GLD": 1.0, "USO": 1.0, "SPX": 1.0}
ETF = ("GLD", "USO")
FIELD = {"NDX": ("strike_index", "net_gamma")}
GAMMA_LIMIT = 460  # per ACTIVE instrument only, with room for guide lines


def _num(value):
    value = float(value)
    if not isfinite(value):
        raise ValueError("Numero strike/Gamma non finito.")
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def _from_capture(symbol, capture, day, band=3.0, extension=True):
    """Use existing market engines; preserve actual expiries and original Gamma."""
    if symbol == "NDX":
        from ndx_engine import (unpack_snapshot, available_expirations,
                                profile, weekly_target, close_from_payload)
        doc = unpack_snapshot(capture["raw"])
        expiries = available_expirations(doc)
        reference = close_from_payload(doc)
        main_date = day
        if main_date not in expiries:
            raise ValueError("NDX: 0DTE della seduta assente.")
        week = weekly_target(day, expiries)
        if week is None:
            raise ValueError("NDX: Weekly successiva assente.")
        make = lambda expiry, width: profile(doc, expiry, reference, band_pct=width)
        field_level, field_gamma = "strike_index", "net_gamma"
    elif symbol in ("RUT", "DJX"):
        from v2_universal_cboe import read_json, expiries as exp, profile
        doc = read_json(capture["raw"], symbol)
        expiries = exp(doc, symbol)
        reference = float(doc["data"]["prev_day_close"])
        main_date = day
        if main_date not in expiries:
            raise ValueError(f"{symbol}: vera 0DTE della seduta assente.")
        from v2_index_weekly import choose_weekly
        week, checked_weekly, _ = choose_weekly(
            doc, symbol, main_date, reference, band, expiries)
        if week is None or checked_weekly is None:
            raise ValueError(f"{symbol}: nessuna Weekly reale utilizzabile "
                             "nella fotografia 07:30.")
        make = lambda expiry, width: profile(doc, symbol, expiry, reference, width)
        field_level, field_gamma = "strike", "net"
    else:
        if symbol == "GLD":
            from gld_cboe import (read_gld, expirations, profile,
                                  next_weekly, close_previous, current_price)
            doc = read_gld(capture["raw"])
        else:
            from uso_cboe import (read_uso, expirations, profile,
                                  next_weekly, close_previous, current_price)
            doc = read_uso(capture["raw"])
        expiries = expirations(doc)
        reference = close_previous(doc)
        future = sorted(d for d in expiries if d >= day)
        if not future:
            raise ValueError(f"{symbol}: scadenze future non disponibili.")
        main_date = day if day in expiries else future[0]
        week = next_weekly(main_date, expiries)
        if week is None:
            raise ValueError(f"{symbol}: Weekly successiva assente.")
        make = lambda expiry, width: profile(doc, expiry, reference, band_pct=width)
        field_level, field_gamma = "strike", "net"
    if reference is None or not isfinite(float(reference)) or float(reference) <= 0:
        raise ValueError(f"{symbol}: close precedente non verificato.")
    main, weekly = make(main_date, band), make(week, band)
    if not main.get("rows") or not weekly.get("rows"):
        raise ValueError(f"{symbol}: profili Gamma senza strike.")
    if symbol in ETF and not (main.get("usable") and weekly.get("usable")):
        raise ValueError(f"{symbol}: copertura Gamma insufficiente.")
    if symbol in ("NDX", "GLD", "USO") and extension:
        spot = doc.get("data", {}).get("current_price")
        try:
            spot = float(spot)
        except (ValueError, TypeError):
            spot = float(reference)
        if symbol == "NDX":
            max_band = 20.0
        else:
            max_band = 10.0
        main, _ = expanded_display(main,
            lambda width: make(main_date, width), float(reference), spot, band,
            strike_field=field_level, gamma_field=field_gamma,
            upper_band_limit=max_band)
        weekly, _ = expanded_display(weekly,
            lambda width: make(week, width), float(reference), spot, band,
            strike_field=field_level, gamma_field=field_gamma,
            upper_band_limit=max_band)
    total = len(main["rows"]) + len(weekly["rows"])
    if total > GAMMA_LIMIT:
        raise ValueError(f"{symbol}: {total} strike superano il limite {GAMMA_LIMIT}; "
                         "riduci la fascia senza scartare strike.")
    for group in (main, weekly):
        for row in group["rows"]:
            lv, gn = float(row[field_level]), float(row[field_gamma])
            if not isfinite(lv) or not isfinite(gn) or lv <= 0:
                raise ValueError(f"{symbol}: strike o Gamma non valido.")
    # One single scale for both maturities, per market (never between markets).
    for_scale = [( {"rows": [{"net_gamma": x[field_gamma]} for x in group["rows"]]}, center)
                 for group, center in ((main, 100), (weekly, 200))]
    scale, _ = _initial_manual_scale(for_scale)
    is_0dte = main_date == day
    top_call = _top_gamma_rows(main["rows"], field_level, field_gamma, positive=True) if is_0dte else []
    top_put = _top_gamma_rows(main["rows"], field_level, field_gamma, positive=False) if is_0dte else []
    return {
        "main": main["rows"], "weekly": weekly["rows"],
        "call": top_call, "put": top_put,
        "field_level": field_level, "field_gamma": field_gamma,
        "scale": scale, "main_label": "0DTE" if is_0dte else "Principale (non 0DTE)",
        "main_expiry": main_date, "weekly_expiry": week,
        "captured": pine_capture_clock(capture["rome"]),
        "reference": float(reference), "source": symbol,
    }


def _session_basis(symbol, day):
    saved = st.session_state.get(f"mm_unified_basis_{symbol}")
    if (isinstance(saved, dict) and saved.get("analysis_day") == day.isoformat()
            and isfinite(float(saved.get("basis", float("nan"))))):
        return float(saved["basis"])
    if symbol == "NDX":
        result = st.session_state.get("ndx_basis_result")
    else:
        result = st.session_state.get(f"v2_primary_{symbol.lower()}_basis_result")
    if isinstance(result, dict) and isfinite(float(result.get("basis", float("nan")))):
        # A basis from another analyzed date must never be applied.
        target = st.session_state.get(
            "_ndx_basis_target" if symbol == "NDX"
            else f"v2_primary_{symbol.lower()}_basis_target")
        if target == day.isoformat():
            return float(result["basis"])
    return None


def _data_arrays(symbol, data):
    from pine_export import _pine_array
    fld, gamma = data["field_level"], data["field_gamma"]
    rows = (data["main"], data["weekly"], data["call"], data["put"])
    return [_pine_array(rows[0], fld), _pine_array(rows[0], gamma),
            _pine_array(rows[1], fld), _pine_array(rows[1], gamma),
            _pine_array(rows[2], fld), _pine_array(rows[3], fld)]


def build_unified_pine(day, market_data):
    """One self-contained Pine indicator. Missing markets never acquire fake data."""
    if not market_data or not isinstance(day, date):
        raise ValueError("Nessuna fotografia verificata per il Pine unico.")
    bad = set(market_data) - set(MARKETS)
    if bad:
        raise ValueError("Mercati sconosciuti: " + ", ".join(sorted(bad)))
    chunks = []
    for symbol in MARKETS:
        data = market_data.get(symbol)
        if data is None:
            chunks.extend(f"var array<float> {symbol}{name} = array.new_float()"
                          for name in ("Levels", "Gamma", "WeekLevels", "WeekGamma",
                                       "Calls", "Puts"))
            continue
        values = _data_arrays(symbol, data)
        for field, val in zip(("Levels", "Gamma", "WeekLevels", "WeekGamma",
                               "Calls", "Puts"), values):
            chunks.append(f"var array<float> {symbol}{field} = {val}")
    statements = "\n".join(chunks)
    def scalar(key, fallback, conversion=lambda a: a):
        items = []
        for ticker in MARKETS:
            item = market_data.get(ticker)
            value = fallback if item is None else conversion(item[key])
            items.append(f'    "{ticker}" => {value}')
        return "\n".join(items) + f"\n    => {fallback}"
    scales = scalar("scale", "1.0", _num)
    main_names = scalar("main_label", '"Non disponibile"', lambda x: '"'+x+'"')
    # Snapshot timestamps are metadata: never silently substitute current clock.
    stamps = scalar("captured", '"non verificata"',
        lambda x: '"'+str(x["stamp"]).replace('"', "'")+'"')
    labels = scalar("main_expiry", '"N/D"', lambda x: '"'+x.strftime("%d/%m/%Y")+'"')
    weekly_labels = scalar("weekly_expiry", '"N/D"', lambda x: '"'+x.strftime("%d/%m/%Y")+'"')
    bases = scalar("basis", "0.0", _num)
    output = '''//@version=6
indicator("Serafini Multi-Market · UNICO 07:30 · @DAY@", overlay=true, max_lines_count=500, max_labels_count=60)
// Cinque mercati, un unico motore grafico; dati originali CBOE.
// Un mercato senza fotografia/basis valido NON viene disegnato.
// ETF GLD/USO: Gamma ETF originale, livello future solo proiezione dinamica.
// Opzioni future native GC/CL NON sono disponibili da questi profili.
bool isES = syminfo.type == "futures" and (syminfo.root == "ES" or syminfo.root == "MES")
bool isNQ = syminfo.type == "futures" and (syminfo.root == "NQ" or syminfo.root == "MNQ")
bool isRTY = syminfo.type == "futures" and (syminfo.root == "RTY" or syminfo.root == "M2K")
bool isYM = syminfo.type == "futures" and (syminfo.root == "YM" or syminfo.root == "MYM")
bool isGC = syminfo.type == "futures" and (ticker.standard(syminfo.tickerid) == "COMEX:GC1!" or ticker.standard(syminfo.tickerid) == "COMEX_MINI:MGC1!")
bool isCL = syminfo.type == "futures" and (ticker.standard(syminfo.tickerid) == "NYMEX:CL1!" or ticker.standard(syminfo.tickerid) == "NYMEX:MCL1!")
string activeMarket = isES ? "SPX" : isNQ ? "NDX" : isRTY ? "RUT" : isYM ? "DJX" : isGC ? "GLD" : isCL ? "USO" : "NONE"
bool validTicker = activeMarket != "NONE"
bool isETF = isGC or isCL

// Manual scale multiplier is per chart. Each market has an independent
// suggested Gamma/bar value, shared between its two maturities.
scaleFactor = input.float(1.0, "Moltiplicatore scala Gamma (mercato corrente)", minval=0.01, step=0.1)
offsetOdte = input.int(100, "Distanza profilo principale", minval=45, maxval=250)
offsetWeekly = input.int(100, "Distanza Weekly dal principale", minval=20, maxval=600)
showCurrentOdte = input.bool(true, "Mostra profilo principale")
showCurrentWeekly = input.bool(true, "Mostra Weekly")
showTop3Odte = input.bool(false, "Proietta Top 3 Call / Put 0DTE")
showTitles = input.bool(true, "Mostra intestazioni")
positiveColor = input.color(color.rgb(0, 143, 76), "NET GAMMA positivo")
negativeColor = input.color(color.rgb(242, 54, 69), "NET GAMMA negativo")

@ARRAYS@

float suggestedScale = switch activeMarket
@SCALES@
string mainKind = switch activeMarket
@MAIN_NAMES@
string snapshotClock = switch activeMarket
@STAMPS@
string primaryExpiry = switch activeMarket
@MAIN_DATES@
string weeklyExpiry = switch activeMarket
@WEEK_DATES@
float basisIndex = switch activeMarket
@BASES@
float priceFactor = isYM ? 100.0 : 1.0
float actualScale = math.max(0.000001, suggestedScale * scaleFactor)

// Only CLOSED, TIME-MATCHED 5m bars may update the ETF/future ratio.
// On 1m/5m use the confirmed 5m feed. On 15m and higher use true lower
// timeframe intrabars, not a single barmerge sample of a 5m series.
// Both symbols are paired by actual 5m open timestamp; never invent a ratio.
string etfTicker = isGC ? "AMEX:GLD" : "AMEX:USO"
string futureTicker = ticker.standard(syminfo.tickerid)
var float lastDynamicRatio = na
var int lastMatchedTime = na
if isETF and timeframe.isintraday
    if timeframe.in_seconds() <= 300
        [etfLast, etfTime] = request.security(etfTicker, "5", [close[1], time[1]], gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_on, ignore_invalid_symbol=true)
        [futLast, futTime] = request.security(futureTicker, "5", [close[1], time[1]], gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_on, ignore_invalid_symbol=true)
        if not na(etfLast) and not na(futLast) and etfLast > 0 and futLast > 0 and not na(etfTime) and etfTime == futTime and (na(lastMatchedTime) or etfTime > lastMatchedTime)
            lastDynamicRatio := futLast / etfLast
            lastMatchedTime := etfTime
    else
        // [1] forces the prior confirmed 5m candle even when the last
        // intrabar of the current chart candle is still developing.
        [etfCloses, etfTimes] = request.security_lower_tf(etfTicker, "5", [close[1], time[1]], ignore_invalid_symbol=true)
        [futCloses, futTimes] = request.security_lower_tf(futureTicker, "5", [close[1], time[1]], ignore_invalid_symbol=true)
        int i = array.size(etfTimes) - 1
        int j = array.size(futTimes) - 1
        // Both arrays are time-ordered; walk backwards to the most recent
        // identical closed-bar timestamp without a cross-session proxy.
        while i >= 0 and j >= 0
            int et = array.get(etfTimes, i)
            int ft = array.get(futTimes, j)
            if na(et)
                i -= 1
            else if na(ft)
                j -= 1
            else if et > ft
                i -= 1
            else if ft > et
                j -= 1
            else
                float ep = array.get(etfCloses, i)
                float fp = array.get(futCloses, j)
                if not na(ep) and not na(fp) and ep > 0 and fp > 0 and (na(lastMatchedTime) or et > lastMatchedTime)
                    lastDynamicRatio := fp / ep
                    lastMatchedTime := et
                    break
                i -= 1
                j -= 1
float ratioToDraw = isETF ? lastDynamicRatio : 1.0
plot(isETF ? ratioToDraw : na, "Rapporto ETF/future sincronizzato", display=display.data_window)

@SPX_ARRAYS@

// The arrays for all six markets are immutable snapshots; only the
// active ticker's six arrays are used to draw. No cross-market rescaling.
array<float> mainLevels = switch activeMarket
    "NDX" => NDXLevels
    "RUT" => RUTLevels
    "DJX" => DJXLevels
    "GLD" => GLDLevels
    "USO" => USOLevels
    "SPX" => SPXLevels
    => array.new_float()
array<float> mainGamma = switch activeMarket
    "NDX" => NDXGamma
    "RUT" => RUTGamma
    "DJX" => DJXGamma
    "GLD" => GLDGamma
    "USO" => USOGamma
    "SPX" => SPXGamma
    => array.new_float()
array<float> weekLevels = switch activeMarket
    "NDX" => NDXWeekLevels
    "RUT" => RUTWeekLevels
    "DJX" => DJXWeekLevels
    "GLD" => GLDWeekLevels
    "USO" => USOWeekLevels
    "SPX" => SPXWeekLevels
    => array.new_float()
array<float> weekGamma = switch activeMarket
    "NDX" => NDXWeekGamma
    "RUT" => RUTWeekGamma
    "DJX" => DJXWeekGamma
    "GLD" => GLDWeekGamma
    "USO" => USOWeekGamma
    "SPX" => SPXWeekGamma
    => array.new_float()
array<float> callLevels = switch activeMarket
    "NDX" => NDXCalls
    "RUT" => RUTCalls
    "DJX" => DJXCalls
    "GLD" => GLDCalls
    "USO" => USOCalls
    "SPX" => SPXCalls
    => array.new_float()
array<float> putLevels = switch activeMarket
    "NDX" => NDXPuts
    "RUT" => RUTPuts
    "DJX" => DJXPuts
    "GLD" => GLDPuts
    "USO" => USOPuts
    "SPX" => SPXPuts
    => array.new_float()

var array<line> drawnLines = array.new_line()
var array<label> drawnLabels = array.new_label()

mapMarket(array<float> strikes, float factor, float shift) =>
    array<float> mapped = array.new_float()
    for val in strikes
        array.push(mapped, val * factor + shift)
    mapped

@RENDER@

if barstate.islast and validTicker
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
    bool haveData = array.size(mainLevels) > 0 and array.size(weekLevels) > 0
    bool ratioValid = not isETF or (timeframe.isintraday and not na(ratioToDraw))
    if not haveData
        label info = label.new(bar_index, close, "Fotografia/basis non disponibile per " + activeMarket, style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, info)
    else if not ratioValid
        label warn = label.new(bar_index, close, "ETF/future: nessuna coppia 5m chiusa e sincronizzata; nessun livello simulato.", style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, warn)
    else
        float factor = isETF ? ratioToDraw : priceFactor
        float shift = isETF ? 0.0 : basisIndex
        array<float> drawMain = mapMarket(mainLevels, factor, shift)
        array<float> drawWeek = mapMarket(weekLevels, factor, shift)
        array<float> drawCalls = mapMarket(callLevels, factor, shift)
        array<float> drawPuts = mapMarket(putLevels, factor, shift)
        int center = bar_index + offsetOdte
        int weekCenter = center + offsetWeekly
        float safe = math.max(
            showCurrentOdte ? requiredScale(mainGamma, offsetOdte) : 0.0,
            showCurrentWeekly ? requiredScale(weekGamma, offsetOdte + offsetWeekly) : 0.0)
        if offsetOdte >= 480 or (showCurrentWeekly and offsetOdte + offsetWeekly >= 480) or actualScale < safe * 0.999999
            label warning = label.new(bar_index + 10, close, "Scala/distanza non valida: aumenta scala o riduci offset.", style=label.style_label_left, color=color.orange, textcolor=color.black)
            array.push(drawnLabels, warning)
        else
            if showCurrentOdte
                renderProfile(drawMain, mainGamma, center, mainKind + " " + primaryExpiry + " · " + snapshotClock, actualScale)
            if showCurrentWeekly
                renderProfile(drawWeek, weekGamma, weekCenter, "Weekly " + weeklyExpiry + " · " + snapshotClock, actualScale)
            if showTop3Odte and mainKind == "0DTE"
                drawOdteTopProjections(drawCalls, drawPuts)
''';
    return (output.replace("@DAY@", day.isoformat())
        .replace("@ARRAYS@", statements).replace("@SCALES@", scales)
        .replace("@MAIN_NAMES@", main_names).replace("@STAMPS@", stamps)
        .replace("@MAIN_DATES@", labels).replace("@WEEK_DATES@", weekly_labels)
        .replace("@BASES@", bases)
        .replace("@SPX_ARRAYS@", "")
        .replace("@RENDER@", SPX_RENDER_FUNCTIONS))


def render():
    """Three unified downloads; individual market exporters stay unchanged."""
    from v2_unified_timed import render as render_unified_timed
    render_unified_timed()
