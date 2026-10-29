"""Pine v6 per NDX/NQ: stessa interfaccia dei Pine Serafini SPX.
Solo disegno dei NET GAMMA gia' calcolati. Ticker consentiti: NQ e MNQ.
"""
from math import ceil, floor, isfinite, log10
from datetime import date
from pine_spx_visual import spx_inputs, SPX_RENDER_FUNCTIONS, spx_last_bar


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
    """Suggerisce la scala di PRESENTAZIONE dal Gamma realmente esportato.

    A differenza di SPX, Gamma NDX puo' essere molto inferiore a 1:
    imporre 1 Gamma/barra comprime tutte le barre in una linea.
    Il suggerimento e' calcolato SOLO in esportazione e resta un input
    manuale in TradingView; nessun Gamma viene riscalato o normalizzato.
    """
    peaks = {}
    for group, center in profiles:
        values = [float(row["net_gamma"]) for row in group["rows"]]
        if not values:
            continue
        positive = max(0.0, max(values))
        negative = max(0.0, -min(values))
        peaks[center] = (positive, negative)
    if not peaks:
        return (0.001, 0.0001)

    # Profili leggibili, senza barre positive e negative sovrapposte
    # tra le colonne (centri 60 e 160 barre dall'ultima candela).
    needed = 0.000001
    for center, (positive, negative) in peaks.items():
        needed = max(needed, positive / 110.0)
        needed = max(needed, negative / (45.0 if center == 60 else 80.0))
    if 60 in peaks and 160 in peaks:
        # Coda positiva 0DTE + coda negativa Weekly: massimo 85 barre.
        needed = max(needed, (peaks[60][0] + peaks[160][1]) / 85.0)

    # Circa due cifre significative: es. 0.00437 -> 0.0044.
    magnitude = floor(log10(needed))
    unit = 10.0 ** max(-8, magnitude - 1)
    initial = ceil(needed / unit - 1e-9) * unit
    initial = round(max(initial, 0.000001), 8)
    return initial, round(unit, 8)



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
    scale, scale_step=_initial_manual_scale([(odte,60),(weekly,160)])
    scale_text=f"{scale:.8f}".rstrip("0").rstrip(".")
    scale_step_text=f"{scale_step:.8f}".rstrip("0").rstrip(".")
    first=date.fromisoformat(odte["expiry"]).strftime("%d/%m") if odte["rows"] else ""
    second=date.fromisoformat(weekly["expiry"]).strftime("%d/%m") if weekly["rows"] else ""
    band=next(iter(profiles.values())).get("band_pct",3.0)
    inputs = spx_inputs(scale_text, scale_step_text, "0DTE",
        "Valore iniziale scelto dalla fotografia NDX per rendere visibili i profili. "
        "Scala sempre MANUALE; NET GAMMA invariato.")
    graphics = SPX_RENDER_FUNCTIONS
    main_call = (f'renderProfile(odteLevels, odteValues, bar_index + offsetOdte, '
                 f'"0DTE {first}", actualScale)' if odte["rows"] else "")
    weekly_call = (f'renderProfile(weeklyLevels, weeklyValues, bar_index + offsetWeekly, '
                   f'"Weekly {second}", actualScale)' if weekly["rows"] else "")
    draw = spx_last_bar(main_call, weekly_call, "odteValues", "weeklyValues")
    return f'''//@version=6
indicator("Multi-Market NET GAMMA · NDX/NQ · {target.isoformat()} · {label}", overlay=true, max_lines_count=500, max_labels_count=35)
// Visualizzazione statica dei NET GAMMA calcolati dall'app, mai in Pine.
// Valido esclusivamente per i futures NQ / MNQ; altri strumenti: nessun disegno.
// Fascia di selezione: +/-{band:g}% dal close NDX precedente.
// Differenziale NQ–NDX gia' applicato agli strike: {basis:.4f}
// Formula INVARIATA: Call (OI+Volume)*Gamma - Put (OI+Volume)*Gamma.
// Stessa interfaccia del generatore Serafini SPX.
validTicker = syminfo.type == "futures" and (syminfo.root == "NQ" or syminfo.root == "MNQ")

{inputs}

var array<line> drawnLines = array.new_line()
var array<label> drawnLabels = array.new_label()
var array<float> odteLevels = {_pine_array(odte["rows"],"strike_index",basis)}
var array<float> odteValues = {_pine_array(odte["rows"],"net_gamma")}
var array<float> weeklyLevels = {_pine_array(weekly["rows"],"strike_index",basis)}
var array<float> weeklyValues = {_pine_array(weekly["rows"],"net_gamma")}

{graphics}

{draw}
'''
