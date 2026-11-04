"""Cboe GLD module: one-click snapshot, with manual JSON fallback.
No Alpaca, scheduled polling, or conversion to CME GC strikes.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo
import csv
import hashlib
import io

import streamlit as st
from gamma_chart_style import profile_chart, panel_heading, capture_display, spx_shared_gamma_bounds
from v2_visual_extension import expanded_display

from etf_pine_view import render_etf_pine_exports
from v2_continuous_ratio import load_chart_continuous_mapping
from etf_gamma_axes import chart_price_axes
from v2_storage_off import archive_panel, prefer_manual_source
from market_ui import render_empty_snapshot

from gld_cboe import (GLD_URL, download_gld, read_gld, expirations, next_weekly,
                      close_previous, current_price, profile, MIN_VALID_COVERAGE)


def _to_csv(rows):
    keys = ["strike", "net", "call", "put", "call_gamma", "put_gamma",
            "call_oi", "put_oi", "call_volume", "put_volume"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()
    writer.writerows(({key: row.get(key, "") for key in keys} for row in rows))
    return output.getvalue().encode("utf-8-sig")


def _plot(p, reference, common_x, shared_y, *, price_ratio=1.0,
          projected=False, title="0DTE", snapshot_label="", tick_levels=None):
    # Native ETF fallback is not a projected GC price: label it as GLD.
    return profile_chart(
        p["rows"], "GLD", reference, common_x, shared_y,
        price_scale=price_ratio,
        axis_symbol="GC" if projected else None,
        close_label="Close prec. proiettato" if projected else "Close prec. GLD",
        title=title, snapshot_label=snapshot_label, tick_levels=tick_levels)


def _save_snapshot(raw, filename, source):
    """Validate before replacing the previous good snapshot."""
    doc = read_gld(raw)
    dates = expirations(doc)
    if not dates:
        raise ValueError("Nessuna scadenza GLD riconosciuta.")
    digest = hashlib.sha256(raw).hexdigest()
    prior = st.session_state.get("gld_cboe_sha256")
    st.session_state["gld_cboe_raw"] = raw
    st.session_state["gld_cboe_file"] = filename
    st.session_state["gld_cboe_sha256"] = digest
    st.session_state["gld_cboe_source"] = source
    st.session_state["gld_cboe_import_rome"] = datetime.now(
        ZoneInfo("Europe/Rome")).isoformat(timespec="seconds")
    if prior != digest:
        # New chain: discard manual previous-close override from older source.
        previous = close_previous(doc)
        st.session_state["gld_cboe_reference"] = (
            f"{previous:.4f}" if previous is not None else "")
        st.session_state.pop("gld_cboe_day", None)
    return prior != digest


def render_gld_cboe():
    st.subheader("Fotografia opzioni Cboe · GLD")
    st.caption("La stessa fotografia alimenta anche il Pine di emergenza in fondo alla pagina.")
    snapshot_placement = st.container()
    # Unico download/importazione manuale nel pannello emergenza in fondo pagina.
    # Qui rimane il selettore delle fotografie archiviate, non un secondo upload.
    st.caption("Per download manuale Cboe o importazione ZIP/JSON, usa "
               "PINE DI EMERGENZA — NET GAMMA CORRENTE in fondo alla pagina.")
    with snapshot_placement:
        archive_selected = archive_panel("GLD")
        if archive_selected is not None:
            original_raw, stored_name = archive_selected
            try:
                _save_snapshot(original_raw, stored_name,
                               "Archivio privato · rilevamento programmato")
                st.session_state["gld_cboe_import_rome"] = (
                    st.session_state.get("v2_archive_capture_rome_GLD")
                    or st.session_state["gld_cboe_import_rome"])
                st.success("Fotografia programmata caricata dall'archivio privato.")
            except Exception as exc:
                st.error(f"Fotografia archivio non valida: {str(exc)[:240]}")

    raw = st.session_state.get("gld_cboe_raw")
    if not raw:
        render_empty_snapshot("GLD")
        return
    try:
        data = read_gld(raw)
        available = expirations(data)
    except Exception as exc:
        st.error(f"File GLD non valido: {str(exc)[:260]}")
        return

    stamp = data.get("timestamp")
    st.caption(f"**Fonte:** {st.session_state.get('gld_cboe_source', 'GLD.json')} · "
               f"**Acquisizione (Roma):** {st.session_state.get('gld_cboe_import_rome', 'non verificata')} · "
               f"**Timestamp originale Cboe:** {stamp if stamp else 'non disponibile'}")
    if not stamp:
        st.warning("Il file non contiene un timestamp Cboe verificabile. "
                   "La data d'importazione non certifica la freschezza del mercato.")

    ny_today = datetime.now(ZoneInfo("America/New_York")).date()
    archive_day = (
        st.session_state.get("v2_archive_capture_nyday_GLD")
        if st.session_state.get("v2_archive_choice_gld") != "manuale"
        else None)
    acquisition_day = archive_day or ny_today
    future = [d for d in available if d >= acquisition_day]
    first = (acquisition_day if acquisition_day in available
             else future[0] if future else available[-1])
    base_day = st.selectbox(
        "Scadenza 0DTE della fotografia selezionata (ora New York)",
        available, index=available.index(first),
        format_func=lambda d: d.strftime("%d/%m/%Y"), key="gld_cboe_day")
    is_0dte = base_day == acquisition_day
    if not is_0dte:
        st.warning(f"La scadenza {base_day:%d/%m/%Y} NON coincide con "
                   f"la data della fotografia {acquisition_day:%d/%m/%Y}: "
                   "profilo di altra scadenza, NON 0DTE del rilevamento.")
    elif acquisition_day != ny_today:
        st.caption(f"0DTE STORICO · fotografia del {acquisition_day:%d/%m/%Y} "
                   "a New York. Non è una catena 0DTE corrente.")
    weekly = next_weekly(base_day, available)
    if weekly is None:
        st.info("Il prossimo venerdì successivo alla scadenza principale "
                "non è presente nel file: Weekly non disponibile.")
    st.caption("Weekly: " + (weekly.strftime("%d/%m/%Y") if weekly else "non disponibile") +
               " (solo venerdì effettivamente presente nella catena Cboe).")

    auto_ref = close_previous(data)
    if auto_ref is None:
        st.warning("Chiusura precedente assente nel JSON; inserisci un riferimento GLD verificato.")
    if "gld_cboe_reference" not in st.session_state:
        st.session_state["gld_cboe_reference"] = (
            f"{auto_ref:.4f}" if auto_ref is not None else "")
    reference_text = st.text_input(
        "Chiusura GLD della seduta precedente (USD)",
        key="gld_cboe_reference")
    try:
        reference = float(reference_text.replace(",", "."))
        if not (0 < reference < 100_000):
            raise ValueError()
    except (TypeError, ValueError):
        st.error("Serve una chiusura GLD precedente valida.")
        return

    band = st.number_input("Fascia strike ± % dal close GLD precedente",
                           min_value=0.5, max_value=10.0, value=3.0,
                           step=0.5, key="gld_cboe_band")
    price = current_price(data)
    if price is not None:
        st.caption(f"Prezzo GLD nel file: {price:,.2f} USD · "
                   f"Chiusura precedente: {reference:,.2f} USD · "
                   f"Fascia strike ±{band:g}%.")
    else:
        st.caption(f"Chiusura precedente: {reference:,.2f} USD · fascia strike ±{band:g}%.")

    groups = {}
    keys = [("0DTE" if is_0dte else "Principale", base_day)]
    if weekly:
        keys.append(("Weekly", weekly))
    for title, expiry in keys:
        try:
            groups[title] = profile(data, expiry, reference, band_pct=band)
        except Exception as exc:
            st.error(f"{title}: {str(exc)[:260]}")
    if not groups:
        return

    show_extension = st.checkbox(
        "Estensione automatica NET GAMMA — solo grafici e Pine",
        value=True, key="v2_gld_visual_extension",
        help="Estensione dei livelli ETF reali nello stesso file Cboe. "
             "La formula e il CSV dei profili originari non cambiano.")
    visual_groups, extension_info = {}, {}
    for name, original in groups.items():
        if show_extension and original.get("usable"):
            visual_groups[name], extension_info[name] = expanded_display(
                original,
                lambda width, expiry=date.fromisoformat(original["expiry"]): profile(
                    data, expiry, reference, band_pct=width),
                reference, price, band, strike_field="strike", gamma_field="net",
                upper_band_limit=10.0)
        else:
            visual_groups[name], extension_info[name] = original, {"extra": 0}
    good = [v for v in visual_groups.values() if v["usable"]]
    if not good:
        st.warning("Nessun profilo NET GAMMA utilizzabile nella fotografia "
                   "selezionata; non vengono inventati strike o Gamma.")
        return
    # Single choice: continuous GC. Yahoo ETF/GC=F matched M5
    # bars, strictly before this Cboe snapshot. NO dated futures / Massive.
    mapping, mapping_issue = load_chart_continuous_mapping(
        "GLD", st.session_state)
    # SPX gamma_section uses one common min/max with 8% spread margin.
    # Independent of bar presentation: no change to original Cboe Gamma.
    xlim = spx_shared_gamma_bounds(good)
    all_strikes = [float(row["strike"]) for p in good for row in p["rows"]]
    ylim = [min(reference * (1 - band / 100), min(all_strikes)),
            max(reference * (1 + band / 100), max(all_strikes))]
    # The same strike ticks on both plots, as in SPX. Never synthesize
    # market levels: ticks are from actual option strikes.
    shared_ticks = sorted({float(row["strike"]) for p in good for row in p["rows"]})
    if len(shared_ticks) > 80:
        step = (len(shared_ticks) + 79) // 80
        shared_ticks = shared_ticks[::step]
    axes = chart_price_axes("GLD", mapping, ylim, shared_ticks)
    projected = axes["projected"]
    st.markdown("**NET GAMMA GC CONTINUO · 0DTE / Weekly**")
    if projected:
        st.caption(
            f"Strike opzioni GLD proiettati sul continuo GC con "
            f"rapporto GLD/{mapping['future_yahoo_ticker']} "
            f"{axes['price_ratio']:.8f} · barra M5 sincronizzata "
            f"{mapping['bar_ny']} New York. NET GAMMA originali invariati. "
            "Il continuo Yahoo è un proxy del continuo TradingView, "
            "che può differire al rollover.")
    else:
        st.caption(
            "Conversione continua non disponibile per questa fotografia: "
            "nessun livello GC viene stimato o mostrato. "
            "Il Pine continuo rimane scaricabile e calcola il rapporto su TradingView.")
    independent_scale = st.checkbox(
        "Ingrandisci ogni profilo con scala indipendente",
        value=False, key="v2_gld_independent_scale",
        help="Disattivato: medesima scala Gamma dei due grafici 0DTE e Weekly, "
             "come SPX. Attivato: barre non direttamente confrontabili.")
    cols = st.columns(len(groups), gap="medium")
    for (title, p), col in zip(groups.items(), cols):
        with col:
            header, source_details = panel_heading(
                title, p["expiry"], source_timestamp=stamp,
                downloaded_rome=st.session_state.get("gld_cboe_import_rome"),
                source=st.session_state.get("gld_cboe_source", ""))
            st.subheader(header)
            st.caption(source_details)
            st.caption(f"{p['eligible']} contratti in fascia · "
                       f"{p['valid_contracts']} contratti completi · "
                       f"{p['complete_strikes']} strike con Call/Put · "
                       f"copertura {p['coverage']:.0%}")
            if p["missing"]:
                st.caption("Dati scartati: " + ", ".join(
                    f"{name}: {count}" for name, count in p["missing"].items()))
            if not p["usable"]:
                st.warning(f"Profilo non utilizzabile: Gamma mancante/tutto zero, "
                           f"meno di due strike completi o copertura inferiore al "
                           f"{MIN_VALID_COVERAGE:.0%}. Nessun livello inventato.")
                continue
            _, capture_label = capture_display(
                stamp, st.session_state.get("gld_cboe_import_rome"),
                st.session_state.get("gld_cboe_source", ""))
            shown = visual_groups[title]
            extra = extension_info[title].get("extra", 0)
            if extra:
                st.caption(f"Estensione grafica: +{extra} strike autentici; "
                           "valori originali invariati.")
            gamma_x = spx_shared_gamma_bounds([shown]) if independent_scale else xlim
            # Never display ETF strikes as GC if prices aren't synchronized.
            if projected:
                fig = _plot(shown, reference, gamma_x, axes["y_range"],
                            price_ratio=axes["price_ratio"], projected=True,
                            title=title, snapshot_label=capture_label,
                            tick_levels=axes["tick_levels"])
                st.plotly_chart(fig, use_container_width=True,
                                key=f"gld_spx_gamma_{title}_{p['expiry']}")
            st.download_button(f"Esporta CSV GLD · {title}",
                               data=_to_csv(p["rows"]),
                               file_name=f"GLD_CBOE_{p['expiry']}_{title}.csv",
                               mime="text/csv", on_click="ignore")
    st.caption("NET GAMMA originali delle opzioni GLD; conversione grafica "
               "sul continuo GC, non Gamma delle opzioni futures.")
    # Keep 4-argument call compatible with a previous module during Streamlit hot reload.
    # The current exporter reads source SHA and Cboe timestamp from session state.
    st.session_state["gld_cboe_timestamp"] = stamp
    render_etf_pine_exports("GLD", visual_groups, reference, base_day)
