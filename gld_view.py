"""GLD-only experimental interface. No CME GC levels and no trade execution."""
import csv
import io
import os

import plotly.graph_objects as go
import streamlit as st

from gld_alpaca import calculate_profile, fetch_gld, MIN_COVERAGE


def _credentials():
    key = os.environ.get("APCA_API_KEY_ID", "")
    secret = os.environ.get("APCA_API_SECRET_KEY", "")
    try:
        key = st.secrets.get("APCA_API_KEY_ID", key)
        secret = st.secrets.get("APCA_API_SECRET_KEY", secret)
    except (FileNotFoundError, KeyError):
        pass
    return str(key or ""), str(secret or "")


def _csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["strike", "call", "put", "net",
                                              "call_oi", "put_oi", "call_volume", "put_volume"])
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def render_gld():
    st.subheader("Gold · GLD (ETF) — esperimento Alpaca")
    st.warning("Questi sono dati delle opzioni sull'ETF GLD (USA), NON delle opzioni CME sul future GC. "
               "Non trasferire direttamente livelli e strike GLD sul grafico GC.")
    st.caption("Alpaca indicativo: greche Black-Scholes, quotazioni indicative e scambi ritardati. "
               "OI potenzialmente differito, volumi giornalieri e nessun GEX monetario/dealer certificato.")
    key, secret = _credentials()
    band = st.number_input("Fascia strike ± % dal close GLD precedente",
                           min_value=0.5, max_value=10.0, value=3.0, step=0.5,
                           key="gld_band", help="Stessa fascia per la scadenza odierna NY e il prossimo venerdì.")
    if not (key and secret):
        st.info("Per collegare l'app Streamlit direttamente ad Alpaca servono le chiavi API "
                "anche nei Secrets dell'app. Il plugin ChatGPT da solo non le trasferisce a Streamlit.")
        with st.expander("Configurazione sicura di Streamlit Secrets"):
            st.code('APCA_API_KEY_ID = "INSERISCI_LA_TUA_KEY"\n'
                    'APCA_API_SECRET_KEY = "INSERISCI_IL_TUO_SECRET"', language="toml")
            st.caption("Streamlit Cloud → App settings → Secrets. Non inserire mai le chiavi nel repository GitHub.")
        return
    if st.button("Aggiorna fotografia GLD da Alpaca", type="primary"):
        try:
            with st.spinner("Lettura GLD, contratti 0DTE e Weekly (solo lettura)..."):
                captured = fetch_gld(key, secret, band_pct=float(band))
            st.session_state["gld_capture"] = captured
            st.success("Dati ricevuti da Alpaca. Verifica copertura, scadenze e data OI qui sotto.")
        except Exception as exc:
            st.error(f"Acquisizione GLD non riuscita: {str(exc)[:340]}")
            return
    data = st.session_state.get("gld_capture")
    if not data:
        st.info("Premi 'Aggiorna fotografia GLD da Alpaca' per avviare il primo controllo.")
        return
    if data.get("symbol") != "GLD" or data.get("feed") != "indicative":
        st.error("Fotografia GLD non riconosciuta.")
        return
    if abs(float(data["band_pct"]) - band) > 1e-8:
        st.info("Fascia modificata: aggiorna la fotografia prima di disegnare un nuovo profilo.")
        return
    close = float(data["prev_close"])
    lower, upper = close * (1 - band / 100), close * (1 + band / 100)
    st.caption(f"Acquisizione: {data['captured_at']} (Roma) · seduta NY {data['as_of_ny']} · "
               f"Close GLD precedente {close:,.2f} USD · fascia {lower:,.2f}–{upper:,.2f} · "
               f"Prezzo ultima operazione {data.get('price_latest') or 'non disponibile'} USD")
    profiles = {}
    for label, group in data["groups"].items():
        try:
            profiles[label] = calculate_profile(group, lower, upper)
        except Exception as exc:
            st.error(f"{label}: catena non valida: {str(exc)[:220]}")
    if not profiles:
        st.error("Nessun profilo valido.")
        return
    usable = [p for p in profiles.values() if p["usable"]]
    values = [r["net"] for p in usable for r in p["rows"]]
    lo, hi = min([0.0] + values), max([0.0] + values)
    span = max(hi - lo, 1e-6)
    horizontal = [lo - span * .06, hi + span * .06]
    columns = st.columns(2, gap="large")
    for label, column in zip(["0DTE", "Weekly"], columns):
        with column:
            p = profiles.get(label)
            if p is None:
                continue
            st.markdown(f"**{label} · {p['expiry']}**")
            st.caption(f"{p['eligible']} contratti rilevati · {p['valid_contracts']} con tutti i dati · "
                       f"{p['complete_strikes']} strike con entrambe le opzioni · "
                       f"copertura contratti {p['coverage']:.0%}")
            if p["oi_dates"]:
                st.caption("Date Open Interest: " + ", ".join(p["oi_dates"]))
                if p["oi_dates"][-1] < data["as_of_ny"]:
                    st.warning("OI non aggiornato alla seduta corrente: profilo sperimentale.")
            if p["missing"]:
                st.caption("Dati assenti/scartati: " + ", ".join(f"{k} {v}" for k, v in p["missing"].items()))
            if not p["usable"]:
                st.warning(f"Profilo non pubblicabile: servono almeno 2 strike Call/Put completi e "
                           f"copertura contratti ≥{MIN_COVERAGE:.0%}. Nessun livello simulato.")
                continue
            if p["coverage"] < 1:
                st.warning("Profilo parziale: alcuni contratti non hanno Gamma, OI o volume. "
                           "Non utilizzare come segnale operativo.")
            rows = p["rows"]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=[r["net"] for r in rows], y=[r["strike"] for r in rows],
                orientation="h", marker_color=["#22c55e" if r["net"] >= 0 else "#ef4444" for r in rows],
                customdata=[[r["call"], r["put"]] for r in rows],
                hovertemplate="GLD %{y:,.2f}<br>Net %{x:+.3f}<br>Call %{customdata[0]:.3f}"
                              "<br>Put %{customdata[1]:.3f}<extra></extra>"))
            fig.add_vline(x=0, line_color="#6b7280")
            fig.add_hline(y=close, line_color="#f0cc65", line_dash="dash")
            steps = [b["strike"] - a["strike"] for a, b in zip(rows, rows[1:])]
            if steps:
                fig.update_traces(width=min(.8, min(steps) * .75))
            fig.update_layout(template="plotly_dark", height=660,
                              margin=dict(l=5, r=5, t=12, b=15), showlegend=False,
                              xaxis=dict(title="Net (OI + Volume) × Gamma", range=horizontal),
                              yaxis=dict(title="Prezzo ETF GLD (USD)", range=[lower, upper], autorange=False))
            st.plotly_chart(fig, use_container_width=True)
            st.download_button(f"Scarica CSV GLD · {label}", data=_csv(rows),
                               file_name=f"GLD_{p['expiry']}_{label}.csv",
                               mime="text/csv", on_click="ignore")
    st.caption("Formula esplorativa: Call [(OI+Volume) × Gamma] − Put [(OI+Volume) × Gamma]. "
               "Tutti gli strike visualizzati sono GLD; non vengono calcolati livelli GC, "
               "Gamma Flip, né esposizioni in dollari. Nessuna operazione di trading eseguita.")
