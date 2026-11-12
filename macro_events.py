"""Fonte unica per le news opzionali nei Pine Multi-Market.

Riutilizza il calendario macro USA gratuito comune alla dashboard (BLS, BEA,
Census, Fed, ISM e FRED/DOL). Nessuna API key, nessuna chiamata FinanceCalendar.
Non modifica NET GAMMA e non deduce eventi da date non confermate.
"""
import re
from macro_calendar import load_calendar

def events_for_pine(day):
    """Eventi del giorno con orario Europe/Rome verificabile; nessuna stima."""
    news, _health = load_calendar(day, day)
    return [
        event for event in news
        if event.get("day") == day
        and re.fullmatch(r"[0-9]{2}:[0-9]{2}", str(event.get("clock", "")))
        and event.get("status") != "cancelled"
    ]
