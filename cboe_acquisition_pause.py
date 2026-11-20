"""Sospensione temporanea Cboe dal 20 novembre 2026, inclusa V1 storica."""
CBOE_ACQUISITIONS_PAUSED = True
PAUSE_MESSAGE = ("Download Cboe sospesi. Sono disponibili solo archivi e importazioni locali.")

def require_cboe_acquisition_enabled():
    if CBOE_ACQUISITIONS_PAUSED:
        raise RuntimeError(PAUSE_MESSAGE)
