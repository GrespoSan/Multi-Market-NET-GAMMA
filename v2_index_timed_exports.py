"""Russell and Dow: verified 07:30 / 15:50 / 17:00 Pine exports; 20:30 historical.

The historic CBOE snapshots remain immutable. 0DTE comparison shows the
previous and current real photographs plus current Weekly, with one common
Gamma/bar scale and the same frozen RTY-RUT or YM-DJIA basis for all levels.
"""
from datetime import datetime
from time import monotonic
from math import isfinite

import streamlit as st

from v2_storage_off import load_pine_slot_captures
from v2_pine_session import LABELS, compare_capture_pair, slots_for_day
from v2_pine_capture import pine_capture_clock
from v2_universal_cboe import read_json, expiries, profile, _pine
from pine_export import _pine_array, _initial_manual_scale
from pine_news_overlay import append_news
from v2_index_basis import CONFIG


def _snapshot_profiles(ticker, captures, day, reference, band):
    result, problems = {}, {}
    for slot, capture in captures.items():
        try:
            doc = read_json(capture["raw"], ticker)
            expiry_dates = expiries(doc, ticker)
            if day not in expiry_dates:
                raise ValueError("0DTE reale non presente nella fotografia.")
            from v2_index_weekly import choose_weekly
            weekly_date, weekly, details = choose_weekly(
                doc, ticker, day, reference, band, expiry_dates)
            if weekly is None:
                if not details:
                    raise ValueError("Weekly successiva non presente nella fotografia.")
                raise ValueError("Weekly di venerdì presenti, ma nessuna "
                                 "catena Gamma Call/Put utilizzabile.")
            odte = profile(doc, ticker, day, reference, band)
            if not odte.get("usable"):
                raise ValueError("Gamma 0DTE insufficienti; Weekly verificata "
                                 "ma confronto 0DTE non disponibile.")
            result[slot] = {"0DTE": odte, "Weekly": weekly, "capture": capture}
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            problems[slot] = str(exc)[:200]
    return result, problems


def _comparison_pine(ticker, prev, cur, weekly, basis, prev_info, cur_info,
                     prev_slot, current_slot):
    compare_capture_pair(prev_info, cur_info, prev_slot, current_slot)
    if prev["expiry"] != cur["expiry"]:
        raise ValueError("Le due 0DTE non hanno la stessa scadenza.")
    if not isfinite(float(basis)):
        raise ValueError("Differenziale indice/future non valido.")
    groups = (prev, cur, weekly)
    for g in groups:
        if not g["rows"]:
            raise ValueError("Profili Gamma reali insufficienti.")
    # Do not pretend to represent all strikes when the TV renderer is full.
    total = sum(len(g["rows"]) for g in groups)
    if total > 470:
        raise ValueError(
            f"Confronto con {total} strike supera il budget grafico Pine (470). "
            "Riduci la fascia strike: nessun livello viene escluso silenziosamente.")
    code = _pine(ticker, {"0DTE": cur, "Weekly": weekly},
                 future_mode=True, future_basis=basis)
    from v2_pine_session import LABELS
    previous_toggle = 'showCurrentOdte = input.bool(true, "Mostra 0DTE corrente")'
    if code.count(previous_toggle) != 1:
        raise ValueError("Template Pine 0DTE non compatibile.")
    code = code.replace(
        previous_toggle,
        'showPrevious = input.bool(false, "Mostra 0DTE precedente")\n'
        + previous_toggle, 1)
    anchor = 'showTitles = input.bool(true, "Mostra intestazioni")'
    if code.count(anchor) != 1:
        raise ValueError("Impostazione intestazioni Pine non trovata.")
    code = code.replace(
        anchor,
        anchor + '\noffsetCompare = input.int(95, "Distanza 0DTE corrente dalle precedenti", minval=20, maxval=200)', 1)
    array_anchor = "var array<float> mainLevels = "
    if code.count(array_anchor) != 1:
        raise ValueError("Array principale Pine non trovato.")
    arrays = (
        f'var array<float> prevIndexLevels = {_pine_array(prev["rows"], "strike")}\n'
        f'var array<float> prevValues = {_pine_array(prev["rows"], "net")}\n'
    )
    code = code.replace(array_anchor, arrays + array_anchor, 1)
    pairs = [({"rows": [{"net_gamma": r["net"]} for r in g["rows"]]}, offset)
             for g, offset in ((prev, 100), (cur, 195), (weekly, 295))]
    scale, step = _initial_manual_scale(pairs)
    def n(x):
        return f"{float(x):.8f}".rstrip("0").rstrip(".")
    import re
    expr = r'gammaPerCandle = input.float\([^\n]+'
    match = re.search(expr, code)
    if not match:
        raise ValueError("Scala Pine non trovata.")
    replacement = (
        f'gammaPerCandle = input.float({n(scale)}, '
        f'"Scala MANUALE · Gamma/barra", minval=0.000001, step={n(step)}, '
        'tooltip="Scala unica tra tutte le tre fotografie; Gamma invariato.")'
    )
    code = code[:match.start()] + replacement + code[match.end():]
    marker = "if barstate.islast and validTicker\n"
    if code.count(marker) != 1:
        raise ValueError("Disegno Pine non compatibile.")
    code = code.split(marker, 1)[0]
    factor = CONFIG[ticker]["factor"]
    prev_title = f"0DTE {LABELS[prev_slot]} · Acq {pine_capture_clock(prev_info['rome'])['clock']}"
    cur_title = f"0DTE {LABELS[current_slot]} · Acq {pine_capture_clock(cur_info['rome'])['clock']}"
    week_title = f"Weekly {LABELS[current_slot]} · Acq {pine_capture_clock(cur_info['rome'])['clock']}"
    # New drawing block only. Original strike and Gamma arrays are unchanged.
    code += f"""if barstate.islast and validTicker
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
    array<float> prevMapped = array.new_float()
    array<float> curMapped = array.new_float()
    array<float> weeklyMapped = array.new_float()
    array<float> callMapped = array.new_float()
    array<float> putMapped = array.new_float()
    for x in prevIndexLevels
        array.push(prevMapped, x * {factor:.1f} + indexFutureBasis)
    for x in mainLevels
        array.push(curMapped, x * {factor:.1f} + indexFutureBasis)
    for x in weeklyLevels
        array.push(weeklyMapped, x * {factor:.1f} + indexFutureBasis)
    for x in topCalls
        array.push(callMapped, x * {factor:.1f} + indexFutureBasis)
    for x in topPuts
        array.push(putMapped, x * {factor:.1f} + indexFutureBasis)
    int previousCenter = offsetOdte
    int currentCenter = previousCenter + (showPrevious ? offsetCompare : 0)
    int weeklyCenter = currentCenter + offsetWeekly
    float safeScale = math.max(
         showPrevious ? requiredScale(prevValues, previousCenter) : 0.0,
         showCurrentOdte ? requiredScale(mainValues, currentCenter) : 0.0)
    safeScale := math.max(safeScale,
         showCurrentWeekly ? requiredScale(weeklyValues, weeklyCenter) : 0.0)
    bool tooFar = (showPrevious and previousCenter >= 480) or (showCurrentOdte and currentCenter >= 480) or (showCurrentWeekly and weeklyCenter >= 480)
    if tooFar or gammaPerCandle < safeScale * 0.999999
        label warning = label.new(bar_index + 10, close, "Distanza profili o scala Gamma da correggere.", style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, warning)
    else
        if showPrevious
            renderProfile(prevMapped, prevValues, bar_index + previousCenter, "{prev_title}", gammaPerCandle)
        if showCurrentOdte
            renderProfile(curMapped, mainValues, bar_index + currentCenter, "{cur_title}", gammaPerCandle)
        if showCurrentWeekly
            renderProfile(weeklyMapped, weeklyValues, bar_index + weeklyCenter, "{week_title}", gammaPerCandle)
        if showTop3Odte
            drawOdteTopProjections(callMapped, putMapped)
"""
    label = f"{LABELS[prev_slot]} → {LABELS[current_slot]}"
    header = (f"// Confronto reale {ticker} {label}; "
              f"0DTE precedente/corrente e Weekly corrente. "
              "Stesso basis; nessun Gamma modificato.\n")
    return code.replace("//@version=6\n", "//@version=6\n" + header, 1)


def render_index_timed_exports(ticker, day, reference, band, basis):
    """The same 3-column, single copy-code panel already used by NQ/GC/CL."""
    if ticker not in ("RUT", "DJX"):
        raise ValueError("Indice non supportato.")
    st.subheader("Esportazione Pine Script v6")
    final_slot = slots_for_day(day)[-1]
    final_label = LABELS[final_slot]
    st.markdown(f"**Pine per orari · 07:30 / 15:50 / {final_label}**")
    st.caption("07:30: 0DTE + Weekly · 15:50: confronto 07:30→15:50 · "
               f"{final_label}: confronto 15:50→{final_label}. Solo fotografie reali "
               "della stessa seduta New York; Gamma CBOE originali.")
    key = f"v2_index_timed_{ticker}_{day.isoformat()}"
    saved = st.session_state.get(key)
    loaded_at = st.session_state.get(key + "_loaded_at", 0.0)
    refresh = st.button("Aggiorna Pine per orari", key=f"refresh_{key}")
    if saved is None or refresh or (len(saved) < len(slots_for_day(day)) and monotonic() - loaded_at > 180):
        try:
            captures = load_pine_slot_captures(ticker, day)
            saved = captures
            st.session_state[key] = saved
            st.session_state[key + "_loaded_at"] = monotonic()
        except Exception as exc:
            st.warning("Archivio rilevamenti non disponibile: " + str(exc)[:180])
            saved = {}
    profiles, errors = _snapshot_profiles(ticker, saved, day, reference, band)
    scripts = {}
    for slot in slots_for_day(day):
        if slot not in profiles:
            errors.setdefault(slot, "Fotografia CBOE di questo slot non disponibile.")
            continue
        try:
            now = profiles[slot]
            if slot == "0730":
                script = _pine(ticker, {"0DTE": now["0DTE"], "Weekly": now["Weekly"]},
                               future_mode=True, future_basis=basis)
            else:
                prev_slot = "0730" if slot == "1550" else "1550"
                if prev_slot not in profiles:
                    raise ValueError("Manca la precedente 0DTE reale.")
                previous = profiles[prev_slot]
                script = _comparison_pine(
                    ticker, previous["0DTE"], now["0DTE"], now["Weekly"],
                    basis, previous["capture"], now["capture"], prev_slot, slot)
            try:
                from macro_events import events_for_pine
                news = events_for_pine(day)
                if news:
                    script = append_news(script, news,
                                         captured_at=now["capture"]["rome"])
            except Exception:
                pass  # News never modify or block verified Gamma.
            scripts[slot] = script
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            errors[slot] = str(exc)[:210]
    cols = st.columns(3, gap="small")
    labels = {"0730": "07:30 · 0DTE + Weekly",
              "1550": "07:30 → 15:50 · 0DTE + Weekly",
              "1700": "15:50 → 17:00 · 0DTE + Weekly",
              "2030": "15:50 → 20:30 · 0DTE + Weekly"}
    for column, slot in zip(cols, slots_for_day(day)):
        with column:
            if slot in scripts:
                st.download_button(
                    "Scarica Pine · " + labels[slot],
                    data=scripts[slot].encode("utf-8"),
                    file_name=f"{ticker}_NET_GAMMA_{day:%Y%m%d}_{slot}.pine",
                    mime="text/plain", on_click="ignore",
                    key=f"{ticker}_timed_{day}_{slot}",
                    use_container_width=True)
                st.caption("Acquisizione reale: " +
                           pine_capture_clock(profiles[slot]["capture"]["rome"])["stamp"])
            else:
                st.button("Pine " + labels[slot] + " · non disponibile",
                          disabled=True, key=f"{ticker}_missing_{day}_{slot}",
                          use_container_width=True)
                st.caption(errors.get(slot, "Fotografia non disponibile."))
    if scripts:
        with st.expander("Mostra codice Pine da copiare e incollare"):
            selected = st.selectbox("Pine orario", list(scripts),
                                    format_func=lambda slot: labels[slot],
                                    key=f"v2_index_code_{ticker}_{day}")
            st.code(scripts[selected], language="pine")
    else:
        st.warning("Nessuna fotografia oraria verificata disponibile: "
                   "non si generano confronti retroattivi.")
