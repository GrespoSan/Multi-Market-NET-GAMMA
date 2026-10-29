"""Shared TradingView Pine v6 VISUAL standard, taken from Serafini SPX export.

Only the presentation layer is shared: manual common Gamma/bar scale,
60/160-bar 0DTE/Weekly placement, colors, dotted vertical baselines,
5px Gamma segments, headings, ticker guard and TradingView line-limit check.
Market data, contract selection and price transformations stay separate.

Reference: GrespoSan/Serafini-SPX-Dashboard/pine_export.py (V53-TV-MANUAL-SCALE).
"""
from textwrap import indent


def spx_inputs(scale: str, scale_step: str, primary_label: str = "0DTE",
               tooltip: str = "") -> str:
    """The same visual controls and defaults for NDX, GLD and USO."""
    tooltip = tooltip or (
        "Scala grafica MANUALE e comune a entrambi i profili. "
        "Nessuna modifica ai NET GAMMA originali.")
    tooltip = tooltip.replace('"', "'").replace("\n", " ")
    return f'''gammaPerCandle = input.float({scale}, "Scala MANUALE · Gamma/barra", minval=0.000001, step={scale_step}, tooltip="{tooltip}")
offsetOdte = input.int(60, "Distanza {primary_label} da ultima candela", minval=45, maxval=170)
offsetWeekly = input.int(160, "Distanza Weekly da ultima candela", minval=55, maxval=300)
positiveColor = input.color(color.rgb(0, 230, 117), "NET GAMMA positivo")
negativeColor = input.color(color.rgb(242, 54, 69), "NET GAMMA negativo")
showTitles = input.bool(true, "Mostra intestazioni")'''


# Identical chart geometry to the SPX template: xloc.bar_index, one manual
# Gamma/bar for both groups, green/right and red/left, dotted baseline,
# 5-pixel horizontal segments, heading above profile. No status/disclaimer
# text is drawn over live candles.
SPX_RENDER_FUNCTIONS = """requiredScale(array<float> gamma, int offsetBars) =>
    float maxPos = 0.0
    float maxNeg = 0.0
    for g in gamma
        maxPos := math.max(maxPos, g)
        maxNeg := math.max(maxNeg, -g)
    float rightCapacity = float(480 - offsetBars)
    float leftCapacity = float(9500 + offsetBars)
    math.max(maxPos / rightCapacity, maxNeg / leftCapacity)

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
            array.push(drawnLabels, t)"""


def spx_last_bar(main_call: str, weekly_call: str, main_values: str,
                 weekly_values: str, prepare: str = "") -> str:
    """Draw SPX-style overlays on the last bar, with only error labels.

    'prepare' can map ETF strikes onto future y-coordinates before rendering.
    It never changes Gamma arrays and is run only when the ticker is valid.
    """
    prefix = (indent(prepare.strip(), "    ") + "\n") if prepare.strip() else ""
    main = main_call if main_call else "// Profilo principale assente"
    weekly = weekly_call if weekly_call else "// Profilo Weekly assente"
    return f'''if barstate.islast and validTicker
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
{prefix}    float actualScale = gammaPerCandle
    float minimumSafe = math.max(requiredScale({main_values}, offsetOdte), requiredScale({weekly_values}, offsetWeekly))
    if actualScale < minimumSafe * 0.999999
        label unsafe = label.new(bar_index + 10, close, "Scala manuale troppo piccola. Imposta almeno " + str.tostring(minimumSafe, "#.########") + " G/bar", xloc=xloc.bar_index, yloc=yloc.price, style=label.style_label_left, color=color.orange, textcolor=color.black, size=size.small)
        array.push(drawnLabels, unsafe)
    else
        {main}
        {weekly}'''
