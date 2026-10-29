"""GLD from the original Cboe option-chain JSON, independent from Alpaca.

Cboe's delayed quote page prohibits automatic extraction. For this study the
user manually downloads the original GLD.json and loads it into Streamlit.
No polling, scraping, scheduled collection, or external API credentials.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import csv
import hashlib
import io

import streamlit as st
import plotly.graph_objects as go

from gld_cboe import (GLD_URL, read_gld, expirations, next_weekly,
                      close_previous, current_price, profile, MIN_VALID_COVERAGE)


def _to_csv(rows):
    keys = ["strike", "net", "call", "put", "call_gamma", "put_gamma",
            "call_oi", "put_oi", "call_volume", "put_volume"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()
    writer.writerows(({key: row.get(key, "") for key in keys} for row in rows))
    return output.getvalue().encode("utf-8-sig")


def _plot(p, reference, common_x, shared_y):
    rows = p["rows"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["net"] for r in rows],
        y=[r["strike"] for r in rows],
        orientation="h",
        marker_color=["#22c55e" if r["net"] >= 0 else "#ef4444" for r in rows],
        customdata=[[r["call"], r["put"], r["call_gamma"], r["put_gamma"]] for r in rows],
        hovertemplate="Strike GLD %{y:,.2f}<br>NET %{x:+.4f}"
                      "<br>Call ponderata %{customdata[0]:.4f}"
                      "<br>Put ponderata %{customdata[1]:.4f}"
                      "<br>Gamma Call %{customdata[2]:.6f}"
                      "<br>Gamma Put %{customdata[3]:.6f}<extra></extra>"))
    diffs = [r1["strike"] - r0["strike"] for r0, r1 in zip(rows, rows[1:])]
    if diffs:
        fig.update_traces(width=min(0.8, max(0.01, min(diffs) * 0.75)))
    fig.add_vline(x=0, line_color="#6b7280")
    fig.add_hline(y=reference, line_color="#eabf65", line_dash="dash", line_width=1.5)
    fig.update_layout(
        template="plotly_dark", height=690,
        margin=dict(l=5, r=5, b=20, t=14), showlegend=False,
        xaxis=dict(title="NET (OI + Volume) × Gamma Cboe", range=common_x),
        yaxis=dict(title="Strike GLD (USD)", range=shared_y, autorange=False),
    )
    return fig


def render_gld_cboe():
    st.subheader("Gold · GLD (ETF) — NET GAMMA Cboe")
    st.caption("Dati originali Cboe: Gamma, Open Interest e Volume per le opzioni GLD. "
               "Non è il mercato delle opzioni CME GC e i livelli NON sono trasferibili direttamente al future.")
    st.caption("Fonte: Cboe delayed quotes · GLD.json. Il timestamp Cboe viene mostrato "
               "esattamente come presente nel file, senza attribuirgli un fuso non documentato.")

    st.markdown("**Acquisizione file originale**")
    st.link_button("Apri GLD.json su Cboe", GLD_URL)
    st.caption("Apri il file nel browser e salvalo come GLD.json; poi importalo qui. "
               "Cboe limita l'estrazione automatica dei dati delayed quotes: "
               "questa modalità non effettua download non presidiati.")

    uploaded = st.file_uploader("Carica GLD.json o GLD.json.gz originale",
                                type=["json", "gz"], key="gld_cboe_upload")
    if uploaded is not None:
        raw = uploaded.getvalue()
        fingerprint = hashlib.sha256(raw).hexdigest()
        if st.session_state.get("gld_cboe_sha256") != fingerprint:
            try:
                parsed = read_gld(raw)
                exps = expirations(parsed)
                if not exps:
                    raise ValueError("Nessuna scadenza GLD riconosciuta nella catena.")
                st.session_state["gld_cboe_raw"] = raw
                st.session_state["gld_cboe_file"] = uploaded.name
                st.session_state["gld_cboe_sha256"] = fingerprint
                st.session_state["gld_cboe_import_rome"] = datetime.now(
                    ZoneInfo("Europe/Rome")).isoformat(timespec="seconds")
                st.success("GLD Cboe validato e caricato.")
            except Exception as exc:
                st.error(f"File non utilizzabile: {str(exc)[:300]}")
                return

    raw = st.session_state.get("gld_cboe_raw")
    if not raw:
        st.info("Importa il JSON Cboe originale per visualizzare i NET GAMMA GLD "
                "0DTE e Weekly. Alpaca non è richiesto.")
        return
    try:
        data = read_gld(raw)
        available = expirations(data)
    except Exception as exc:
        st.error(f"File GLD non valido: {str(exc)[:260]}")
        return

    stamp = data.get("timestamp")
    st.caption(f"**File:** {st.session_state.get('gld_cboe_file', 'GLD.json')} · "
               f"**Importato:** {st.session_state.get('gld_cboe_import_rome', 'non verificato')} (Roma) · "
               f"**Timestamp originale Cboe:** {stamp if stamp else 'non disponibile'}")
    if not stamp:
        st.warning("Il file non contiene un timestamp Cboe verificabile. "
                   "La data d'importazione non certifica la freschezza del mercato.")

    ny_today = datetime.now(ZoneInfo("America/New_York")).date()
    future = [d for d in available if d >= ny_today]
    first = ny_today if ny_today in available else (future[0] if future else available[-1])
    base_day = st.selectbox(
        "Scadenza principale (0DTE solo quando coincide con la data di New York)",
        available, index=available.index(first),
        format_func=lambda d: d.strftime("%d/%m/%Y"), key="gld_cboe_day")
    is_0dte = base_day == ny_today
    if not is_0dte:
        st.warning(f"La scadenza {base_day:%d/%m/%Y} NON coincide con oggi "
                   f"{ny_today:%d/%m/%Y} a New York: profilo storico/futuro, NON 0DTE corrente.")
    weekly = next_weekly(base_day, available)
    if weekly is None:
        st.info("Il prossimo venerdì successivo alla scadenza principale "
                "non è presente nel file: Weekly non disponibile.")
    st.caption("Weekly: " + (weekly.strftime("%d/%m/%Y") if weekly else "non disponibile") +
               " (solo venerdì effettivamente presente nella catena Cboe).")

    auto_ref = close_previous(data)
    if auto_ref is None:
        st.warning("Chiusura precedente assente nel JSON; inserisci un riferimento GLD verificato.")
    reference_text = st.text_input(
        "Chiusura GLD della seduta precedente (USD)",
        value=f"{auto_ref:.4f}" if auto_ref is not None else "",
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

    good = [v for v in groups.values() if v["usable"]]
    magnitudes = [r["net"] for p in good for r in p["rows"]]
    mn, mx = min([0] + magnitudes), max([0] + magnitudes)
    delta = max(mx - mn, 1e-8)
    xlim = [mn - 0.06 * delta, mx + 0.06 * delta]
    ylim = [reference * (1 - band / 100), reference * (1 + band / 100)]
    st.markdown("**NET GAMMA GLD · 0DTE / Weekly**")
    st.caption("Formula: Call [(OI+Volume)×Gamma] − Put [(OI+Volume)×Gamma]. "
               "Il Gamma è letto dal JSON Cboe, non stimato. "
               "Stessa fascia strike e stessa scala Gamma per entrambi i grafici.")
    cols = st.columns(len(groups), gap="large")
    for (title, p), col in zip(groups.items(), cols):
        with col:
            st.markdown(f"**{title} · {p['expiry']}**")
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
            st.plotly_chart(_plot(p, reference, xlim, ylim), use_container_width=True)
            st.download_button(f"Esporta CSV GLD · {title}",
                               data=_to_csv(p["rows"]),
                               file_name=f"GLD_CBOE_{p['expiry']}_{title}.csv",
                               mime="text/csv", on_click="ignore")
    st.caption("Questi grafici non rappresentano Gamma monetario/dealer GEX, "
               "non individuano automaticamente Gamma Flip e non sono livelli GC.")
