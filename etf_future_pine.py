"""Pine v6 ETF-option Gamma projected via synchronized FROZEN ETF/future ratio.

Pine has optional dynamic mode matching 5-minute time-keys; neither mode
claims native GC/CL options levels, and raw Gamma is never rescaled.
"""
from datetime import date
from math import isfinite
from pine_export import _pine_array, _initial_manual_scale, _top_gamma_rows
from pine_spx_visual import spx_inputs, SPX_RENDER_FUNCTIONS, spx_last_bar
from v2_pine_capture import pine_capture_clock

ASSETS = {
    "GLD": {"roots": ("GC", "MGC"), "label": "Gold GC/MGC",
            "continuous": "COMEX:GC1!",
            "continuous_micro": "COMEX_MINI:MGC1!"},
    "USO": {"roots": ("CL", "MCL"), "label": "Petrolio CL/MCL",
            "continuous": "NYMEX:CL1!",
            "continuous_micro": "NYMEX:MCL1!"},
}


def make_etf_future_pine(symbol: str, profiles: dict, etf_previous_close: float,
                         target: date, label: str, mapping: dict,
                         acquisition_time=None, *, continuous=False) -> str:
    if symbol not in ASSETS:
        raise ValueError("Sottostante Pine ETF non riconosciuto.")
    if not isinstance(target, date):
        raise ValueError("Data di riferimento non valida.")
    try:
        etf_reference = float(etf_previous_close)
    except (TypeError, ValueError) as exc:
        raise ValueError("Close precedente ETF mancante.") from exc
    if not isfinite(etf_reference) or etf_reference <= 0:
        raise ValueError("Close precedente ETF non valido.")
    if continuous:
        # Pine obtains both CLOSED 5m quotes from TradingView. No Massive,
        # Yahoo proxy, guessed locked ratio, or cross-contract substitution.
        if mapping is not None:
            raise ValueError("Per il continuo non inserire un rapporto esterno.")
        etf_price = fut_price = locked_ratio = None
        future_tv = ASSETS[symbol]["continuous"]
    else:
        if not isinstance(mapping, dict) or mapping.get("etf_symbol") != symbol:
            raise ValueError("Acquisisci un rapporto ETF/future sincronizzato e bloccato prima di esportare.")
        try:
            etf_price, fut_price, locked_ratio = (
                float(mapping["etf_price"]), float(mapping["future_price"]), float(mapping["ratio"]))
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("Prezzi per la mappatura ETF/future mancanti.") from exc
        if (not all(isfinite(x) and x > 0 for x in (etf_price, fut_price, locked_ratio))
                or abs(locked_ratio - fut_price / etf_price) > 1e-8):
            raise ValueError("Rapporto ETF/future incoerente con i prezzi abbinati.")
        future_tv = str(mapping.get("future_tv_symbol", ""))
        valid_prefix = "COMEX:GC" if symbol == "GLD" else "NYMEX:CL"
        if not future_tv.startswith(valid_prefix) or not mapping.get("bar_ny"):
            raise ValueError("Contratto future o timestamp rapporto non valido.")
    if not profiles or any(x not in ("0DTE", "Principale", "Weekly") for x in profiles):
        raise ValueError("Profili Pine ETF non riconosciuti.")
    if "Principale" in profiles and "0DTE" in profiles:
        raise ValueError("Non includere contemporaneamente Principale e 0DTE.")
    for p in profiles.values():
        if not p.get("usable") or not p.get("rows"):
            raise ValueError("Esportazione disabilitata: profilo ETF non completo.")
        if not p.get("expiry"):
            raise ValueError("Scadenza ETF assente.")
        date.fromisoformat(str(p["expiry"]))
        for r in p["rows"]:
            if not all(key in r for key in ("strike", "net")):
                raise ValueError("Dati strike o Gamma assenti.")
            try:
                strike, gamma = float(r["strike"]), float(r["net"])
            except (ValueError, TypeError) as exc:
                raise ValueError("Strike o Gamma non numerico.") from exc
            if not (isfinite(strike) and strike > 0 and isfinite(gamma)):
                raise ValueError("Strike o Gamma non finito.")
    total = sum(len(x["rows"]) for x in profiles.values())
    if total > 480:
        raise ValueError(f"Servono {total} linee (massimo 480): riduci la fascia "
                         "oppure esporta i profili separati; nessuno strike viene nascosto.")

    main_name = "0DTE" if "0DTE" in profiles else ("Principale" if "Principale" in profiles else "0DTE")
    main = profiles.get(main_name, {"rows": [], "expiry": ""})
    weekly = profiles.get("Weekly", {"rows": [], "expiry": ""})
    main_rows, weekly_rows = main["rows"], weekly["rows"]
    # Principale/Weekly is NOT 0DTE. Never project those as 0DTE.
    top_call = (_top_gamma_rows(main_rows, "strike", "net", positive=True)
                if main_name == "0DTE" else [])
    top_put = (_top_gamma_rows(main_rows, "strike", "net", positive=False)
               if main_name == "0DTE" else [])
    scale_p = [(dict(rows=[{"net_gamma": row["net"]} for row in main_rows]), 100),
               (dict(rows=[{"net_gamma": row["net"]} for row in weekly_rows]), 200)]
    scale, step = _initial_manual_scale(scale_p)
    # Keep the same manual presentation-scale concept as the tested NDX exporter.
    def n(x):
        return f"{x:.8f}".rstrip("0").rstrip(".")

    roots = ASSETS[symbol]["roots"]
    market = ASSETS[symbol]["label"]
    capture = pine_capture_clock(acquisition_time)
    capture_suffix = ("Acq " + capture["clock"] if capture["verified"]
                      else capture["clock"])
    valid = " or ".join(f'syminfo.root == "{root}"' for root in roots)
    main_label = (f'{main_name} {date.fromisoformat(main["expiry"]):%d/%m} · '
                  f'{capture_suffix}' if main_rows else "")
    weekly_label = (f'Weekly {date.fromisoformat(weekly["expiry"]):%d/%m} · '
                    f'{capture_suffix}' if weekly_rows else "")
    # All three Multi-Market exports use the same Serafini SPX graphical code.
    # Ratio calculations are isolated here, before the SPX-style renderer.
    visual_inputs = spx_inputs(
        n(max(0.000001, scale)), n(max(0.00000001, step)), main_name,
        "Scala grafica MANUALE comune ai profili. NET GAMMA ETF invariato.")
    main_call = (f'renderProfile(odteLevels, mainGammaETF, bar_index + offsetOdte, '
                 f'"{main_label}", actualScale)' if main_rows else "")
    weekly_call = (f'renderProfile(weeklyLevels, weeklyGammaETF, bar_index + weeklyCenter, '
                   f'"{weekly_label}", actualScale)' if weekly_rows else "")
    prepare = (
        "array<float> odteLevels = mapETF(mainStrikesETF, ratioToDraw)\n"
        "array<float> weeklyLevels = mapETF(weeklyStrikesETF, ratioToDraw)\n"
        "array<float> topCallFutures = mapETF(topCallStrikesETF, ratioToDraw)\n"
        "array<float> topPutFutures = mapETF(topPutStrikesETF, ratioToDraw)"
    )
    visual_draw = spx_last_bar(
        main_call, weekly_call, "mainGammaETF", "weeklyGammaETF", prepare,
        top3_levels=("topCallFutures", "topPutFutures")
        if main_name == "0DTE" and main_rows else None)
    if continuous:
        # Without a true matched pair, NEVER create fictitious 0-price lines.
        visual_draw = visual_draw.replace(
            "if barstate.islast and validTicker\n",
            "if barstate.islast and validTicker and not na(ratioToDraw)\n", 1)
        visual_draw += """
var label missingRatioLabel = na
if barstate.islast and validTicker and na(ratioToDraw)
    if not na(missingRatioLabel)
        label.delete(missingRatioLabel)
    missingRatioLabel := label.new(bar_index, close, "NET GAMMA ETF: rapporto continuo non disponibile. Apri @FUT_TV@ su TF 1m/5m e verifica dati ETF/future.", style=label.style_label_left, textcolor=color.black, color=color.orange, size=size.small)
else if barstate.islast and not na(missingRatioLabel)
    label.delete(missingRatioLabel)
    missingRatioLabel := na
"""
    if continuous:
        visual_draw = visual_draw.replace("@FUT_TV@", future_tv)
    template = """//@version=6
indicator("Multi-Market NET GAMMA · @SYMBOL@ → @MARKET@ · @DATE@ · @CLOCK@ · @LABEL@", overlay=true, max_lines_count=500, max_labels_count=50)
// Ora acquisizione fotografia Cboe (Europe/Rome; CET/CEST): @ACQUISITION@. Non e' il timestamp Cboe originale.
// Fonte: opzioni ETF @SYMBOL@ Cboe, Gamma originale. NON opzioni native del future @MARKET@.
// ATTENZIONE: la mappatura percentuale ETF → future e' una STIMA grafica, NON un livello opzioni @MARKET@.
// Formula ETF invariata: Call [(OI+Volume)*Gamma] - Put [(OI+Volume)*Gamma].
// Riferimento ETF (close precedente al rilevamento): @ETF_REFERENCE@.
// @MAPPING_NOTE@
// Contratto future riferimento: @FUT_TV@.
// ETF non quotato durante tutta la sessione future: conserva l'ultimo rapporto valido.
// Le barre 5m sono confermate, ma i livelli proiettati possono cambiare nel tempo.
string etfTicker = "@ETF_TV@"
@CONTRACT_TICKER_LINE@
validTicker = @VALID_TICKER_EXPR@
@RATIO_MODE_LINE@
@RATIO_LOCKED_LINE@
@SPX_INPUTS@

// Solo barre ETF/future 5m CHIUSE e con lo stesso timestamp.
var float lastDynamicRatio = na
var int lastMatchedTime = na
if timeframe.isintraday
    if timeframe.in_seconds() <= 300
        [etfLast, etfTime] = request.security(etfTicker, "5", [close[1], time[1]], gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_on, ignore_invalid_symbol=true)
        [futLast, futTime] = request.security(contractTicker, "5", [close[1], time[1]], gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_on, ignore_invalid_symbol=true)
        if not na(etfLast) and not na(futLast) and etfLast > 0 and futLast > 0 and not na(etfTime) and etfTime == futTime and (na(lastMatchedTime) or etfTime > lastMatchedTime)
            lastDynamicRatio := futLast / etfLast
            lastMatchedTime := etfTime
    else
        // Su 15m/30m/60m esamina le barre interne reali, non un valore
        // aggregato arbitrario. [1] esclude la barra 5m ancora in formazione.
        [etfCloses, etfTimes] = request.security_lower_tf(etfTicker, "5", [close[1], time[1]], ignore_invalid_symbol=true)
        [futCloses, futTimes] = request.security_lower_tf(contractTicker, "5", [close[1], time[1]], ignore_invalid_symbol=true)
        int i = array.size(etfTimes) - 1
        int j = array.size(futTimes) - 1
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
bool dynamicAvailable = modeRatio == "Dinamico" and not na(lastDynamicRatio)
float ratioToDraw = @RATIO_SELECTION@
plot(ratioToDraw, title="Rapporto ETF/future", display=display.data_window)

var array<line> drawnLines = array.new_line()
var array<label> drawnLabels = array.new_label()
var array<float> mainStrikesETF = @MAIN_STRIKES@
var array<float> mainGammaETF = @MAIN_GAMMA@
// TOP3 solo dalle opzioni ETF 0DTE; stessa conversione al continuo del profilo.
var array<float> topCallStrikesETF = @TOP_CALL_STRIKES@
var array<float> topPutStrikesETF = @TOP_PUT_STRIKES@
var array<float> weeklyStrikesETF = @WEEKLY_STRIKES@
var array<float> weeklyGammaETF = @WEEKLY_GAMMA@

// Conversione dello strike ETF al prezzo del future PRIMA del disegno.
// Nessuna variazione al Gamma: il rendering sotto e' quello comune SPX.
mapETF(array<float> etfLevels, float ratio) =>
    array<float> resultLevels = array.new_float()
    for etfStrike in etfLevels
        array.push(resultLevels, etfStrike * ratio)
    resultLevels

@SPX_RENDER_FUNCTIONS@

@SPX_DRAW@
"""
    if continuous:
        micro_tv = ASSETS[symbol]["continuous_micro"]
        validity = (
            'syminfo.type == "futures" and '
            f'(ticker.standard(syminfo.tickerid) == "{future_tv}" or '
            f'ticker.standard(syminfo.tickerid) == "{micro_tv}")')
        # The 5m future price comes from the ACTUAL continuous contract
        # open in TradingView, so GC and MGC (or CL and MCL) are never
        # silently mixed for the same ratio.
        contract_line = 'string contractTicker = ticker.standard(syminfo.tickerid)'
        mapping_note = (
            "SOLO FUTURE CONTINUO: Gamma Cboe ETF fissi per lo snapshot, "
            "ratio DINAMICO TradingView da barre 5m chiuse e sincronizzate. "
            "Nessun rapporto iniziale inventato. "
            "Usare su timeframe 1m o 5m su GC1!/MGC1! "
            "oppure CL1!/MCL1! secondo lo strumento.")
        mode_line = 'modeRatio = "Dinamico"'
        locked_line = 'float lockedRatio = na'
        ratio_selection = 'dynamicAvailable ? lastDynamicRatio : na'
    else:
        validity = f'syminfo.type == "futures" and ({valid})'
        contract_line = f'string contractTicker = "{future_tv}"'
        mapping_note = (
            f"Rapporto congelato ETF {etf_price:.5f}; Future {fut_price:.5f}; "
            f"ratio {locked_ratio:.12f}; barra {mapping['bar_ny']}. "
            f"Fonte: {str(mapping.get('source', ''))[:120]}. "
            "Bloccato predefinito, dinamico facoltativo.")
        mode_line = (
            'modeRatio = input.string("Bloccato", "Rapporto ETF/future", '
            'options=["Bloccato", "Dinamico"], '
            'tooltip="Bloccato: rapporto verificato per la fotografia. '
            'Dinamico: ultimo rapporto barre ETF e futuro 5m CHIUSE con stesso timestamp.")')
        locked_line = f"float lockedRatio = {locked_ratio:.12f}".rstrip("0").rstrip(".")
        ratio_selection = 'dynamicAvailable ? lastDynamicRatio : lockedRatio'
    substitutions = {
        "@SYMBOL@": symbol,
        "@MARKET@": market,
        "@DATE@": target.isoformat(),
        "@CLOCK@": capture_suffix,
        "@ACQUISITION@": capture["stamp"],
        "@LABEL@": label.replace('"', "").replace("\\n", " ")[:60],
        "@VALID_TICKER_EXPR@": validity,
        "@MAPPING_NOTE@": mapping_note.replace("\\n", " "),
        "@RATIO_MODE_LINE@": mode_line,
        "@RATIO_LOCKED_LINE@": locked_line,
        "@RATIO_SELECTION@": ratio_selection,
        "@ETF_REFERENCE@": n(etf_reference),
        "@ETF_TV@": "AMEX:" + symbol,
        "@FUT_TV@": future_tv,
        "@CONTRACT_TICKER_LINE@": contract_line,
        "@SPX_INPUTS@": visual_inputs,
        "@SPX_RENDER_FUNCTIONS@": SPX_RENDER_FUNCTIONS,
        "@SPX_DRAW@": visual_draw,
        "@MAIN_STRIKES@": _pine_array(main_rows, "strike"),
        "@MAIN_GAMMA@": _pine_array(main_rows, "net"),
        "@TOP_CALL_STRIKES@": _pine_array(top_call, "strike"),
        "@TOP_PUT_STRIKES@": _pine_array(top_put, "strike"),
        "@WEEKLY_STRIKES@": _pine_array(weekly_rows, "strike"),
        "@WEEKLY_GAMMA@": _pine_array(weekly_rows, "net"),
    }
    for key, val in substitutions.items():
        template = template.replace(key, str(val))
    return template
