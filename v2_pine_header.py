"""Validate and normalize generated TradingView Pine v6 declaration.

The final Pine output must contain exactly one actual indicator() line and
the directive must be first; avoid sending partial scripts to the editor.
Do not invent indicator titles or change the source arrays and Gamma.
"""


def normalize_indicator_header(script):
    if not isinstance(script, str):
        raise ValueError("Pine: esportazione non testuale.")
    lines = script.splitlines(keepends=True)
    if not lines or lines[0].strip() != "//@version=6":
        raise ValueError("Pine: la direttiva //@version=6 deve essere la prima riga.")
    candidates = [
        i for i, line in enumerate(lines)
        if line.startswith("indicator(")
    ]
    if len(candidates) != 1:
        raise ValueError(
            "Pine: dichiarazione indicator(...) mancante o duplicata; "
            "esportazione bloccata.")
    index = candidates[0]
    line = lines[index]
    if not line.rstrip().endswith(")"):
        raise ValueError("Pine: dichiarazione indicator(...) incompleta.")
    # Physically move the already validated declaration immediately after
    # //@version=6, before all comparison notes and data arrays.
    declaration = lines.pop(index)
    lines.insert(1, declaration)
    result = "".join(lines)
    if not result.splitlines()[1].startswith("indicator("):
        raise ValueError("Pine: intestazione non corretta.")
    return result
