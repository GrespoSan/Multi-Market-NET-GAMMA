"""Pine v6 visualization only: gamma is already calculated in Python.

Generates either single 0DTE, single Weekly, or side-by-side profiles.
No future/live Cboe data is read by Pine. 500-future-bar constraints are checked.
"""
import math
from datetime import date


def _numbers(rows, key, offset=0.0):
    return ', '.join(format(float(row[key]) + offset, '.6f') for row in rows)


def _safe_scale(profiles):
    minimum = 0.01
    for profile, center in profiles:
        pos = max((max(0, float(r['net_gamma'])) for r in profile['rows']), default=0)
        neg = max((max(0,-float(r['net_gamma'])) for r in profile['rows']), default=0)
        minimum=max(minimum,pos/max(1,480-center),neg/(9500+center))
    # Rounded up for safety; no net_gamma value is changed.
    return math.ceil(minimum*100 - 1e-9)/100.0


def make_pine(profiles: dict, basis: float, target: date, label: str) -> str:
    if not profiles:
        raise ValueError('Nessun profilo da esportare')
    if not math.isfinite(basis):
        raise ValueError('Differenziale NQ-NDX non valido')
    positions = {'0DTE':75, 'Weekly':260} if len(profiles)==2 else {next(iter(profiles)):90}
    draw = [(profiles[k],positions[k]) for k in profiles]
    for p,_ in draw:
        if len(p['rows']) !=50:
            raise ValueError('Esportazione bloccata: ogni profilo deve contenere 50 strike')
    scale=_safe_scale(draw)
    lines=[
        '//@version=6',
        f'indicator("Multi-Market NET GAMMA · NDX/NQ · {label} · {target.isoformat()}", overlay=true, max_lines_count=350, max_labels_count=30)',
        f'// NDX/NQ · Snapshot {label}; prezzi = strike NDX + basis {basis:.4f}',
        '// Formula sperimentale NDX: Call (OI+Volume)*Gamma - Put (OI+Volume)*Gamma.',
        '// Questi sono dati statici esportati, NON un feed Pine automatico.',
        f'gammaPerBar = input.float({scale:.2f}, "Scala GAMMA manuale", minval=0.01, step=0.01)',
        'showTitles = input.bool(true, "Mostra titoli")',
        'var array<line> allLines = array.new_line()',
        'var array<label> allLabels = array.new_label()',
    ]
    for kind,p in profiles.items():
        lines += [
            f'var array<float> levels{kind} = array.from({_numbers(p["rows"],"strike_index",basis)})',
            f'var array<float> values{kind} = array.from({_numbers(p["rows"],"net_gamma")})',
        ]
    lines += [
        'drawGroup(array<float> levels, array<float> gamma, int xcenter, string name) =>',
        '    float top = array.max(levels)',
        '    float bottom = array.min(levels)',
        '    float room = math.max((top - bottom) * 0.075, syminfo.mintick * 20)',
        '    float required = 0.01',
        '    for g in gamma',
        '        required := math.max(required, g > 0 ? g / (480.0 - xcenter) : -g / (9500.0 + xcenter))',
        '    if showTitles',
        '        label title = label.new(bar_index + xcenter, top + room, name, xloc=xloc.bar_index, style=label.style_label_down, color=color.new(color.gray, 25), textcolor=color.white, size=size.normal)',
        '        array.push(allLabels, title)',
        '    if gammaPerBar >= required',
        '        for j=0 to array.size(levels)-1',
        '            float price = array.get(levels,j)',
        '            float g = array.get(gamma,j)',
        '            int targetX = bar_index + xcenter + int(math.round(g/gammaPerBar))',
        '            line ln = line.new(bar_index+xcenter, price, targetX, price, xloc=xloc.bar_index, color=g>=0?color.lime:color.red, width=3)',
        '            array.push(allLines,ln)',
        '    else',
        '        label warn = label.new(bar_index+xcenter, top+2*room, "Scala ottimale " + str.tostring(math.ceil(required*100)/100.0, "#.##"), xloc=xloc.bar_index, style=label.style_label_down, color=color.orange, textcolor=color.black, size=size.normal)',
        '        array.push(allLabels,warn)',
        'if barstate.islast',
        '    for ln in allLines',
        '        line.delete(ln)',
        '    array.clear(allLines)',
        '    for lb in allLabels',
        '        label.delete(lb)',
        '    array.clear(allLabels)',
    ]
    for kind, _ in profiles.items():
        title = ('0DTE ' if kind=='0DTE' else 'Weekly ') + label.replace('"', '')
        lines.append(f'    drawGroup(levels{kind}, values{kind}, {positions[kind]}, "{title}")')
    return '\n'.join(lines)+'\n'
