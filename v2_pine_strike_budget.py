"""Bound the *three-column* Pine drawing without changing original Cboe Gamma.

TradingView imposes 500 line objects per script. Each rendered nonzero
strike consumes one line, and each of the three columns uses one baseline.
Only when the three actual Cboe profiles together exceed the safe 480-line
budget, select up to 140 authentic strike rows per profile. Preserve the
strongest positive and negative exposure, nearby prices and range coverage.
Never interpolate, aggregate, rescale, change the saved source profiles, or
silently drop any level: the comparison export records all selection counts.
"""
from math import isfinite

TOTAL_SAFE = 480
PER_COLUMN = 140


def _value(row, field):
    number = float(row[field])
    if not isfinite(number):
        raise ValueError("Gamma/strike non finito nel profilo Pine.")
    return number


def _center(profile, strike_field, symbol):
    if symbol == "NDX":
        val = profile.get("reference")
    else:
        low, high = profile.get("lower"), profile.get("upper")
        val = ((float(low) + float(high)) / 2
               if low is not None and high is not None else None)
    if val is not None:
        try:
            f = float(val)
            if isfinite(f) and f > 0:
                return f
        except (ValueError, TypeError):
            pass
    levels = sorted(_value(r, strike_field) for r in profile["rows"])
    return levels[len(levels) // 2]


def _selected_rows(profile, symbol, budget):
    strike_field, gamma_field = (
        ("strike_index", "net_gamma") if symbol == "NDX"
        else ("strike", "net"))
    rows = profile["rows"]
    if len(rows) <= budget:
        return list(rows)
    levels = [_value(r, strike_field) for r in rows]
    gammas = [_value(r, gamma_field) for r in rows]
    if len(set(levels)) != len(levels) or min(levels) <= 0:
        raise ValueError("Strike Cboe duplicati/non validi.")
    center = _center(profile, strike_field, symbol)
    chosen = set()

    def take(indices, max_added):
        count = 0
        for i in indices:
            if len(chosen) >= budget or count >= max_added:
                return
            if i not in chosen:
                chosen.add(i)
                count += 1

    # Anchor both tails and the strongest positive and negative real NET Gamma.
    by_level = sorted(range(len(rows)), key=lambda i: levels[i])
    strongest_plus = max(range(len(rows)), key=lambda i: (gammas[i], -abs(levels[i] - center)))
    strongest_minus = min(range(len(rows)), key=lambda i: (gammas[i], abs(levels[i] - center)))
    chosen.update((by_level[0], by_level[-1], strongest_plus, strongest_minus))

    # Highest actual Gamma concentrations, without replacing them by averages.
    by_strength = sorted(range(len(rows)), key=lambda i: (
        -abs(gammas[i]), abs(levels[i] - center), levels[i]))
    take(by_strength, budget * 4 // 10)
    # Price-nearest original strikes, to keep the operative area readable.
    by_distance = sorted(range(len(rows)), key=lambda i: (
        abs(levels[i] - center), -abs(gammas[i]), levels[i]))
    take(by_distance, budget * 4 // 10)
    # Evenly sample the full source price range; all are original rows.
    coverage = []
    coverage_count = max(1, budget // 5)
    for j in range(coverage_count):
        rank = round(j * (len(rows) - 1) / max(1, coverage_count - 1))
        coverage.append(by_level[rank])
    take(coverage, budget)
    # Use every remaining slot, preferring genuine large Gamma exposures.
    take(by_strength, budget)
    result = [rows[i] for i in sorted(chosen, key=lambda i: levels[i])]
    if len(result) != budget:
        raise ValueError("Numero strike Pine selezionati incoerente.")
    return result


def prepare_comparison_profiles(symbol, previous, current, weekly):
    """Return original profiles unless 3-way line budget is exceeded.

    On reduction, never mutate the input or recalculate values. Report the
    exact per-column counts, so the UI and Pine disclose reduced coverage.
    """
    profiles = [previous, current, weekly]
    sizes = [len(p["rows"]) for p in profiles]
    for n in sizes:
        if n == 0:
            raise ValueError("Profilo Gamma senza strike.")
    if sum(sizes) <= TOTAL_SAFE:
        return profiles, None
    converted = []
    rendered = []
    for p in profiles:
        new = dict(p)
        new["rows"] = _selected_rows(p, symbol, PER_COLUMN)
        converted.append(new)
        rendered.append(len(new["rows"]))
    if sum(rendered) > TOTAL_SAFE:
        raise ValueError("Pine: selezione livelli oltre limite TradingView.")
    return converted, {"original": sizes, "rendered": rendered,
                       "omitted": [a - b for a, b in zip(sizes, rendered)]}
