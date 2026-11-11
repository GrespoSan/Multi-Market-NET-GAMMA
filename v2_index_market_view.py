"""Dedicated RUT/RTY and DJX/YM principal markets, separate from universal CBOE.

The data is not SPX GEX or futures options. Raw CBOE (OI+V)*Gamma Call-Put
never changes. Only the y-axis undergoes a verified price mapping.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import io
import math
import csv
import streamlit as st
import plotly.graph_objects as go

from v2_universal_cboe import (
    download_once, import_original, read_json, expiries, profile, _pine,
)
from v2_index_basis import compute_basis, CONFIG

NY = ZoneInfo("America/New_York")
ROME = ZoneInfo("Europe/Rome")


@st.cache_data(ttl=3600, show_spinner=False, max_entries=24)
def _basis_cached(ticker, day, key):
    return compute_basis(ticker, day, key)


def _chart(group, symbol, factor, basis, common_x):
    values = group["rows"]
    figure = go.Figure(go.Bar(
        x=[row["net"] for row in values],
        y=[row["strike"] * factor + basis for row in values],
        orientation="h",
        marker_color=["#22c55e" if row["net"] >= 0 else "#ef4444" for row in values],
        hovertemplate="Future %{y:,.2f}<br>NET %{x:+,.4f}<extra></extra>",
    ))
    figure.add_vline(x=0, line_color="#94a3b8")
    figure.update_layout(
        template="plotly_dark", height=590,
        title=f"{symbol} · {group['expiry']:%d/%m/%Y}",
        xaxis_title="NET GAMMA originale CBOE", xaxis_range=common_x,
        yaxis_title="Livelli future proiettati",
        margin=dict(l=20, r=20, t=55, b=40), showlegend=False,
    )
    return figure


def render(ticker):
    if ticker not in CONFIG:
        raise ValueError("Mercato indice sconosciuto")
    info = CONFIG[ticker]
    future = info["future"]
    factor = info["factor"]
    prefix = f"v2_primary_{ticker.lower()}"
    from v2_storage_off import archive_panel, prefer_manual_source
    archive = archive_panel(ticker)
    if archive is not None:
        archived_raw, archived_name = archive
        try:
            verified = read_json(archived_raw, ticker)
            st.session_state[f"{prefix}_active"] = {
                "raw": archived_raw, "origin": f"Archivio GitHub · {archived_name}",
                "stamp": st.session_state.get(f"v2_archive_capture_rome_{ticker}"),
            }
        except Exception as exc:
            st.error(f"Fotografia archivio {ticker} non valida: {str(exc)[:210]}")
    st.subheader(f"Fotografia opzioni CBOE · {ticker}")
    st.caption(
        f"Opzioni {ticker} originali, visualizzazione sul futuro {future}. "
        "Gamma non monetario: [(OI+Volume)×Gamma] Call − [(OI+Volume)×Gamma] Put."
    )
    with st.container(border=True):
        if st.button(f"Scarica fotografia {ticker} da CBOE", key=f"{prefix}_download"):
            try:
                with st.spinner(f"Acquisizione CBOE {ticker}..."):
                    raw = download_once(ticker)
                prefer_manual_source(ticker)
                st.session_state[f"{prefix}_active"] = {
                    "raw": raw, "origin": "Download CBOE manuale",
                    "stamp": datetime.now(ROME).isoformat(timespec="seconds"),
                }
                st.rerun()
            except Exception as exc:
                st.error(f"Download non riuscito: {str(exc)[:260]}")
        with st.expander("Oppure importa ZIP / JSON / JSON.GZ", expanded=False):
            upload = st.file_uploader(
                f"Carica fotografia originale {ticker}", type=["zip", "json", "gz"],
                key=f"{prefix}_upload",
            )
            if st.button("Usa file importato", key=f"{prefix}_import",
                         disabled=upload is None):
                try:
                    raw = import_original(upload.name, upload.getvalue(), ticker)
                    prefer_manual_source(ticker)
                    st.session_state[f"{prefix}_active"] = {
                        "raw": raw, "origin": "Importazione locale", "stamp": None,
                    }
                    st.rerun()
                except Exception as exc:
                    st.error(f"Importazione non riuscita: {str(exc)[:260]}")
    active = st.session_state.get(f"{prefix}_active")
    if not active:
        st.info(f"Nessuna fotografia {ticker} verificata. Usa l'acquisizione manuale o l'importazione.")
        return
    try:
        doc = read_json(active["raw"], ticker)
        dates = expiries(doc, ticker)
        reference = float(doc["data"]["prev_day_close"])
        if not dates or not math.isfinite(reference) or reference <= 0:
            raise ValueError("Scadenze o close precedente CBOE non validi")
    except (ValueError, TypeError, KeyError) as exc:
        st.error(f"Fotografia non utilizzabile: {exc}")
        return
    st.caption(
        f"Fonte: {active['origin']} · CBOE timestamp {doc.get('timestamp', 'non dichiarato')} "
        f"(fuso fonte non certificato) · acquisizione Roma {active['stamp'] or 'non verificabile'}"
    )
    close = st.number_input(
        f"Close precedente {ticker} · verificare fonte",
        value=reference, min_value=0.01, format="%.4f",
        key=f"{prefix}_close",
    )
    today = datetime.now(NY).date()
    available = [d for d in dates if d >= today]
    preferred = today if today in dates else available[0] if available else dates[-1]
    day = st.selectbox(
        "Scadenza principale (0DTE solo se coincide con la seduta NY)", dates,
        index=dates.index(preferred),
        format_func=lambda d: d.strftime("%d/%m/%Y"),
        key=f"{prefix}_expiry",
    )
    following_fridays = [d for d in dates if d > day and d.weekday() == 4]
    weekly = st.selectbox(
        "Weekly (scadenza CBOE effettivamente presente)",
        [None] + following_fridays,
        format_func=lambda d: "Non disponibile" if d is None else d.strftime("%d/%m/%Y"),
        key=f"{prefix}_weekly",
    )
    st.subheader(f"Differenziale {future} − {'RUT' if ticker == 'RUT' else 'Dow Jones'}")
    st.caption(
        "Calcolo automatico sulla seduta cash precedente: barre chiuse 15m Massive "
        "future trimestrale e Yahoo indice, sincronizzate per timestamp. "
        "Contratto scelto per la giornata di analisi con controllo rollover."
    )
    result_key = f"{prefix}_basis_result"
    value_key = f"{prefix}_basis_value"
    attempted_key = f"{prefix}_basis_attempted"
    target_key = f"{prefix}_basis_target"
    if st.session_state.get(target_key) != day.isoformat():
        st.session_state[target_key] = day.isoformat()
        st.session_state.pop(result_key, None)
        st.session_state[value_key] = ""
        st.session_state.pop(attempted_key, None)
    def recalc():
        try:
            api = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
            result = _basis_cached(ticker, day, api)
            st.session_state[result_key] = result
            st.session_state[value_key] = f"{result['basis']:.4f}"
            st.session_state.pop(f"{prefix}_basis_error", None)
        except Exception as exc:
            st.session_state.pop(result_key, None)
            st.session_state[f"{prefix}_basis_error"] = str(exc)[:260]
    if not st.session_state.get(attempted_key):
        st.session_state[attempted_key] = True
        recalc()
    if st.button(f"Ricalcola differenziale {future}", key=f"{prefix}_recalc"):
        _basis_cached.clear()
        recalc()
    if st.session_state.get(f"{prefix}_basis_error"):
        st.warning("Differenziale automatico non disponibile: " +
                   st.session_state[f"{prefix}_basis_error"])
    st.text_input(
        f"Differenziale {future} meno indice (punti future, modificabile)",
        key=value_key,
        help="Inserisci un basis verificato per il contratto future selezionato. "
             "Un campo vuoto blocca l'esportazione Pine: mai assumere zero.",
    )
    basis_raw = str(st.session_state.get(value_key, "")).strip()
    try:
        basis = float(basis_raw.replace(",", ".")) if basis_raw else None
        if basis is not None and not math.isfinite(basis):
            raise ValueError("non finito")
    except ValueError:
        st.error("Differenziale non valido: inserisci un numero finito")
        return
    result = st.session_state.get(result_key)
    if result:
        st.caption(
            f"{result['source']} · Contratto {result['tv_contract']} · "
            f"seduta {result['reference_date']} · {result['bar_count']} barre comuni · "
            f"media {result['basis']:+.2f}, min {result['minimum']:+.2f}, "
            f"max {result['maximum']:+.2f} · rollover {result['roll_day']}."
        )
    if ticker == "DJX":
        st.info("DJX = DJIA / 100 (specifica CBOE). "
                "Sul future YM/MYM: strike DJX × 100 + differenziale YM−DJIA.")
    else:
        st.caption("Sul future RTY/M2K: strike RUT + differenziale RTY−RUT.")
    band = st.number_input(
        "Fascia strike ± % dal close precedente (comune)",
        min_value=0.5, max_value=25.0, value=10.0, step=0.5,
        key=f"{prefix}_band",
    )
    groups = {}
    for title, expiry in (("0DTE" if day == today else "Principale", day),
                          ("Weekly", weekly)):
        if expiry is None:
            continue
        try:
            group = profile(doc, ticker, expiry, close, band)
            if group["usable"]:
                groups[title] = group
            else:
                st.warning(f"{title}: Gamma insufficienti; copertura {group['coverage']:.0%}.")
        except ValueError as exc:
            st.warning(f"{title}: {exc}")
    if not groups:
        st.error("Nessun profilo CBOE validato: nessun Pine generato.")
        return
    rows = [r for g in groups.values() for r in g["rows"]]
    net = sum(row["net"] for row in rows)
    st.metric("NET GAMMA · sole scadenze mostrate", f"{net:+,.2f}")
    st.caption(
        f"Gamma originale CBOE · {len(rows)} livelli · close {ticker} {close:.2f}. "
        "Zero interpolazione e zero modifica del Gamma."
    )
    if basis is None:
        st.warning("Differenziale non verificato: grafici sui futures ed export Pine bloccati.")
        return
    maximum = max(abs(row["net"]) for row in rows) or 1.0
    common_x = [-maximum * 1.08, maximum * 1.08]
    cols = st.columns(len(groups))
    for (name, group), col in zip(groups.items(), cols):
        with col:
            st.plotly_chart(
                _chart(group, future, factor, basis, common_x),
                use_container_width=True,
                key=f"{prefix}_chart_{name}_{day}",
            )
            st.caption(f"{len(group['rows'])} strike · copertura {group['coverage']:.0%}")
    try:
        pine = _pine(ticker, groups, future_mode=True, future_basis=basis)
        st.download_button(
            f"Scarica Pine {ticker} → {future} / micro",
            data=pine,
            file_name=f"{ticker}_{future}_NET_GAMMA.pine",
            mime="text/plain",
            key=f"{prefix}_pine_download",
        )
        with st.expander("Mostra codice Pine da copiare"):
            st.code(pine, language="pine")
    except ValueError as exc:
        st.warning(f"Esportazione Pine non disponibile: {exc}")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["scadenza", "strike_indice", "livello_future", "net_gamma_originale"])
    for group in groups.values():
        for row in group["rows"]:
            writer.writerow([
                group["expiry"], row["strike"], row["strike"] * factor + basis, row["net"],
            ])
    st.download_button(
        "Esporta livelli verificati CSV",
        output.getvalue(),
        file_name=f"{ticker}_{future}_levels.csv",
        mime="text/csv", key=f"{prefix}_csv",
    )
