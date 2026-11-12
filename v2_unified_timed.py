"""Timed unified 6-market exporter: 07:30 / 15:50 / 17:00 (legacy 20:30).

Comparisons are based ONLY on validated same-day Cboe snapshots. They draw
the preceding real 0DTE plus current 0DTE and current Weekly. This module
extends the existing single-market graphics engine without changing Serafini
Gamma, original strike values, ticker conversions, or ETF/future mapping.
"""
from datetime import datetime, date
from time import monotonic
from math import isfinite
from zoneinfo import ZoneInfo

import streamlit as st

from pine_export import _pine_array, _initial_manual_scale
from v2_pine_session import LABELS, slots_for_day, compare_capture_pair
from v2_pine_capture import pine_capture_clock
from v2_storage_off import load_pine_slot_captures
from v2_unified_pine import (
    MARKETS, ROOTS, ETF, _from_capture, _session_basis,
    _num, build_unified_pine, GAMMA_LIMIT,
)

NY = ZoneInfo("America/New_York")


def _checked_comparison(previous, current, symbol):
    """Verify same real expiry. Never mislabel a future principal as 0DTE."""
    kind = current["main_label"]
    if previous["main_label"] != kind:
        raise ValueError(f"{symbol}: tipo di profilo differente tra le due fotografie.")
    if kind != "0DTE" and not (
            symbol in ETF and kind == "Principale (non 0DTE)"):
        raise ValueError(f"{symbol}: tipo principale non confrontabile.")
    if previous["main_expiry"] != current["main_expiry"]:
        raise ValueError(f"{symbol}: scadenze principali precedenti/correnti differenti.")
    size = len(previous["main"]) + len(current["main"]) + len(current["weekly"])
    if size > GAMMA_LIMIT:
        raise ValueError(f"{symbol}: confronto con {size} strike oltre il limite "
                         f"grafico {GAMMA_LIMIT}; nessuno strike eliminato.")
    field = current["field_level"]
    value = current["field_gamma"]
    if previous["field_level"] != field or previous["field_gamma"] != value:
        raise ValueError("Tipologia strike/Gamma incompatibile.")
    if not all(isfinite(float(x[value])) and isfinite(float(x[field]))
               for x in previous["main"]):
        raise ValueError(f"{symbol}: Gamma precedente non valido.")
    # The PREVIOUS profile is OFF by default. Derive the recommended scale
    # from CURRENT and WEEKLY only, exactly as in the 07:30 Pine.
    # When previous is enabled Pine automatically checks its own size.
    return dict(current)


def build_unified_comparison_pine(day, current, previous, slot, reports=None):
    """Upgrade the SAME unified Pine renderer to three verified columns."""
    if not isinstance(day, date) or slot not in slots_for_day(day)[1:]:
        raise ValueError("Fascia di confronto non prevista per la seduta.")
    if not current:
        raise ValueError("Nessun profilo corrente reale disponibile.")
    if set(previous) - set(current):
        raise ValueError("Fotografie precedenti senza mercato corrente.")
    valid = {}
    for symbol, item in current.items():
        valid[symbol] = (_checked_comparison(previous[symbol], item, symbol)
                         if symbol in previous else dict(item))
    script = build_unified_pine(day, valid)
    prev_slot = "0730" if slot == "1550" else "1550"
    marker = 'offsetOdte = input.int(100, "Distanza profilo principale", minval=45, maxval=250)'
    if script.count(marker) != 1:
        raise ValueError("Template unico: offset profili assente.")
    script = script.replace(marker,
        marker + '\nshowPrevious = input.bool(false, "Mostra 0DTE precedente")'
        '\noffsetCompare = input.int(95, "Distanza corrente dalla precedente",'
        ' minval=20, maxval=200)', 1)
    # Immutable original strike and original Gamma arrays of previous snapshots.
    prev_arrays = []
    for symbol in MARKETS:
        p = previous.get(symbol)
        if p is None:
            prev_arrays.extend([
                f"var array<float> {symbol}PrevLevels = array.new_float()",
                f"var array<float> {symbol}PrevGamma = array.new_float()",
            ])
        else:
            prev_arrays.extend([
                f'var array<float> {symbol}PrevLevels = {_pine_array(p["main"], p["field_level"])}',
                f'var array<float> {symbol}PrevGamma = {_pine_array(p["main"], p["field_gamma"])}',
            ])
    names = "\n".join(prev_arrays)
    start = "var array<line> drawnLines = array.new_line()"
    if script.count(start) != 1:
        raise ValueError("Template unico: inizio disegno non trovato.")
    prev_selection = """array<float> previousLevels = switch activeMarket
    "NDX" => NDXPrevLevels
    "RUT" => RUTPrevLevels
    "DJX" => DJXPrevLevels
    "GLD" => GLDPrevLevels
    "USO" => USOPrevLevels
    => array.new_float()
array<float> previousGamma = switch activeMarket
    "NDX" => NDXPrevGamma
    "RUT" => RUTPrevGamma
    "DJX" => DJXPrevGamma
    "GLD" => GLDPrevGamma
    "USO" => USOPrevGamma
    => array.new_float()
"""
    script = script.replace(start, names + "\n" + prev_selection + "\n" + start, 1)
    # Source has exactly one guarded drawing block, generated by build_unified_pine.
    anchor = "if barstate.islast and validTicker\n"
    if script.count(anchor) != 1:
        raise ValueError("Template unico: guardia disegno non compatibile.")
    # Exact reasons from archive checks; do not misdiagnose basis errors.
    reasons = reports or {}
    def _pine_reason(symbol):
        msg = str(reasons.get(symbol, "Fotografia corrente non disponibile"))
        if msg.startswith("N/D · "):
            msg = msg[6:]
        return msg.replace('"', "'").replace("\n", " ")[:135]
    unavailable_switch = "\n".join(
        f'    "{symbol}" => "{_pine_reason(symbol)}"' for symbol in MARKETS
    ) + '\n    => "Mercato non supportato"'
    anchor = "if barstate.islast and validTicker\n"
    script = script[:script.index(anchor)] + """
// Scala dei soli istogrammi: NET GAMMA originali e strike invariati.
unifiedReadableScale(array<float> values, float maxBars) =>
    float peak = 0.0
    for g in values
        peak := math.max(peak, math.abs(g))
    peak / math.max(1.0, maxBars)

string missingReason = switch activeMarket
@MISSING@
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
        label info = label.new(bar_index + 10, close, "Profilo @CUR@ " + activeMarket + " N/D: " + missingReason, style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, info)
    else if not ratioValid
        label warn = label.new(bar_index, close, "ETF/future: nessuna coppia 5m chiusa e sincronizzata; nessun livello simulato.", style=label.style_label_left, color=color.orange, textcolor=color.black)
        array.push(drawnLabels, warn)
    else
        float factor = isETF ? ratioToDraw : priceFactor
        float shift = isETF ? 0.0 : basisIndex
        array<float> prevMapped = mapMarket(previousLevels, factor, shift)
        array<float> drawMain = mapMarket(mainLevels, factor, shift)
        array<float> drawWeek = mapMarket(weekLevels, factor, shift)
        array<float> drawCalls = mapMarket(callLevels, factor, shift)
        array<float> drawPuts = mapMarket(putLevels, factor, shift)
        bool previousVisible = showPrevious and array.size(previousLevels) > 0
        int previousCenter = offsetOdte
        int currentCenter = previousCenter + (previousVisible ? offsetCompare : 0)
        int weeklyCenter = currentCenter + offsetWeekly
        float safe = math.max(
            previousVisible ? requiredScale(previousGamma, previousCenter) : 0.0,
            showCurrentOdte ? requiredScale(mainGamma, currentCenter) : 0.0)
        safe := math.max(safe,
            showCurrentWeekly ? requiredScale(weekGamma, weeklyCenter) : 0.0)
        float barsCurrent = previousVisible ? 42.0 : 78.0
        float readable = math.max(
            previousVisible ? unifiedReadableScale(previousGamma, 42.0) : 0.0,
            showCurrentOdte ? unifiedReadableScale(mainGamma, barsCurrent) : 0.0)
        readable := math.max(readable,
            showCurrentWeekly ? unifiedReadableScale(weekGamma, 78.0) : 0.0)
        float effectiveScale = math.max(actualScale, math.max(safe * 1.001, readable))
        bool far = (previousVisible and previousCenter >= 480) or (showCurrentOdte and currentCenter >= 480) or (showCurrentWeekly and weeklyCenter >= 480)
        if far
            label warning = label.new(bar_index + 10, close, "Distanza profili oltre +480 barre: riduci gli offset.", style=label.style_label_left, color=color.orange, textcolor=color.black)
            array.push(drawnLabels, warning)
        else
            if previousVisible
                renderProfile(prevMapped, previousGamma, previousCenter + bar_index, mainKind + " @PREV@ · precedente · " + primaryExpiry, effectiveScale)
            if showCurrentOdte
                renderProfile(drawMain, mainGamma, currentCenter + bar_index, mainKind + " @CUR@ · corrente · " + snapshotClock, effectiveScale)
            if showCurrentWeekly
                renderProfile(drawWeek, weekGamma, weeklyCenter + bar_index, "Weekly " + weeklyExpiry + " · " + snapshotClock, effectiveScale)
            if showPrevious and not previousVisible
                label noPrior = label.new(bar_index + currentCenter, close, "Precedente @PREV@ non disponibile", style=label.style_label_left, color=color.gray, textcolor=color.white, size=size.tiny)
                array.push(drawnLabels, noPrior)
            if showTop3Odte and mainKind == "0DTE"
                drawOdteTopProjections(drawCalls, drawPuts)
""".replace("@MISSING@", unavailable_switch)

    script = script.replace("@PREV@", LABELS[prev_slot]).replace("@CUR@", LABELS[slot])
    script = script.replace("UNICO 07:30 ·", f"UNICO {LABELS[slot]} ·", 1)
    return script


def _verified_basis(symbol, market_day):
    """No guessed cash/future basis; cache date-bound independently of widgets."""
    basis = _session_basis(symbol, market_day)
    if basis is not None:
        return basis
    key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
    if not key:
        raise ValueError("MASSIVE_API_KEY non configurata.")
    if symbol == "NDX":
        from ndx_basis import fetch_basis
        result = fetch_basis(market_day, key)
    else:
        from v2_index_basis import compute_basis
        result = compute_basis(symbol, market_day, key)
    basis = float(result["basis"])
    if not isfinite(basis):
        raise ValueError("Differenziale non finito.")
    st.session_state[f"mm_unified_basis_{symbol}"] = {
        "analysis_day": market_day.isoformat(),
        "basis": basis,
        "source": result.get("source", ""),
        "reference_date": str(result.get("reference_date", "")),
    }
    return basis


def _market_band(symbol):
    if symbol in ("RUT", "DJX"):
        return float(st.session_state.get(f"v2_primary_{symbol.lower()}_band", 5.0))
    if symbol == "NDX":
        return float(st.session_state.get("ndx_band_pct", 3.0))
    return float(st.session_state.get(f"{symbol.lower()}_cboe_band", 3.0))


def prepare_slot(day, slot):
    """Read 5 independent CBOE archives plus official SPX; no look-ahead."""
    if slot not in slots_for_day(day):
        raise ValueError("Orario non previsto per la seduta selezionata.")
    prev_slot = "0730" if slot == "1550" else "1550"
    records, previous, reports = {}, {}, {}
    # Read-only SPX bridge. Failed auth must NEVER disable the other 5 assets.
    try:
        from v2_spx_bridge import load_official_spx, spx_record, spx_basis
        spx_frames = load_official_spx(day, slots_for_day(day))
        spx_problem = None
    except (ValueError, OSError, TypeError, KeyError) as exc:
        spx_frames, spx_problem = {}, str(exc)[:170]

    for symbol in MARKETS:
        try:
            if symbol == "SPX":
                if spx_problem:
                    raise ValueError(spx_problem)
                current_frame = spx_frames.get(slot)
                if current_frame is None:
                    raise ValueError(f"SPX: fotografia ufficiale {LABELS[slot]} "
                                     "non verificata nell'archivio Serafini SPX.")
                basis, basis_source = spx_basis(day)
                extension = bool(st.session_state.get("mm_unified_spx_extension", True))
                now = spx_record(current_frame, day, basis, extension=extension)
                prior_note = ""
                old = None
                if slot != "0730":
                    earlier = spx_frames.get(prev_slot)
                    if earlier is not None:
                        try:
                            old_time = datetime.fromisoformat(earlier["download_rome"])
                            now_time = datetime.fromisoformat(current_frame["download_rome"])
                            if old_time >= now_time:
                                raise ValueError("timestamp precedenti non cronologici.")
                            candidate = spx_record(
                                earlier, day, basis, extension=extension)
                            _checked_comparison(candidate, now, symbol)
                            old = candidate
                        except (ValueError, TypeError, KeyError) as exc:
                            prior_note = " · precedente SPX N/D: " + str(exc)[:95]
                    else:
                        prior_note = f" · precedente SPX {LABELS[prev_slot]} non verificato"
                records[symbol] = now
                if old is not None:
                    previous[symbol] = old
                count = len(now["main"]) + len(now["weekly"])
                if old is not None:
                    count += len(old["main"])
                reports[symbol] = (
                    f"OK · SPX UFFICIALE · {LABELS[slot]} · "
                    f"{count} strike · 25+25 originali per profilo · "
                    f"ES−SPX {basis:+.2f} ({basis_source})" + prior_note
                )
                continue

            captures = load_pine_slot_captures(symbol, day)
            current_capture = captures.get(slot)
            if current_capture is None:
                raise ValueError(f"Fotografia corrente {LABELS[slot]} non trovata "
                                 "nell'archivio verificato.")
            band = _market_band(symbol)
            if not 0.0 < band <= 25:
                raise ValueError("Fascia strike non valida.")
            extension = bool(st.session_state.get(
                f"v2_{symbol.lower()}_visual_extension", True))
            now = _from_capture(symbol, current_capture, day, band, extension)
            if symbol not in ETF:
                now["basis"] = _verified_basis(symbol, day)
            else:
                now["basis"] = 0.0
            old = None
            prior_note = ""
            if slot != "0730":
                previous_capture = captures.get(prev_slot)
                if previous_capture is None:
                    prior_note = f"precedente {LABELS[prev_slot]} non archiviato"
                else:
                    try:
                        compare_capture_pair(previous_capture, current_capture,
                                             prev_slot, slot)
                        candidate = _from_capture(
                            symbol, previous_capture, day, band, extension)
                        _checked_comparison(candidate, now, symbol)
                        old = candidate
                    except (ValueError, KeyError, TypeError,
                            OverflowError, OSError) as exc:
                        prior_note = "precedente N/D: " + str(exc)[:110]
            records[symbol] = now
            if old is not None:
                previous[symbol] = old
            total = len(now["main"]) + len(now["weekly"])
            if old is not None:
                total += len(old["main"])
            reports[symbol] = (f"OK · {LABELS[slot]} · "
                               f"{total} strike reali · "
                               f"{now['main_label']} {now['main_expiry']:%d/%m} · "
                               f"Weekly {now['weekly_expiry']:%d/%m}"
                               + (f" · {prior_note}" if prior_note else ""))
        except (ValueError, KeyError, TypeError, OverflowError, OSError) as exc:
            reports[symbol] = f"N/D · {str(exc)[:155]}"
    return records, previous, reports


def render():
    """One panel, three independently prepared and downloadable time slots."""
    with st.expander("PINE MULTI-MARKET UNICO · 07:30 / 15:50 / 17:00",
                     expanded=False):
        st.caption("Un Pine per fascia oraria con ES/MES · NQ/MNQ · RTY/M2K · YM/MYM · "
                   "GC/MGC · CL/MCL. I confronti mostrano 0DTE precedente, "
                   "0DTE corrente e Weekly corrente, soltanto da archivi reali. "
                   "I Pine individuali restano disponibili; Serafini SPX è in sola lettura.")
        day = st.date_input("Seduta New York", value=datetime.now(NY).date(),
                            key="mm_unified_day")
        if not isinstance(day, date):
            st.warning("Seleziona una seduta.")
            return
        slots = slots_for_day(day)
        st.caption("Per le sedute precedenti al cambio d'orario rimane "
                   "il terzo slot storico delle 20:30.")
        # SPX original data stay in the separate, private official archive.
        # A manual verified ES-SPX basis may override SPX's identical Yahoo
        # previous-session methodology. Never overwrite a manual input.
        def _invalidate_spx_scripts():
            saved_items = st.session_state.get("mm_unified_prepared_by_slot", {})
            for cached_key in list(saved_items):
                if cached_key[0] == day.isoformat():
                    saved_items.pop(cached_key, None)

        st.text_input(
            "SPX → ES/MES · differenziale ES−SPX (facoltativo, punti)",
            key=f"mm_unified_spx_basis_manual_{day.isoformat()}",
            placeholder="Vuoto = calcolo automatico come in Serafini SPX",
            on_change=_invalidate_spx_scripts,
            help="Compilare solo con il valore verificato per questa seduta "
                 "nell'app SPX. Se vuoto, usa la medesima media ES=F−^GSPC "
                 "delle barre 15m della sessione cash precedente, arrotondata "
                 "all'intero come nell'app SPX."
        )
        st.checkbox(
            "SPX · estensione grafica originale (25+25 sempre conservati)",
            value=True, key="mm_unified_spx_extension",
            on_change=_invalidate_spx_scripts
        )
        try:
            spx_key_configured = bool(str(
                st.secrets.get("SPX_SUPABASE_READ_KEY", "")).strip())
        except Exception:
            spx_key_configured = False
        if not spx_key_configured:
            st.caption("SPX/ES: la lettura dell'archivio privato richiede "
                       "SPX_SUPABASE_READ_KEY nei Secrets di Multi-Market. "
                       "URL del progetto SPX già configurato; nessuna "
                       "modifica a Serafini SPX. Gli altri cinque mercati "
                       "continuano a funzionare.")
        cache_key = "mm_unified_prepared_by_slot"
        saved = st.session_state.setdefault(cache_key, {})
        # Populate on first visit, then reuse the same immutable snapshot for
        # downloads and code copy. Retry incomplete slots periodically only
        # after explicit page interactions; no repeated archive downloads on
        # each Streamlit widget rerun. The refresh button forces a new audit.
        refresh = st.button("Aggiorna Pine per orari",
                            key=f"mm_unified_refresh_{day}")
        cols = st.columns(3, gap="small")
        for col, slot in zip(cols, slots):
            with col:
                label = LABELS[slot]
                identity = (day.isoformat(), slot)
                prepared = saved.get(identity)
                stale_missing = (
                    prepared is not None and not prepared.get("script")
                    and monotonic() - prepared.get("checked_at", 0) > 180
                )
                if refresh or prepared is None or stale_missing:
                    try:
                        current, previous, reports = prepare_slot(day, slot)
                        script = (
                            build_unified_pine(day, current) if slot == "0730"
                            else build_unified_comparison_pine(
                                day, current, previous, slot, reports=reports)
                        ) if current else None
                        prepared = {
                            "script": script, "reports": reports,
                            "checked_at": monotonic(),
                        }
                    except (ValueError, KeyError, TypeError, OverflowError,
                            OSError) as exc:
                        prepared = {
                            "script": None,
                            "reports": {symbol: "N/D · " + str(exc)[:130]
                                        for symbol in MARKETS},
                            "checked_at": monotonic(),
                        }
                    saved[identity] = prepared
                if prepared and prepared.get("script"):
                    st.download_button(
                        f"Scarica Pine · {label}",
                        data=prepared["script"].encode("utf-8"),
                        file_name=f"Serafini_MultiMarket_UNICO_{slot}_{day:%Y%m%d}.pine",
                        mime="text/plain", on_click="ignore",
                        use_container_width=True,
                        key=f"mm_unified_download_{day}_{slot}")
                    count = sum(
                        x.startswith("OK")
                        for x in prepared["reports"].values())
                    st.caption(f"{count}/{len(MARKETS)} mercati verificati")
                else:
                    st.button(f"Pine · {label} · non disponibile",
                              disabled=True, use_container_width=True,
                              key=f"mm_unified_missing_{day}_{slot}")
                    if prepared:
                        issues = [
                            f"{symbol}: {message}" for symbol, message in
                            prepared["reports"].items()
                            if not message.startswith("OK")
                        ]
                        st.caption(issues[0] if issues else
                                   "Fotografie CBOE non disponibili.")
                    else:
                        st.caption("Fotografie CBOE non disponibili.")
        available = [s for s in slots
                     if saved.get((day.isoformat(), s), {}).get("script")]
        if not available:
            return
        selected = st.selectbox(
            "Visualizza report e codice Pine",
            available, format_func=lambda s: LABELS[s],
            key=f"mm_unified_view_slot_{day}")
        chosen = saved[(day.isoformat(), selected)]
        st.markdown(f"**Pine Multi-Market unico · {LABELS[selected]}**")
        for symbol in MARKETS:
            st.caption(f"{symbol} → {', '.join(ROOTS[symbol])}: "
                       f"{chosen['reports'][symbol]}")
        n = sum(chosen["reports"][symbol].startswith("OK")
                for symbol in MARKETS)
        if n < len(MARKETS):
            st.warning(f"Copertura {n}/{len(MARKETS)} mercati: gli strumenti senza dati "
                       "verificati non mostrano alcun profilo.")
        with st.expander("Mostra codice Pine unico da copiare"):
            st.code(chosen["script"], language="pine")
