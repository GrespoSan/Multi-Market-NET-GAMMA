"""Pine Script v6 export of ETF option-Gamma profiles to related futures.

This is a *percentage-mapped visualization* of Cboe GLD/USO ETF strikes.
It NEVER claims to supply native GC/CL option Gamma or a validated futures
price level. The reference futures close must be checked by the user.
"""
from datetime import date
from math import isfinite
from pine_export import _pine_array, _initial_manual_scale

ASSETS = {
    "GLD": {"roots": ("GC", "MGC"), "label": "Gold GC/MGC"},
    "USO": {"roots": ("CL", "MCL"), "label": "Petrolio CL/MCL"},
}


def make_etf_future_pine(symbol: str, profiles: dict, etf_previous_close: float,
                         target: date, label: str) -> str:
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

    main_name = "0DTE" if "0DTE" in profiles else "Principale"
    main = profiles.get(main_name, {"rows": [], "expiry": ""})
    weekly = profiles.get("Weekly", {"rows": [], "expiry": ""})
    main_rows, weekly_rows = main["rows"], weekly["rows"]
    scale_p = [(dict(rows=[{"net_gamma": row["net"]} for row in main_rows]), 60),
               (dict(rows=[{"net_gamma": row["net"]} for row in weekly_rows]), 160)]
    scale, step = _initial_manual_scale(scale_p)
    # Keep the same manual presentation-scale concept as the tested NDX exporter.
    def n(x):
        return f"{x:.8f}".rstrip("0").rstrip(".")

    roots = ASSETS[symbol]["roots"]
    market = ASSETS[symbol]["label"]
    valid = " or ".join(f'syminfo.root == "{root}"' for root in roots)
    main_label = (f'{main_name} {date.fromisoformat(main["expiry"]):%d/%m}'
                  if main_rows else "")
    weekly_label = (f'Weekly {date.fromisoformat(weekly["expiry"]):%d/%m}'
                    if weekly_rows else "")
    template = """//@version=6
indicator("Multi-Market NET GAMMA · @SYMBOL@ → @MARKET@ · @DATE@ · @LABEL@", overlay=true, max_lines_count=500, max_labels_count=50)
// Fonte: opzioni ETF @SYMBOL@ Cboe, Gamma originale. NON opzioni native del future @MARKET@.
// ATTENZIONE: la mappatura percentuale ETF → future e' una STIMA grafica, NON un livello opzioni @MARKET@.
// Formula ETF invariata: Call [(OI+Volume)*Gamma] - Put [(OI+Volume)*Gamma].
// Riferimento ETF (close precedente al rilevamento): @ETF_REFERENCE@.
// Mappatura: livelloFuture = riferimentoFuture * (strikeETF / riferimentoETF).
// Riferimento future manuale 0 = close Daily precedente del future sul grafico.
// Il riferimento automatico cambia a ogni nuova sessione: usare l'ancora manuale
// per congelare la mappatura di uno snapshot e verificare l'allineamento temporale.
validTicker = syminfo.type == "futures" and (@VALID_ROOTS@)
futureAnchorManual = input.float(0.0, "Riferimento future MANUALE (0 = close D precedente)", minval=0.0, step=0.01, tooltip="Per mantenere livelli fissi imposta il prezzo future riferito alla stessa sessione del close ETF. Con 0 usa il close Daily precedente, che varia ogni nuova seduta e puo' non essere sincronizzato con ETF.")
gammaPerCandle = input.float(@GAMMA_SCALE@, "Scala MANUALE · Gamma/barra", minval=0.000001, step=@SCALE_STEP@, tooltip="Scala grafica, il NET GAMMA delle opzioni ETF non viene alterato.")
offsetOdte = input.int(60, "Distanza profilo principale da ultima candela", minval=45, maxval=170)
offsetWeekly = input.int(160, "Distanza Weekly da ultima candela", minval=55, maxval=300)
positiveColor = input.color(color.rgb(0, 230, 117), "NET GAMMA positivo")
negativeColor = input.color(color.rgb(242, 54, 69), "NET GAMMA negativo")
showTitles = input.bool(true, "Mostra intestazioni")
showContext = input.bool(true, "Mostra avviso mappatura ETF → future")

// Non utilizzare la chiusura della candela in formazione: solo Daily completato.
futureDailyPrevious = request.security(syminfo.tickerid, "D", close[1], lookahead=barmerge.lookahead_on)
float futureReference = futureAnchorManual > 0 ? futureAnchorManual : futureDailyPrevious
bool validReference = not na(futureReference) and futureReference > 0

var array<line> drawnLines = array.new_line()
var array<label> drawnLabels = array.new_label()
var array<float> mainStrikesETF = @MAIN_STRIKES@
var array<float> mainGammaETF = @MAIN_GAMMA@
var array<float> weeklyStrikesETF = @WEEKLY_STRIKES@
var array<float> weeklyGammaETF = @WEEKLY_GAMMA@

requiredScale(array<float> values, int centerDistance) =>
    float p = 0.0
    float n = 0.0
    for g in values
        p := math.max(p, g)
        n := math.max(n, -g)
    math.max(p / float(480 - centerDistance), n / float(9500 + centerDistance))

renderProfile(array<float> strikes, array<float> values, int center, string heading, float scale, float ref) =>
    int count = array.size(strikes)
    if count > 0
        float firstY = array.get(strikes, 0) / @ETF_REFERENCE@ * ref
        float lastY = array.get(strikes, count - 1) / @ETF_REFERENCE@ * ref
        line base = line.new(center, firstY, center, lastY, xloc=xloc.bar_index, color=color.gray, style=line.style_dotted)
        array.push(drawnLines, base)
        for j = 0 to count - 1
            float etfStrike = array.get(strikes, j)
            float yPrice = ref * etfStrike / @ETF_REFERENCE@
            float g = array.get(values, j)
            int length = g != 0 ? math.max(1, int(math.round(math.abs(g) / scale))) : 0
            if length > 0
                line ln = line.new(center, yPrice, center + (g > 0 ? length : -length), yPrice, xloc=xloc.bar_index, color=g >= 0 ? positiveColor : negativeColor, width=5)
                array.push(drawnLines, ln)
        if showTitles
            float spacing = count > 1 ? math.max(syminfo.mintick * 20, (lastY - firstY) / 20.0) : syminfo.mintick * 20
            label title = label.new(center, lastY + spacing, heading, xloc=xloc.bar_index, yloc=yloc.price, color=color.new(color.black, 50), textcolor=color.white, style=label.style_label_down)
            array.push(drawnLabels, title)

if barstate.islast
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
    if validTicker
        if not validReference
            label missing = label.new(bar_index + 10, close, "Riferimento future mancante: inseriscilo nelle impostazioni.", style=label.style_label_left, color=color.orange, textcolor=color.black)
            array.push(drawnLabels, missing)
        else
            float minSafe = math.max(requiredScale(mainGammaETF, offsetOdte), requiredScale(weeklyGammaETF, offsetWeekly))
            if gammaPerCandle < minSafe * 0.999999
                label invalidScale = label.new(bar_index + 10, close, "Scala Gamma/barra troppo piccola: minimo " + str.tostring(minSafe, "#.########"), style=label.style_label_left, color=color.orange, textcolor=color.black)
                array.push(drawnLabels, invalidScale)
            else
                @RENDER_MAIN@
                @RENDER_WEEKLY@
            if showContext
                string refType = futureAnchorManual > 0 ? "manuale" : "auto Daily (variabile)"
                label notice = label.new(bar_index + 3, close, "@SYMBOL@ → @MARKET@ · livelli % indicativi, NON gamma future\\nAncora future " + refType + ": " + str.tostring(futureReference, format.mintick), style=label.style_label_left, color=color.new(color.orange, 60), textcolor=color.white, size=size.tiny)
                array.push(drawnLabels, notice)
"""
    substitutions = {
        "@SYMBOL@": symbol,
        "@MARKET@": market,
        "@DATE@": target.isoformat(),
        "@LABEL@": label.replace('"', "").replace("\n", " ")[:60],
        "@VALID_ROOTS@": valid,
        "@ETF_REFERENCE@": n(etf_reference),
        "@GAMMA_SCALE@": n(max(0.000001, scale)),
        "@SCALE_STEP@": n(max(0.00000001, step)),
        "@MAIN_STRIKES@": _pine_array(main_rows, "strike"),
        "@MAIN_GAMMA@": _pine_array(main_rows, "net"),
        "@WEEKLY_STRIKES@": _pine_array(weekly_rows, "strike"),
        "@WEEKLY_GAMMA@": _pine_array(weekly_rows, "net"),
        "@RENDER_MAIN@": f'renderProfile(mainStrikesETF, mainGammaETF, bar_index + offsetOdte, "{main_label}", gammaPerCandle, futureReference)' if main_rows else '// Profilo principale assente',
        "@RENDER_WEEKLY@": f'renderProfile(weeklyStrikesETF, weeklyGammaETF, bar_index + offsetWeekly, "{weekly_label}", gammaPerCandle, futureReference)' if weekly_rows else '// Weekly assente',
    }
    for key, val in substitutions.items():
        template = template.replace(key, str(val))
    return template
