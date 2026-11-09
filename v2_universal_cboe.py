"""NET GAMMA UNIVERSALE — CBOE: one manual snapshot, no future mapping.

Independent of NDX/GLD/USO, Supabase, archives and scheduled tasks.
Gamma convention matches V2 emergency: (OI + Volume) * Gamma, calls minus puts.
This is not an independently established dealer-positioning or dollar-GEX model.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import requests
import streamlit as st

MAX_BYTES = 60 * 1024 * 1024
TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
CONTRACT = re.compile(r"^([A-Z0-9.-]+)(\d{6})([CP])(\d{8})$")
NY = ZoneInfo("America/New_York")
ROME = ZoneInfo("Europe/Rome")


def validate_ticker(value):
    symbol = str(value or "").strip().upper()
    if not TICKER.fullmatch(symbol):
        raise ValueError("Ticker non valido: usa soltanto lettere, numeri, punto o trattino.")
    return symbol


def _numeric(v):
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) and n >= 0 else None


def read_json(raw, ticker):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError("File JSON assente o troppo grande (60 MB max).")
    if raw[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as z:
            raw = z.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("JSON decompresso troppo grande.")
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("File non JSON CBOE valido.") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("data"), dict):
        raise ValueError("Oggetto data CBOE assente.")
    actual = str(obj.get("symbol") or "").lstrip("_").upper()
    if actual != ticker:
        raise ValueError(f"Il file contiene {actual or 'un simbolo sconosciuto'}, non {ticker}.")
    options = obj["data"].get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("Catena delle opzioni CBOE vuota.")
    return obj


def parse_contract(item, ticker):
    m = CONTRACT.fullmatch(str(item.get("option", "")).strip().replace(" ", "").upper())
    if not m or m.group(1) != ticker:
        return None
    try:
        expiry = date(2000 + int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:]))
    except ValueError:
        return None
    return expiry, m.group(3), int(m.group(4)) / 1000.0


def expiries(doc, ticker):
    return sorted({v[0] for o in doc["data"]["options"] if isinstance(o, dict)
                   if (v := parse_contract(o, ticker)) is not None})


def profile(doc, ticker, expiry, close, band=3.0):
    if not math.isfinite(close) or close <= 0 or not 0 < band <= 25:
        raise ValueError("Chiusura precedente o fascia non valida.")
    lo, hi = close * (1 - band / 100), close * (1 + band / 100)
    sides = defaultdict(dict)
    seen = set()
    matched, complete, positives = 0, 0, 0
    missing = defaultdict(int)
    for o in doc["data"]["options"]:
        if not isinstance(o, dict):
            continue
        part = parse_contract(o, ticker)
        if part is None or part[0] != expiry or not lo - 1e-9 <= part[2] <= hi + 1e-9:
            continue
        _, side, strike = part
        identifier = (expiry, side, strike)
        if identifier in seen:
            raise ValueError("Contratto duplicato nella catena CBOE.")
        seen.add(identifier)
        matched += 1
        gamma, oi, volume = (_numeric(o.get(k)) for k in ("gamma", "open_interest", "volume"))
        if any(v is None for v in (gamma, oi, volume)):
            missing["Gamma/OI/Volume assenti"] += 1
            continue
        complete += 1
        positives += int(gamma > 0)
        sides[strike][side] = (oi + volume) * gamma
    rows = []
    for strike, pair in sorted(sides.items()):
        if "C" not in pair or "P" not in pair:
            missing["Strike senza coppia Call/Put"] += 1
            continue
        rows.append({"strike": strike, "call": pair["C"], "put": pair["P"],
                     "net": pair["C"] - pair["P"]})
    coverage = complete / matched if matched else 0.0
    usable = coverage >= .70 and positives > 0 and len(rows) >= 2
    return {"expiry": expiry, "rows": rows if usable else [],
            "matched": matched, "complete": complete, "coverage": coverage,
            "missing": dict(missing), "usable": usable, "low": lo, "high": hi}


def import_original(name, content, ticker):
    if len(content) > MAX_BYTES:
        raise ValueError("File troppo grande (60 MB max).")
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [x for x in archive.infolist() if not x.is_dir()
                       and x.filename.lower().endswith((".json", ".json.gz"))
                       and x.file_size <= MAX_BYTES]
            if len(members) != 1:
                raise ValueError("ZIP: deve contenere un solo JSON o JSON.GZ CBOE.")
            with archive.open(members[0]) as fd:
                content = fd.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError("File estratto troppo grande.")
    read_json(content, ticker)
    return content


def download_once(ticker):
    # CBOE can restrict requests from hosted servers; never bypass access restrictions.
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"
    with requests.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                      timeout=(8, 55), stream=True) as response:
        if response.status_code in (401, 403, 429):
            raise RuntimeError(f"CBOE HTTP {response.status_code}: usa importazione manuale.")
        response.raise_for_status()
        chunks, length = [], 0
        for chunk in response.iter_content(1024 * 1024):
            length += len(chunk)
            if length > MAX_BYTES:
                raise ValueError("Risposta CBOE oltre 60 MB.")
            chunks.append(chunk)
    raw = b"".join(chunks)
    read_json(raw, ticker)
    return raw


def _chart(group, ticker, common_x):
    rows = group["rows"]
    fig = go.Figure(go.Bar(x=[r["net"] for r in rows],
                           y=[r["strike"] for r in rows], orientation="h",
                           marker_color=["#22c55e" if r["net"] >= 0 else "#ef4444" for r in rows],
                           hovertemplate="Strike %{y:,.2f}<br>NET %{x:+,.4f}<extra></extra>"))
    fig.add_vline(x=0, line_color="#94a3b8")
    fig.update_layout(template="plotly_dark", height=600,
                      title=f"{ticker} · {group['expiry']:%d/%m/%Y}",
                      xaxis_title="NET GAMMA = Call − Put", xaxis_range=common_x,
                      yaxis_title=f"Strike {ticker}",
                      margin=dict(l=20, r=20, t=55, b=40), showlegend=False)
    return fig


def _pine(ticker, groups):
    """Same Serafini histogram renderer and one common Gamma scale for both profiles."""
    from pine_export import _pine_array, _initial_manual_scale, _top_gamma_rows
    from pine_spx_visual import spx_inputs, SPX_RENDER_FUNCTIONS

    if not groups or len(groups) > 2:
        raise ValueError("Attesi uno o due profili verificati.")
    main_name = next((name for name in groups if name != "Weekly"), None)
    if main_name is None:
        raise ValueError("Scadenza principale CBOE assente.")
    main = groups[main_name]
    weekly = groups.get("Weekly", {"rows": [], "expiry": ""})
    mr, wr = main["rows"], weekly["rows"]
    count = len(mr) + len(wr)
    if not mr or count > 480:
        raise ValueError(f"Livelli Pine {count}: massimo 480; riduci la fascia.")
    for group in (main, weekly):
        for row in group["rows"]:
            if not all(math.isfinite(float(row[k])) for k in ("strike", "net")):
                raise ValueError("Strike/NET GAMMA non finito.")
    is_odte = main_name == "0DTE"
    tc = _top_gamma_rows(mr, "strike", "net", positive=True) if is_odte else []
    tp = _top_gamma_rows(mr, "strike", "net", positive=False) if is_odte else []

    # One common display scale; preserve magnitude comparisons across maturities.
    scale, step = _initial_manual_scale([
        ({"rows": [{"net_gamma": x["net"]} for x in mr]}, 100),
        ({"rows": [{"net_gamma": x["net"]} for x in wr]}, 200)])
    n = lambda value: f"{value:.8f}".rstrip("0").rstrip(".")
    inputs = spx_inputs(n(scale), n(step),
                        tooltip="Scala Gamma unica per 0DTE e Weekly, valori invariati.")
    if not is_odte:
        inputs = inputs.replace('"Mostra 0DTE corrente"', '"Mostra profilo principale"')
        inputs = inputs.replace(
            'showTop3Odte = input.bool(true, "Proietta Top 3 Call / Put 0DTE")',
            'showTop3Odte = false')
    label = "0DTE" if is_odte else "Principale"
    main_title = f"{label} {main['expiry']:%d/%m/%Y}"
    weekly_title = (f"Weekly {weekly['expiry']:%d/%m/%Y}" if wr else "")
    top3_code = (
        '    if showTop3Odte\n'
        '        drawOdteTopProjections(topCalls, topPuts)\n'
        if is_odte else "")
    main_render = (
        f'            if showCurrentOdte\n'
        f'                renderProfile(mainLevels, mainValues, '
        f'bar_index + offsetOdte, "{main_title}", actualScale)\n')
    weekly_render = (
        f'            if showCurrentWeekly\n'
        f'                renderProfile(weeklyLevels, weeklyValues, '
        f'bar_index + weeklyCenter, "{weekly_title}", actualScale)\n'
        if wr else "")
    # Keep exactly the common SPX renderProfile function and line/label
    # cleanup; adapt only the per-column drawing scale and safety check.
    draw = f'''if barstate.islast and validTicker
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)
    float actualScale = gammaPerCandle
    int weeklyCenter = offsetOdte + offsetWeekly
    bool beyondLimit = offsetOdte >= 480 or (showCurrentWeekly and array.size(weeklyValues) > 0 and weeklyCenter >= 480)
    float safeMain = showCurrentOdte ? requiredScale(mainValues, offsetOdte) : 0.0
    float safeWeekly = showCurrentWeekly ? requiredScale(weeklyValues, weeklyCenter) : 0.0
    bool unsafeScale = actualScale < math.max(safeMain, safeWeekly) * 0.999999
    if beyondLimit
        label warn = label.new(bar_index + 10, close, "Distanza profili oltre +500 barre: riduci gli offset.", style=label.style_label_left, color=color.orange, textcolor=color.black, size=size.small)
        array.push(drawnLabels, warn)
    else if unsafeScale
        label warn = label.new(bar_index + 10, close, "Scala Gamma troppo piccola: aumenta Gamma/barra per il profilo interessato.", style=label.style_label_left, color=color.orange, textcolor=color.black, size=size.small)
        array.push(drawnLabels, warn)
    else
{main_render}{weekly_render}{top3_code}'''
    return f'''//@version=6
indicator("NET GAMMA UNIVERSALE {ticker} · CBOE", overlay=true, max_lines_count=500, max_labels_count=35)
// Fotografia CBOE statica; rigenerare il Pine per aggiornare.
// Strike originali {ticker}, nessuna conversione verso futures.
// Formula: Call (OI+Volume)*Gamma - Put (OI+Volume)*Gamma.
// Scala Weekly indipendente: la lunghezza grafica delle barre non e'
// direttamente confrontabile con 0DTE se usano scale differenti.
validTicker = (syminfo.type == "stock" or syminfo.type == "fund") and syminfo.ticker == "{ticker}"

{inputs}

var array<line> drawnLines = array.new_line()
var array<label> drawnLabels = array.new_label()
var array<float> mainLevels = {_pine_array(mr, "strike")}
var array<float> mainValues = {_pine_array(mr, "net")}
var array<float> weeklyLevels = {_pine_array(wr, "strike")}
var array<float> weeklyValues = {_pine_array(wr, "net")}
var array<float> topCalls = {_pine_array(tc, "strike")}
var array<float> topPuts = {_pine_array(tp, "strike")}

{SPX_RENDER_FUNCTIONS}

{draw}
'''

def render():
    with st.expander("NET GAMMA UNIVERSALE — CBOE", expanded=False):
        st.caption("Ticker libero · un solo download manuale CBOE · Gamma originali · "
                   "nessuna conversione, Supabase, replay o cron. Formula: "
                   "(OI+Volume)×Gamma Call − (OI+Volume)×Gamma Put.")
        ticker_text = st.text_input("Ticker CBOE (es. AAPL)", value="AAPL",
                                    key="universal_cboe_ticker").strip().upper()
        try:
            ticker = validate_ticker(ticker_text)
        except ValueError as exc:
            st.warning(str(exc))
            return
        previous = st.session_state.get("universal_cboe_active")
        if previous and previous["ticker"] != ticker:
            st.session_state.pop("universal_cboe_active", None)
            previous = None
        if st.button("Scarica CBOE e calcola", key="universal_cboe_download",
                     use_container_width=True):
            try:
                with st.spinner(f"Download manuale {ticker} da CBOE..."):
                    raw = download_once(ticker)
                st.session_state["universal_cboe_active"] = {
                    "ticker": ticker, "raw": raw, "source": "Download manuale CBOE",
                    "rome": datetime.now(ROME).isoformat(timespec="seconds")}
                st.rerun()
            except Exception as exc:
                st.error(f"Download fallito: {str(exc)[:260]}")
        uploaded = st.file_uploader("Oppure importa ZIP / JSON / JSON.GZ",
                                    type=["zip", "json", "gz"],
                                    key=f"universal_file_{ticker}")
        if st.button("Usa file importato", key="universal_import",
                     disabled=uploaded is None, use_container_width=True):
            try:
                raw = import_original(uploaded.name, uploaded.getvalue(), ticker)
                st.session_state["universal_cboe_active"] = {
                    "ticker": ticker, "raw": raw, "source": "Importazione locale",
                    "rome": None}
                st.rerun()
            except Exception as exc:
                st.error(f"Importazione fallita: {str(exc)[:260]}")
        active = st.session_state.get("universal_cboe_active")
        if not active or active["ticker"] != ticker:
            st.info("Scarica una fotografia CBOE oppure importa il file originale.")
            return
        try:
            doc = read_json(active["raw"], ticker)
            dates = expiries(doc, ticker)
            close = _numeric(doc["data"].get("prev_day_close"))
            if not dates or close is None or close == 0:
                raise ValueError("Scadenze o prev_day_close CBOE non disponibili.")
        except ValueError as exc:
            st.error(str(exc))
            return
        stamp = doc.get("timestamp") or "non dichiarato"
        st.caption(f"Fonte: {active['source']} · timestamp CBOE: {stamp} "
                   "(fuso della fonte non certificato) · acquisizione Roma: "
                   f"{active['rome'] or 'ora originaria non verificabile'}")
        now = datetime.now(NY).date()
        future = [d for d in dates if d >= now]
        initial = now if now in dates else (future[0] if future else dates[-1])
        main_exp = st.selectbox("Scadenza da analizzare", dates, index=dates.index(initial),
                                format_func=lambda d: d.strftime("%d/%m/%Y"),
                                key=f"universal_expiry_{ticker}")
        label = "0DTE" if main_exp == now else "Scadenza selezionata (non 0DTE)"
        weekly_day = main_exp + timedelta(days=((4 - main_exp.weekday()) % 7 or 7))
        weekly = weekly_day if weekly_day in dates else None
        band = st.number_input("Fascia strike ± % dal close precedente",
                               min_value=0.5, max_value=25.0, value=10.0, step=0.5,
                               key="universal_cboe_band")
        groups = {}
        for name, exp in [(label, main_exp), ("Weekly", weekly)]:
            if exp is None:
                continue
            group = profile(doc, ticker, exp, close, band)
            if group["usable"]:
                groups[name] = group
            else:
                st.warning(f"{name}: dati insufficienti (copertura {group['coverage']:.0%}, "
                           f"contratti {group['matched']}, coppie {len(group['rows'])}).")
        if not groups:
            st.error("Nessun profilo affidabile; non calcolo NET GAMMA.")
            return
        allrows = [r for g in groups.values() for r in g["rows"]]
        net = sum(r["net"] for r in allrows)
        calls = sum(r["call"] for r in allrows)
        puts = sum(r["put"] for r in allrows)
        a, b, c = st.columns(3)
        a.metric("NET GAMMA · scadenze selezionate", f"{net:+,.2f}")
        b.metric("CALL GAMMA", f"{calls:,.2f}")
        c.metric("PUT GAMMA", f"{puts:,.2f}")
        st.caption(f"Close precedente {close:,.2f} · prezzo CBOE "
                   f"{doc['data'].get('current_price', 'N/D')} · Gamma non monetario. "
                   "Il NET totale somma solo i profili visualizzati, non tutta la catena.")
        from gamma_chart_style import spx_shared_gamma_bounds
        shared_x = spx_shared_gamma_bounds(groups.values(), field="net")
        st.caption("Scala NET GAMMA comune per tutte le scadenze: lunghezze confrontabili.")
        columns = st.columns(len(groups))
        for (name, group), col in zip(groups.items(), columns):
            with col:
                st.plotly_chart(_chart(group, ticker, shared_x), use_container_width=True,
                                key=f"universal_chart_{ticker}_{name}_{group['expiry']}")
                st.caption(f"{len(group['rows'])} strike Call/Put · "
                           f"copertura {group['coverage']:.0%} · "
                           f"contratti completi {group['complete']}/{group['matched']}")
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["scadenza", "strike", "call", "put", "net"])
        writer.writeheader()
        for name, group in groups.items():
            for row in group["rows"]:
                writer.writerow({"scadenza": group["expiry"], **row})
        st.download_button("Esporta NET GAMMA (.csv)", out.getvalue(),
                           file_name=f"{ticker}_NET_GAMMA.csv", mime="text/csv",
                           key="universal_csv_export", on_click="ignore")
        try:
            pine = _pine(ticker, groups)
            st.download_button(f"Scarica Pine {ticker} (.pine)", pine,
                               file_name=f"{ticker}_NET_GAMMA_CBOE.pine",
                               mime="text/plain", key="universal_pine_export",
                               on_click="ignore")
            with st.expander("Mostra codice Pine da copiare", expanded=False):
                st.code(pine, language="pine")
            st.caption("Pine statico: strike originali sul grafico del solo ticker inserito. "
                       "Non contiene conversioni né aggiornamento automatico.")
        except ValueError as exc:
            st.warning(f"Pine non generato: {exc}")
        st.caption("Modello sperimentale di posizionamento Gamma, non esposizione dealer verificata. "
                   "La disponibilità del download diretto dipende da CBOE e dalla rete del server.")
