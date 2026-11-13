"""Offline sidebar refresh regression: BOTH authorized roles retain login.

No network, credentials, Supabase, Cboe or Massive are used.
"""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from v2_refresh import refresh_multimarket_data

ROOT = Path(__file__).resolve().parents[1]
CACHES = {
    "v2_storage_off": ("_cached_artifacts",),
    "v2_spx_bridge": ("_official_captures", "_cached_verified_official_feed"),
    "v2_context": ("_artifact_registers",),
    "macro_calendar": ("load_calendar",),
    "v2_volatility": ("fetch_daily", "fetch_massive_futures",
                      "fetch_market_curve"),
}


class MultiMarketSidebarRefreshTests(unittest.TestCase):
    def test_refresh_invalidates_short_lived_sources_not_auth(self):
        modules, clear_calls = {}, []
        for name, attrs in CACHES.items():
            module = types.ModuleType(name)
            for attr in attrs:
                clear = Mock()
                setattr(module, attr, types.SimpleNamespace(clear=clear))
                clear_calls.append(clear)
            modules[name] = module

        for role in ("admin", "friend"):
            for clear in clear_calls:
                clear.reset_mock()
            session = {
                "v2_role": role,
                "v2_login_id": "existing-private-login",
                "v2_market_selected": "NASDAQ",
                "v2_archive_choice_ndx": "manuale",
                "ndx_blob": b"unchanged-user-chain",
                "ndx_basis_value": "300.25",
                "mm_unified_day": "2026-11-13",
                "mm_unified_view_slot_2026-11-13": "1700",
                "mm_unified_prepared_by_slot_gex_source_v2": {
                    ("2026-11-13", "1700"): {"script": "STATIC OLD PINE"}},
            }
            with self.subTest(role=role), patch.dict(sys.modules, modules):
                refresh_multimarket_data(session)
                for clear in clear_calls:
                    clear.assert_called_once_with()
                self.assertEqual(session["v2_role"], role)
                self.assertEqual(session["v2_login_id"], "existing-private-login")
                self.assertEqual(session["v2_archive_choice_ndx"], "manuale")
                self.assertEqual(session["ndx_blob"], b"unchanged-user-chain")
                self.assertEqual(session["ndx_basis_value"], "300.25")
                self.assertEqual(session["mm_unified_day"], "2026-11-13")
                self.assertEqual(session["mm_unified_view_slot_2026-11-13"], "1700")
                self.assertNotIn("mm_unified_prepared_by_slot_gex_source_v2", session)

    def test_sidebar_is_shared_after_login_and_before_logout(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        start = source.index('role = st.session_state["v2_role"]\nwith st.sidebar:')
        end = source.index('st.caption("V2 indipendente', start)
        sidebar = source[start:end]
        self.assertIn('st.button("🔄 Aggiorna dati"', sidebar)
        self.assertIn('refresh_multimarket_data(st.session_state)', sidebar)
        self.assertLess(sidebar.index('Aggiorna dati'), sidebar.index('st.button("Esci"'))
        self.assertNotIn('if role == "admin":', sidebar)
        self.assertNotIn('st.session_state.clear()', sidebar)
        self.assertNotIn('st.cache_data.clear()', sidebar)
        self.assertNotIn('st.rerun()', sidebar.split('if st.button("Esci"')[0])

    def test_targeted_refresh_does_not_touch_immutable_raw_or_cboe(self):
        source = (ROOT / "v2_refresh.py").read_text(encoding="utf-8")
        self.assertNotIn("st.cache_data.clear()", source)
        self.assertNotIn("_cached_snapshot.clear()", source)
        self.assertNotIn("_cl_cached_json.cache_clear()", source)
        self.assertNotIn("login_limiter.clear()", source)
        self.assertNotIn('session_state.pop("v2_role"', source)
        self.assertNotIn("download_once", source)


if __name__ == "__main__":
    unittest.main()
