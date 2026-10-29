"""GLD-only experimental interface. No CME GC levels and no trade execution."""
import csv
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st

from gld_alpaca import calculate_profile, calculate_open_interest, fetch_gld, MIN_COVERAGE
from gld_gamma_estimate import estimate_0dte


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
    fields = ["strike", "call", "put", "net", "call_oi", "put_oi", "call_volume", "put_volume"]
    if rows and "call_gamma" in rows[0]:
        fields.extend(["call_gamma", "put_gamma", "call_iv", "put_iv", "call_method", "put_method"])
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _draw_oi(rows, lower, upper, close):
    """OI-only visualization: green call OI and red negative put OI, NOT Gamma."""
    strikes = [r["strike"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["call_oi"] for r in rows], y=strikes,
        name="OI Call", orientation="h", marker_color="#22c55e",
        hovertemplate="Strike GLD %{y:,.2f}<br>Call OI %{x:,.0f} contratti<extra></extra>"))
    fig.add_trace(go.Bar(
        x=[-r["put_oi"] for r in rows], y=strikes,
        name="OI Put", orientation="h", marker_color="#ef4444",
        customdata=[r["put_oi"] for r in rows],
        hovertemplate="Strike GLD %{y:,.2f}<br>Put OI %{customdata:,.0f} contratti<extra></extra>"))
    steps = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
    if steps:
        fig.update_traces(width=min(.8, min(steps) * .75))
    fig.add_vline(x=0, line_color="#6b7280", line_width=1)
    fig.add_hline(y=close, line_color="#f0cc65", line_dash="dash")
    mx = max([1.0] + [r["call_oi"] for r in rows] + [r["put_oi"] for r in rows])
    fig.update_layout(template="plotly_dark", height=620,
                      margin=dict(l=8, r=8, t=10, b=15), showlegend=True,
                      legend=dict(orientation="h", y=1.07, x=0),
                      xaxis=dict(title="OPEN INTEREST · contratti (non Gamma)",
                                 range=[-mx * 1.12, mx * 1.12]),
                      yaxis=dict(title="Strike ETF GLD · USD",
                                 range=[lower, upper], autorange=False))
    st.plotly_chart(fig, use_container_width=True)


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
    st.markdown("**Gamma 0DTE · modello indipendente (sperimentale)**")
    enable_estimate = st.toggle("Prova a stimare Gamma 0DTE, se Alpaca non lo fornisce",
                                value=True, key="gld_estimate_on")
    use_proxy = st.toggle("Consenti IV Weekly del giorno successivo come proxy, se la IV 0DTE non è ricavabile",
                          value=True, key="gld_iv_proxy", disabled=not enable_estimate)
    rate_percent = st.number_input("Tasso annuo ipotizzato per Black-Scholes (%)",
                                    min_value=0.0, max_value=15.0, value=3.5, step=0.25,
                                    key="gld_bs_rate",
                                    help="Ipotesi modificabile, non dato rilevato da Alpaca. Dividend yield GLD posto a zero.")
    market_close = st.selectbox("Orario termine opzioni GLD a New York",
                                options=["16:15 · sessione normale", "13:15 · chiusura anticipata"],
                                index=0, key="gld_option_close")
    st.caption("Le opzioni GLD sono di tipo americano. Il modello Black-Scholes europeo "
               "e i prezzi indicativi Alpaca producono solo Gamma approssimativi. "
               "Non equivale a Gamma osservato, NET dealer, né livelli GC.")
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
    estimate = None
    if enable_estimate and "0DTE" in profiles and not profiles["0DTE"]["usable"]:
        # A historical snapshot must NEVER silently appear to be a current 0DTE estimate.
        try:
            captured = datetime.fromisoformat(data["captured_at"])
            age = (datetime.now(ZoneInfo("Europe/Rome")) - captured).total_seconds()
            if age > 600 or age < -30:
                st.info("Fotografia GLD troppo vecchia per stimare Gamma 0DTE. "
                        "Premi Aggiorna fotografia GLD da Alpaca.")
            elif not data.get("spot_quote"):
                st.info("La fotografia precedente non contiene la quotazione GLD necessaria: aggiornala.")
            else:
                hour = 13 if market_close.startswith("13:") else 16
                estimate = estimate_0dte(data, annual_rate=rate_percent / 100,
                                          use_weekly_proxy=use_proxy,
                                          close_hour=hour, close_minute=15)
                if estimate["usable"]:
                    profiles["0DTE"] = estimate
                else:
                    st.info("Gamma 0DTE stimato non pubblicabile: copertura "
                            f"{estimate['coverage']:.0%}, strike Call/Put "
                            f"{estimate['complete_strikes']}. Resta disponibile l'Open Interest.")
                    if estimate["excluded"]:
                        st.caption("Motivi dati esclusi: " +
                                   ", ".join(f"{k}: {v}" for k, v in estimate["excluded"].items()))
        except Exception as exc:
            st.warning(f"Stima Gamma 0DTE non disponibile: {str(exc)[:260]}")
    usable = [p for p in profiles.values() if p["usable"]]
    values = [r["net"] for p in usable for r in p["rows"]]
    lo, hi = min([0.0] + values), max([0.0] + values)
    span = max(hi - lo, 1e-6)
    horizontal = [lo - span * .06, hi + span * .06]
    oi_fallback = None
    zero_day = profiles.get("0DTE")
    if zero_day and not zero_day["usable"] and zero_day["eligible"] > 0:
        # Every missing Gamma can be observed directly in the source; OI is separate.
        try:
            oi_fallback = calculate_open_interest(data["groups"]["0DTE"], lower, upper)
        except Exception as exc:
            st.warning(f"OI 0DTE non utilizzabile: {str(exc)[:180]}")
    have_oi = bool(oi_fallback and oi_fallback["usable"])
    single_weekly = bool(zero_day and not zero_day["usable"] and not have_oi)
    if single_weekly:
        st.info("0DTE: NET GAMMA non disponibile per la scadenza odierna; "
                "Alpaca non ha restituito Gamma sufficiente e nemmeno OI completo da rappresentare.")
    labels = ["Weekly"] if single_weekly else ["0DTE", "Weekly"]
    columns = [st.container()] if single_weekly else st.columns(2, gap="large")
    for label, column in zip(labels, columns):
        with column:
            p = profiles.get(label)
            if p is None:
                continue
            estimated_here = label == "0DTE" and bool(p.get("approximate"))
            st.markdown(f"**{label} · {p['expiry']}" +
                        (" · GAMMA STIMATO (non Alpaca)" if estimated_here else "") + "**")
            if estimated_here:
                st.warning("STIMA NON VALIDATA · Black-Scholes europeo su ETF GLD (opzioni americane). "
                           "Quotazioni Alpaca indicative; il calcolo può utilizzare la IV Weekly "
                           "come proxy esplicito. Non usarlo come segnale operativo GC.")
                st.caption(f"Riferimento ETF GLD: {p['spot_used']:,.3f} USD · "
                           f"orario prezzo {p['asof_ny']} NY · "
                           f"tempo residuo {p['minutes_left']:.1f} min · "
                           f"tasso ipotizzato {rate_percent:.2f}% · dividend yield 0%.")
                st.caption("Provenienza IV: " + ", ".join(f"{k} {v}" for k, v in p["sources"].items()))
                if p["excluded"]:
                    st.caption("Esclusi: " + ", ".join(f"{k} {v}" for k, v in p["excluded"].items()))
            st.caption(f"{p['eligible']} contratti rilevati · {p['valid_contracts']} con tutti i dati · "
                       f"{p['complete_strikes']} strike con entrambe le opzioni · "
                       f"copertura contratti {p['coverage']:.0%}")
            dates = p["oi_dates"] or (oi_fallback["oi_dates"] if label == "0DTE" and have_oi else [])
            if dates:
                st.caption("Date Open Interest: " + ", ".join(dates))
                if dates[-1] < data["as_of_ny"]:
                    st.warning("OI precedente alla seduta: fotografia sperimentale.")
            if p.get("missing"):
                st.caption("Dati assenti/scartati: " + ", ".join(f"{k} {v}" for k, v in p["missing"].items()))
            if not p["usable"]:
                if label == "0DTE" and have_oi:
                    st.info("Alpaca non fornisce Gamma per le opzioni 0DTE di questa fotografia. "
                            "NET GAMMA non calcolabile: sotto compare SOLO Open Interest, "
                            "non una misura Gamma né un segnale GC.")
                    st.caption(f"OPEN INTEREST 0DTE · {oi_fallback['complete_pairs']} strike Call/Put "
                               f"· copertura OI {oi_fallback['coverage']:.0%} "
                               f"· OI mancanti {oi_fallback['missing_oi']}")
                    _draw_oi(oi_fallback["rows"], lower, upper, close)
                    continue
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
            fig.add_hline(y=p["spot_used"] if estimated_here else close,
                          line_color="#f0cc65", line_dash="dash")
            steps = [b["strike"] - a["strike"] for a, b in zip(rows, rows[1:])]
            if steps:
                fig.update_traces(width=min(.8, min(steps) * .75))
            fig.update_layout(template="plotly_dark", height=620,
                              margin=dict(l=5, r=5, t=12, b=15), showlegend=False,
                              xaxis=dict(title="Net (OI + Volume) × Gamma STIMATO" if estimated_here
                                         else "Net (OI + Volume) × Gamma Alpaca",
                                         range=horizontal),
                              yaxis=dict(title="Prezzo ETF GLD (USD)", range=[lower, upper], autorange=False))
            st.plotly_chart(fig, use_container_width=True)
            st.download_button(f"Scarica CSV GLD · {label}" +
                               (" (STIMATO)" if estimated_here else ""),
                               data=_csv(rows),
                               file_name=f"GLD_{p['expiry']}_{label}" +
                               ("_STIMATO" if estimated_here else "") + ".csv",
                               mime="text/csv", on_click="ignore")
            if estimated_here:
                with st.expander("Controllo stime: Gamma, IV e fonte per ogni strike"):
                    st.dataframe([{"Strike GLD": r["strike"],
                                   "Gamma Call (stimato)": r["call_gamma"],
                                   "Gamma Put (stimato)": r["put_gamma"],
                                   "IV Call": r["call_iv"], "IV Put": r["put_iv"],
                                   "Fonte Call": r["call_method"], "Fonte Put": r["put_method"]}
                                  for r in rows], use_container_width=True)
    st.caption("Formula esplorativa, Gamma Alpaca dove disponibile e GAMMA STIMATO 0DTE se chiaramente etichettato: "
               "Call [(OI+Volume) × Gamma] − Put [(OI+Volume) × Gamma]. "
               "Tutti gli strike visualizzati sono GLD; non vengono calcolati livelli GC, "
               "Gamma Flip, né esposizioni in dollari. Nessuna operazione di trading eseguita.")
