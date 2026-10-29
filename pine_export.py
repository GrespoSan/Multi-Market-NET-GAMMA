"""Pine v6 per NDX/NQ: stessa interfaccia dei Pine Serafini SPX.
Solo disegno dei NET GAMMA gia' calcolati. Ticker consentiti: NQ e MNQ.
"""
from math import ceil, isfinite
from datetime import date


def _pine_array(rows, field, offset=0.0):
    values=[]
    for row in rows:
        v=float(row[field]) + (offset if field == "strike_index" else 0.0)
        if not isfinite(v):
            raise ValueError("Valore Gamma / strike non finito.")
        formatted=f"{v:.8f}".rstrip("0").rstrip(".")
        values.append(formatted if "." in formatted else formatted+".0")
    if not values:
        return "array.new_float()"
    return "array.from(\n        "+",\n        ".join(
        ", ".join(values[i:i+8]) for i in range(0,len(values),8)
    )+"\n    )"


def _initial_manual_scale(profiles):
    # Nessun ricalcolo del Gamma: solo valore iniziale suggerito per la UI.
    minimum=0.01
    for group,center in profiles:
        vals=[float(r["net_gamma"]) for r in group["rows"]]
        if not vals:
            continue
        necessary=max(max(0.0,max(vals))/float(480-center),
                      max(0.0,-min(vals))/float(9500+center))
        minimum=max(minimum,necessary)
    return ceil(minimum*100-1e-9)/100.0


def make_pine(profiles: dict, basis: float, target: date, label: str) -> str:
    if not profiles or not isfinite(float(basis)):
        raise ValueError("NET GAMMA o differenziale NQ-NDX non valido.")
    if any(name not in ("0DTE","Weekly") for name in profiles):
        raise ValueError("Profilo Pine sconosciuto.")
    for group in profiles.values():
        if not group.get("rows"):
            raise ValueError("Nessuno strike reale nella fascia.")
    # 500 linee massime: un margine per basi, eventi macro e guide.
    total=sum(len(group["rows"]) for group in profiles.values())
    if total>480:
        raise ValueError(
            f"Pine richiede {total} linee Gamma (massimo 480 con margine "
            "per news e basi). Nessuno strike escluso automaticamente: "
            "riduci la percentuale oppure usa i Pine separati 0DTE/Weekly."
        )
    odte=profiles.get("0DTE",{"rows":[],"expiry":""})
    weekly=profiles.get("Weekly",{"rows":[],"expiry":""})
    scale=_initial_manual_scale([(odte,60),(weekly,160)])
    first=date.fromisoformat(odte["expiry"]).strftime("%d/%m") if odte["rows"] else ""
    second=date.fromisoformat(weekly["expiry"]).strftime("%d/%m") if weekly["rows"] else ""
    band=next(iter(profiles.values())).get("band_pct",3.0)
    return f'''//@version=6
indicator("Multi-Market NET GAMMA · NDX/NQ · {target.isoformat()} · {label}", overlay=true, max_lines_count=500, max_labels_count=35)
// Visualizzazione statica dei NET GAMMA calcolati dall'app, mai in Pine.
// Valido esclusivamente per i futures NQ / MNQ; altri strumenti: nessun disegno.
// Fascia di selezione: +/-{band:g}% dal close NDX precedente.
// Differenziale NQ–NDX gia' applicato agli strike: {basis:.4f}
// Formula INVARIATA: Call (OI+Volume)*Gamma - Put (OI+Volume)*Gamma.
// Stessa interfaccia del generatore Serafini SPX.
validTicker = syminfo.type == "futures" and (syminfo.root == "NQ" or syminfo.root == "MNQ")

gammaPerCandle = input.float({scale:.2f}, "Scala MANUALE · Gamma/barra", minval=0.001, step=0.01, tooltip="Scala comune e sempre manuale: nessun adattamento automatico dei NET GAMMA.")
offsetOdte = input.int(60, "Distanza 0DTE da ultima candela", minval=45, maxval=170)
offsetWeekly = input.int(160, "Distanza Weekly da ultima candela", minval=55, maxval=300)
positiveColor = input.color(color.rgb(0, 230, 117), "NET GAMMA positivo")
negativeColor = input.color(color.rgb(242, 54, 69), "NET GAMMA negativo")
showTitles = input.bool(true, "Mostra intestazioni")

var array<line> drawnLines = array.new_line()
var array<label> drawnLabels = array.new_label()
var array<float> odteLevels = {_pine_array(odte["rows"],"strike_index",basis)}
var array<float> odteValues = {_pine_array(odte["rows"],"net_gamma")}
var array<float> weeklyLevels = {_pine_array(weekly["rows"],"strike_index",basis)}
var array<float> weeklyValues = {_pine_array(weekly["rows"],"net_gamma")}

requiredScale(array<float> gamma, int offsetBars) =>
    float maxPos = 0.0
    float maxNeg = 0.0
    for g in gamma
        maxPos := math.max(maxPos, g)
        maxNeg := math.max(maxNeg, -g)
    math.max(maxPos / float(480 - offsetBars), maxNeg / float(9500 + offsetBars))

renderProfile(array<float> levels, array<float> gamma, int center, string heading, float actualScale) =>
    int count = array.size(levels)
    if count > 0
        float bottom = array.get(levels, 0)
        float top = array.get(levels, count - 1)
        line baseline = line.new(center, bottom, center, top, xloc=xloc.bar_index, extend=extend.none, color=color.gray, style=line.style_dotted, width=1)
        array.push(drawnLines, baseline)
        for j = 0 to count - 1
            float level = array.get(levels, j)
            float g = array.get(gamma, j)
            int length = g != 0 ? math.max(1, int(math.round(math.abs(g) / actualScale))) : 0
            if length > 0
                int farX = center + (g > 0 ? length : -length)
                line segment = line.new(center, level, farX, level, xloc=xloc.bar_index, extend=extend.none, color=g >= 0 ? positiveColor : negativeColor, width=5)
                array.push(drawnLines, segment)
        if showTitles
            float spacing = count > 1 ? math.max(5.0, (top - bottom) / 20.0) : 10.0
            label t = label.new(center, top + spacing, heading, xloc=xloc.bar_index, yloc=yloc.price, color=color.new(color.black, 50), textcolor=color.white, style=label.style_label_down, size=size.normal)
            array.push(drawnLabels, t)

if barstate.islast and validTicker
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
    float actualScale = gammaPerCandle
    float minimumSafe = math.max(requiredScale(odteValues, offsetOdte), requiredScale(weeklyValues, offsetWeekly))
    if actualScale + 0.000001 < minimumSafe
        label unsafe = label.new(bar_index + 10, close, "Scala manuale troppo piccola. Imposta almeno " + str.tostring(math.ceil(minimumSafe * 100) / 100.0, "#.##") + " G/bar", xloc=xloc.bar_index, yloc=yloc.price, style=label.style_label_left, color=color.orange, textcolor=color.black, size=size.small)
        array.push(drawnLabels, unsafe)
    else
        {'renderProfile(odteLevels, odteValues, bar_index + offsetOdte, "0DTE '+first+'", actualScale)' if odte["rows"] else '// 0DTE non incluso in questa esportazione'}
        {'renderProfile(weeklyLevels, weeklyValues, bar_index + offsetWeekly, "Weekly '+second+'", actualScale)' if weekly["rows"] else '// Weekly non incluso in questa esportazione'}
'''
