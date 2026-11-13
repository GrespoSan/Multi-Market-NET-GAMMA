"""User-triggered refresh of read-only Multi-Market data, without logging out.

Clear ONLY time-sensitive caches, not global Streamlit cache, security
resources, verified immutable raw Cboe snapshots, manually imported chains,
session-frozen ES/NQ basis, or Massive CL throttling/cooldown state.
Streamlit's button automatically reruns the page; no extra st.rerun needed.
"""


def refresh_multimarket_data(session_state):
    """Refresh latest archived acquisitions and optional market context.

    Authentication is maintained by app.py in v2_role; this helper must
    never read or mutate it. Explicitly drop only completed Pine exports,
    because they embed *static* verified snapshots and would otherwise mask
    newly available acquisitions even after refreshing their source cache.
    """
    from v2_storage_off import _cached_artifacts
    from v2_spx_bridge import (
        _official_captures, _cached_verified_official_feed,
    )
    from v2_context import _artifact_registers
    from macro_calendar import load_calendar
    from v2_volatility import (
        fetch_daily, fetch_massive_futures, fetch_market_curve,
    )

    for cache in (
        _cached_artifacts,             # New GitHub snapshots of 5 main markets
        _official_captures,           # New official SPX slots for ES/MES
        _cached_verified_official_feed,  # Latest independently validated GEX CSV
        _artifact_registers,          # News/context archive index
        load_calendar,                # Macro calendar updates, if activated
        fetch_daily,                  # Yahoo daily and volatility closed bars
        fetch_massive_futures,        # Massive closed futures sessions
        fetch_market_curve,          # Verified forward structure, if activated
    ):
        cache.clear()

    # Regenerate the three user-visible unified Pine downloads on next render.
    # The session key is application-owned, NOT user input/authentication.
    session_state.pop("mm_unified_prepared_by_slot_chicago_1616_1746_v3", None)
