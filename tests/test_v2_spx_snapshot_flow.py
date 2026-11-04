"""SPX-like NET GAMMA snapshot selection without a Supabase dependency.

All fixtures are synthetic. Never calls Cboe or external APIs.
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v2_storage_off import _archive_label, SLOTS, AVAILABLE_MARKETS
from gamma_chart_style import capture_display

ROOT = Path(__file__).resolve().parent.parent


class SPXSnapshotParityTests(unittest.TestCase):
    def test_display_provenance_is_real_created_at_converted_to_rome(self):
        item={"name":"v2-multi-market-42","created_at":"2026-10-30T13:55:00Z"}
        label=_archive_label(item)
        self.assertIn("30/10/2026 · 14:55 Roma", label)
        self.assertIn("v2-multi-market-42", label)
        self.assertEqual(SLOTS["0730"],"Mattina 07:30 Roma")
        self.assertEqual(SLOTS["1550"],"Pomeriggio 08:50 Chicago")
        self.assertEqual(SLOTS["2030"],"Sera 13:30 Chicago")
        self.assertEqual(AVAILABLE_MARKETS,("NDX","GLD","USO"))

    def test_same_archive_selector_and_manual_override_for_all_markets(self):
        accessor=(ROOT/"v2_storage_off.py").read_text(encoding="utf-8")
        self.assertIn('"Snapshot originale Cboe"', accessor)
        self.assertIn("manca nei Secrets Streamlit:", accessor)
        self.assertIn('"V2_GITHUB_TOKEN"', accessor)
        self.assertNotIn('with st.expander("RILEVAMENTI PROGRAMMATI', accessor)
        self.assertIn('st.session_state[choice_key] = "ultimo" if artifacts else "manuale"', accessor)
        self.assertIn('for item in artifacts[:12]:', accessor)
        self.assertIn('packed, filename = _cached_snapshot(', accessor)
        self.assertIn('if packed is None:', accessor)
        self.assertIn("def prefer_manual_source(symbol):", accessor)
        self.assertIn("if chosen == \"manuale\":", accessor)
        self.assertIn("fetch_artifact_snapshot", accessor)
        self.assertIn("v2_archive_capture_nyday_", accessor)
        self.assertNotIn("st.session_state.get(\"v2_role\") != \"admin\"",accessor)
        self.assertNotIn("from storage import Store",accessor)
        for file,symbol in (
            ("v2_market_engine.py","NDX"),
            ("gld_cboe_view.py","GLD"),
            ("uso_cboe_view.py","USO")):
            source=(ROOT/file).read_text()
            with self.subTest(symbol=symbol):
                self.assertIn(f"prefer_manual_source('{symbol}')" if symbol=="NDX"
                              else f'prefer_manual_source("{symbol}")',source)
                self.assertIn("archive_panel",source)
                self.assertIn("v2_archive_capture_nyday_",source)
                self.assertIn("v2_archive_capture_rome_",source)
                self.assertIn("independent_scale",source)
        for file in ("v2_market_engine.py", "gld_cboe_view.py", "uso_cboe_view.py"):
            source=(ROOT/file).read_text()
            self.assertIn("snapshot_placement = st.container()", source)
            shared_label = 'with st.expander("Acquisizione Cboe / importazione manuale'
            self.assertIn(shared_label, source)
            self.assertIn("condivisa con Pine di emergenza", source)
            self.assertIn("with snapshot_placement:", source)
            self.assertLess(source.index("snapshot_placement = st.container()"),
                            source.index(shared_label))
        ui=(ROOT/"market_ui.py").read_text()
        self.assertIn("show_header=False", (ROOT/"v2_market_engine.py").read_text())
        self.assertIn("show_header=True", ui)
        header=(ROOT/"app.py").read_text()
        self.assertIn('st.header("NET GAMMA · formula Serafini")',header)
        self.assertIn("60%/23%",header)
        self.assertNotIn("from storage import",header)

    def test_ndx_archive_provenance_preserved_in_both_plot_titles(self):
        source=(ROOT/"v2_market_engine.py").read_text(encoding="utf-8")
        self.assertIn("st.session_state['ndx_source']='Archivio privato · rilevamento programmato'", source)
        self.assertIn("st.session_state['ndx_source']='Acquisizione diretta su richiesta'", source)
        self.assertIn("st.session_state['ndx_source']='Importazione manuale'", source)
        self.assertEqual(source.count("st.session_state.get('ndx_source', st.session_state.get('ndx_name', ''))"), 2)
        date_text, descriptor = capture_display(
            "2026-11-02 06:27:15", "2026-11-02T07:31:08+01:00",
            "Archivio privato · rilevamento programmato")
        self.assertEqual(date_text, "02/11/2026")
        self.assertIn("Archivio · download ore 07:31 Roma", descriptor)
        self.assertNotIn("manuale", descriptor.lower())

    def test_pine_macro_diagnostic_is_collapsed_and_never_blocks_export(self):
        source=(ROOT/"v2_market_engine.py").read_text(encoding="utf-8")
        self.assertIn("with st.expander('Dettaglio news macro opzionali nei Pine', expanded=False):", source)
        self.assertNotIn("st.warning('Calendario macro USA temporaneamente non disponibile:", source)
        self.assertIn("macro_news=events_for_pine(day)", source)
        self.assertIn("macro_news=events_for_pine(day)", source)
        self.assertIn("render_timed_pine_exports(", source)
        self.assertIn("extension=show_extension, macro_news=macro_news", source)
        timed = (ROOT/"v2_pine_timed_exports.py").read_text(encoding="utf-8")
        self.assertIn("if macro_news and symbol == \"NDX\":", timed)
        self.assertIn("script = append_news(script, macro_news)", timed)
        self.assertIn("st.download_button(", timed)
        self.assertIn("07:30 0DTE → 15:50 0DTE + Weekly", timed)

    def test_scheduler_retains_chicago_dst_and_authorized_source_gate(self):
        from v2_schedule import SLOTS as clock
        import v2_cron
        self.assertEqual(clock["07:30"][0],"Europe/Rome")
        self.assertEqual(clock["15:50"][0],"America/Chicago")
        self.assertEqual(clock["20:30"][0],"America/Chicago")
        self.assertIn("V2_AUTHORIZED_FEED_CONFIRMED",Path(v2_cron.__file__).read_text())
        self.assertIn("V2_FEED_TOKEN",Path(v2_cron.__file__).read_text())
        self.assertIn("V2_ARCHIVE_FERNET_KEY",Path(v2_cron.__file__).read_text())
        self.assertIn("delayed_quotes",Path(v2_cron.__file__).read_text())

if __name__=="__main__":
    unittest.main()
