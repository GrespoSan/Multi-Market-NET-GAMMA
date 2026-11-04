"""Multi-Market V2 SPX-adapted market engines.

Source: preserved independent validated NDX/GLD/USO engines of V1.
Called only within the cloned SPX-style ANALISI NET GAMMA dashboard.
No Supabase imports, persistent store access or scheduled downloads.
"""
import csv
import io
import math
from datetime import datetime, date
from zoneinfo import ZoneInfo
import streamlit as st

from markets import MARKETS
from gamma_chart_style import profile_chart, panel_heading, capture_display, spx_shared_gamma_bounds
from v2_visual_extension import expanded_display
from v2_storage_off import archive_panel, prefer_manual_source
from market_ui import render_empty_snapshot
from ndx_engine import (unpack_snapshot, available_expirations, close_from_payload,
                        profile, weekly_target, DEFAULT_BAND_PCT)
from ndx_basis import fetch_basis
from pine_export import make_pine
from v2_pine_timed_exports import render_timed_pine_exports
from macro_events import events_for_pine, CREDITS as MACRO_CREDITS
from pine_news_overlay import append_news
from nq_price_panel import load_nq_candles, chart_compare_nq

ROME=ZoneInfo('Europe/Rome')


def render_selected_market(market_key):
    market=MARKETS[market_key]
    if market_key == 'GOLD':
        from gld_cboe_view import render_gld_cboe
        render_gld_cboe()
        return
    if market_key == 'WTI':
        from uso_cboe_view import render_uso_cboe
        render_uso_cboe()
        return
    
    if not market.enabled:
        st.info(f'{market.label}: modulo predisposto, non ancora operativo. {market.info} '
                'Nessun livello sarà simulato senza una catena opzioni validata.')
        return
    
    
    st.subheader("Fotografia opzioni Cboe · NDX")
    st.caption("La stessa fotografia viene utilizzata anche dal Pine di emergenza in fondo alla pagina; nessun secondo download.")
    snapshot_placement = st.container()
    # Unico download/importazione manuale nel pannello emergenza in fondo pagina.
    # Qui rimane il selettore delle fotografie archiviate, non un secondo upload.
    st.caption("Per download manuale Cboe o importazione ZIP/JSON, usa "
               "PINE DI EMERGENZA — NET GAMMA CORRENTE in fondo alla pagina.")
    with snapshot_placement:
        archive_selected=archive_panel('NDX')
        if archive_selected is not None:
            scheduled_raw, scheduled_name=archive_selected
            try:
                unpack_snapshot(scheduled_raw)
                st.session_state['ndx_blob']=scheduled_raw
                st.session_state.pop("v2_ndx_reference_current", None)
                st.session_state['ndx_name']=scheduled_name
                st.session_state['ndx_source']='Archivio privato · rilevamento programmato'
                st.session_state['ndx_capture_rome_iso']=st.session_state.get(
                    'v2_archive_capture_rome_NDX')
                st.session_state['ndx_download_rome']=(
                    st.session_state['ndx_capture_rome_iso']
                    or 'Archivio privato · ora acquisizione non verificabile')
                st.success('Fotografia programmata NDX validata e caricata.')
            except Exception as exc:
                st.error(f'Archivio NDX non valido: {str(exc)[:230]}')
    
    blob=st.session_state.get('ndx_blob')
    if not blob:
        render_empty_snapshot('NDX')
        return
    try:
        doc=unpack_snapshot(blob)
        expiry_dates=available_expirations(doc)
    except Exception as exc:
        st.error(f'Fotografia non valida: {exc}')
        return
    if not expiry_dates:
        st.error('Nessuna scadenza NDX/NDXP riconosciuta: controllare il formato dei contratti.')
        return
    
    st.markdown(f'**File:** {st.session_state.get("ndx_name")} · '
                f'**Acquisizione:** {st.session_state.get("ndx_download_rome") or "non verificabile (file importato)"} · '
                f'**Timestamp Cboe originale:** `{doc.get("timestamp", "non dichiarato")}`')
    
    st.subheader('Riferimento indice e differenziale NQ − NDX')
    ref_auto=close_from_payload(doc)
    reference_input=st.text_input('Chiusura NDX della sessione precedente',
                                value=f'{ref_auto:.4f}' if ref_auto else '',
                                help='Dal campo prev_day_close della fotografia. Se assente, inserire valore verificato.')
    try:
        reference=float(reference_input.replace(',','.'))
        if reference<=0 or not math.isfinite(reference):raise ValueError()
    except ValueError:
        st.info('Inserisci una chiusura NDX precedente valida per procedere.')
        return
    
    st.session_state["v2_ndx_reference_current"] = reference
    now=datetime.now(ZoneInfo('America/New_York')).date()
    archive_ny_day = (
        st.session_state.get('v2_archive_capture_nyday_NDX')
        if st.session_state.get('v2_archive_choice_ndx') != 'manuale'
        else None)
    snapshot_day = archive_ny_day or now
    non_past=[d for d in expiry_dates if d >= snapshot_day]
    default_exp=(snapshot_day if snapshot_day in expiry_dates
                 else non_past[0] if non_past else expiry_dates[-1])
    day=st.selectbox('Scadenza 0DTE / giornata analizzata',expiry_dates,
                     index=expiry_dates.index(default_exp),format_func=lambda x:x.strftime('%d/%m/%Y'))
    if st.session_state.get('_ndx_basis_target') != day.isoformat():
        st.session_state['_ndx_basis_target']=day.isoformat()
        st.session_state['ndx_basis_value']=''
        st.session_state.pop('ndx_basis_result',None)
        st.session_state.pop('ndx_basis_error',None)
        st.session_state.pop('ndx_basis_attempted',None)
    if day!=now:
        st.caption('0DTE storico / di studio: la scadenza selezionata non coincide '
                   'con la giornata corrente di New York.')
    elif archive_ny_day and day == archive_ny_day:
        st.caption('0DTE del rilevamento programmato selezionato.')
    weekly_default=weekly_target(day,expiry_dates)
    fridays=[x for x in expiry_dates if x.weekday()==4 and x>=day and x!=day]
    weekly_exp=st.selectbox('Scadenza Weekly (solo scadenze venerdì realmente presenti)',
                             [None]+fridays,
                             index=fridays.index(weekly_default)+1 if weekly_default in fridays else 0,
                             format_func=lambda x: 'Non disponibile' if x is None else x.strftime('%d/%m/%Y'))
    
    @st.cache_data(ttl=3600, show_spinner=False, max_entries=16)
    def _cached_basis(target_day):
        """Calcola il basis una volta per data e lo riusa nei rerun Streamlit."""
        try:
            massive_key=str(st.secrets.get("MASSIVE_API_KEY","")).strip()
        except Exception:
            massive_key=""
        return fetch_basis(target_day,massive_key)
    
    def _calculate_and_store_basis():
        try:
            result=_cached_basis(day)
            st.session_state['ndx_basis_result']=result
            st.session_state['ndx_basis_value']=f"{result['basis']:.4f}"
            st.session_state.pop('ndx_basis_error',None)
        except Exception as exc:
            st.session_state.pop('ndx_basis_result',None)
            st.session_state['ndx_basis_error']=str(exc)[:240]
    
    # Re-try once after the Massive date-bound correction, including sessions
    # that previously failed and kept the old ndx_basis_attempted flag.
    if st.session_state.get('ndx_basis_revision') != 'massive_15m_full_day_v2':
        st.session_state['ndx_basis_revision']='massive_15m_full_day_v2'
        st.session_state.pop('ndx_basis_attempted',None)
        st.session_state.pop('ndx_basis_error',None)
        if not st.session_state.get('ndx_basis_result'):
            st.session_state['ndx_basis_value']=''
    # Prima acquisizione del giorno: differenziale automatico; nessun clic richiesto.
    # Successivi rerun (download Pine, cambio widget) non sovrascrivono il manuale.
    if not st.session_state.get('ndx_basis_attempted'):
        st.session_state['ndx_basis_attempted']=True
        with st.spinner('Calcolo automatico NQ–NDX sulla sessione precedente...'):
            _calculate_and_store_basis()
    
    if st.button('Ricalcola differenziale NQ–NDX', help='Richiede un nuovo calcolo e aggiorna il valore modificabile'):
        _cached_basis.clear()
        with st.spinner('Aggiornamento differenziale NQ–NDX...'):
            _calculate_and_store_basis()
    if st.session_state.get('ndx_basis_error'):
        st.warning('Differenziale automatico temporaneamente non disponibile: '
                   + st.session_state['ndx_basis_error']
                   + '. Inserisci un valore verificato o usa Ricalcola.')
    
    basis_text=st.text_input('Differenziale NQ − NDX (modificabile)',key='ndx_basis_value',
                            help='Esporta livelli NQ soltanto con differenziale verificato. '
                                 'Contratto NQ trimestrale selezionato in automatico secondo il rollover CME. '
                                 'Calcolo della seduta cash precedente con Massive NQ e Yahoo NDX.')
    try:
        basis=float(basis_text.replace(',','.').strip()) if basis_text.strip() else None
        if basis is not None and not math.isfinite(basis):raise ValueError()
    except ValueError:
        st.error('Differenziale non numerico o non finito')
        return
    if st.session_state.get('ndx_basis_result'):
        res=st.session_state['ndx_basis_result']
        st.caption(f"Proposta automatica {res['basis']:+.2f} pt · "
                   f"**Contratto {res['tv_contract']}** ({res['ticker']}, fonte Massive) · "
                   f"seduta {res['reference_date']} · {res['bar_count']} barre comuni · "
                   f"min {res['minimum']:+.2f} / max {res['maximum']:+.2f} · "
                   f"rollover CME successivo {res['roll_day']:%d/%m/%Y}.")
    
    # Fascia comune 0DTE/Weekly: percentuale libera, centrata sul close NDX precedente.
    # Modificare la fascia cambia solo gli strike selezionati, mai la formula Gamma.
    band_pct=st.number_input('Fascia strike ± % dal Close precedente (0DTE e Weekly)',
                             min_value=0.1, max_value=10.0, value=3.0, step=0.1,
                             format='%.1f', key='ndx_strike_band_percent',
                             help='Unica ampiezza percentuale applicata alle due scadenze; '
                                  'include ogni strike reale dentro i limiti.')
    profiles={}
    for kind,exp in [('0DTE',day),('Weekly',weekly_exp)]:
        if exp is None:continue
        try:
            profiles[kind]=profile(doc,exp,reference,band_pct=band_pct)
        except Exception as exc:
            st.warning(f'{kind}: {exc}')
    if not profiles:
        st.error('Nessuno strike disponibile nella fascia percentuale: NET GAMMA e Pine non generati.')
        return
    show_extension = st.checkbox(
        "Estensione automatica NET GAMMA — solo grafici e Pine",
        value=True, key="v2_ndx_visual_extension",
        help="Estende soltanto la visualizzazione usando gli strike già nel JSON Cboe. "
             "Il nucleo e i calcoli originari NDX rimangono invariati.")
    visual_profiles = {}
    visual_notes = {}
    spot_ndx = doc["data"].get("current_price")
    for kind, group in profiles.items():
        if show_extension:
            visual_profiles[kind], visual_notes[kind] = expanded_display(
                group,
                lambda width, exp=date.fromisoformat(group["expiry"]): profile(
                    doc, exp, reference, band_pct=width),
                reference, spot_ndx, band_pct,
                strike_field="strike_index", gamma_field="net_gamma",
                upper_band_limit=20.0)
        else:
            visual_profiles[kind], visual_notes[kind] = group, {"extra": 0}
    
    # Stessa finestra di prezzo per 0DTE e Weekly, basata sul close indice precedente.
    band_low = reference * (1 - band_pct / 100)
    band_high = reference * (1 + band_pct / 100)
    # Identical 0DTE/Weekly X scale to SPX (raw values plus 8% span).
    shared_gamma_range = spx_shared_gamma_bounds(visual_profiles.values(), field='net_gamma')
    shared_ticks = sorted({float(r['strike_index']) + (basis or 0.0)
                           for p in visual_profiles.values() for r in p['rows']})
    if len(shared_ticks) > 80:
        shared_ticks = shared_ticks[::(len(shared_ticks) + 79) // 80]
    price_shift = basis if basis is not None else 0.0
    shown_strikes = [float(r["strike_index"])
                    for p in visual_profiles.values() for r in p["rows"]]
    shared_price_range = [min(band_low, min(shown_strikes)) + price_shift,
                          max(band_high, max(shown_strikes)) + price_shift]
    
    st.subheader(f'NET GAMMA — NDX → NQ · fascia ±{band_pct:g}%')
    st.caption('Formula invariata: NET = [(OI+Volume)×Gamma] Call − [(OI+Volume)×Gamma] Put. '
               'Tutti gli strike Cboe disponibili tra '
               f'**{band_low:,.2f} e {band_high:,.2f} NDX** (±{band_pct:g}% dal close precedente). '
               'Stessa fascia prezzi e stessa scala Gamma per 0DTE e Weekly.')
    if basis is None:
        st.warning('Differenziale NQ–NDX assente: grafici in scala NQ non disponibili. '
                   'Non vengono mostrati strike NDX come se fossero NQ; '
                   'esportazione NQ disabilitata.')
    else:
        # Identico riferimento grafico SPX/ES: close indice precedente + basis future.
        # E' solo un livello guida e non interviene nel calcolo dei NET GAMMA.
        previous_close_nq = reference + basis
        st.caption(
            f'**Close NQ precedente (stimato)** = Chiusura NDX {reference:,.4f} '
            f'+ differenziale NQ–NDX {basis:+,.4f} = **{previous_close_nq:,.2f}**'
        )
    
    independent_scale = st.checkbox(
        'Ingrandisci ogni profilo con scala indipendente', value=False,
        key='v2_ndx_independent_scale',
        help='Disattivato: scala Gamma comune fra 0DTE e Weekly, come SPX. '
             'Attivato: le lunghezze delle barre non sono più confrontabili.')
    cols=st.columns(len(profiles),gap='medium')
    for (kind,group),column in zip(profiles.items(),cols):
        with column:
            title, source_details = panel_heading(
                kind, group['expiry'], source_timestamp=doc.get('timestamp'),
                downloaded_rome=st.session_state.get('ndx_download_rome'),
                source=st.session_state.get('ndx_source', st.session_state.get('ndx_name', '')))
            st.subheader(title)
            st.caption(source_details)
            st.caption(f'{group["contract_count"]} contratti · '
                       f'{group["available_strikes"]} strike disponibili · '
                       f'{group["selected_strikes"]} originali · '
                       f'{visual_notes[kind].get("extra", 0)} aggiuntivi solo grafica/Pine')
            _, capture_label = capture_display(
                doc.get('timestamp'), st.session_state.get('ndx_download_rome'),
                st.session_state.get('ndx_source', st.session_state.get('ndx_name', '')))
            if basis is not None:
                fg = profile_chart(
                    visual_profiles[kind]['rows'], 'NDX', reference,
                    (spx_shared_gamma_bounds([visual_profiles[kind]], field='net_gamma')
                     if independent_scale else shared_gamma_range),
                    shared_price_range, level_field='strike_index',
                    gamma_field='net_gamma', price_shift=price_shift,
                    axis_symbol='NQ', close_label='Close prec. proiettato',
                    ndx=True, show_close=True,
                    title=kind, snapshot_label=capture_label,
                    tick_levels=shared_ticks)
                st.plotly_chart(fg, use_container_width=True,
                                key=f'ndx_spx_gamma_{kind}_{group["expiry"]}')
    
    # Vista confronto facoltativa: la chiamata Yahoo 5m parte soltanto se attivata.
    # I grafici NDX base e il motore Gamma rimangono invariati.
    st.subheader('Confronto NET GAMMA / candele Nasdaq')
    show_candle_compare=st.toggle('Mostra NET GAMMA a sinistra e candele NQ a destra',
                                  value=False, key='ndx_show_candle_compare')
    if show_candle_compare:
        names=list(profiles)
        mode=st.radio('Profilo da confrontare con NQ', names,
                      horizontal=True, key='ndx_candle_profile')
        if basis is None:
            st.info('Inserisci il differenziale NQ–NDX per allineare la scala dei prezzi.')
        else:
            try:
                with st.spinner('Lettura candele NQ=F Yahoo 5 minuti...'):
                    candles=load_nq_candles(day)
                fig=chart_compare_nq(profiles[mode],candles,basis,
                                     band_low,band_high,previous_close_nq,mode)
                st.plotly_chart(fig, use_container_width=True,
                                key=f'ndx_price_gamma_{day}_{mode}')
                st.caption('Scala prezzi condivisa NQ. Candele NQ=F Yahoo a 5 minuti '
                           '(possono differire da NQ1! TradingView); nessuna candela simulata. '
                           'L’intervallo visibile comprende anche le candele quando il '
                           'mercato esce dalla fascia strike selezionata.')
            except Exception as exc:
                st.warning(f'Candele NQ a 5 minuti non disponibili: {str(exc)[:240]}. '
                           'Il profilo NET GAMMA rimane accessibile sopra.')
    
    st.subheader('Esportazione Pine Script v6')
    if basis is None:
        st.info('Inserisci il differenziale NQ–NDX per esportare gli strike sul grafico NQ.')
        return
    
    # Time-based exports are prepared from verified same-day V2 archives.
    # Linee news opzionali: il calendario è indipendente dai NET GAMMA.
    # Nascondiamo i dettagli nella sezione espandibile, senza cambiare il
    # codice Pine esportato o inventare timestamp se la fonte è assente.
    macro_news=[]
    with st.expander('Dettaglio news macro opzionali nei Pine', expanded=False):
        try:
            with st.spinner('Verifica calendario macro USA...'):
                macro_news=events_for_pine(day)
            st.caption(f"Eventi macro con orario verificato: {len(macro_news)} "
                       f"per il {day:%d/%m/%Y} · Fonte: [Finance Calendar]({MACRO_CREDITS}). "
                       "Le linee possono essere disattivate nei parametri Pine.")
        except Exception:
            st.caption('Calendario macro non disponibile: eventuali linee news '
                       'vengono omesse dai Pine. I livelli NET GAMMA non cambiano.')
    # Pine corrente dalla fotografia selezionata: separato dai tre
    # pulsanti orari, incluso 07:30 autonomo (richiesto dall'utente).
    st.markdown("**NET GAMMA corrente · NQ/MNQ · 0DTE + Weekly**")
    if "0DTE" in visual_profiles and "Weekly" in visual_profiles:
        try:
            current_script = make_pine(
                {"0DTE": visual_profiles["0DTE"],
                 "Weekly": visual_profiles["Weekly"]},
                basis, day, "NET GAMMA CORRENTE",
                acquisition_time=st.session_state.get("ndx_capture_rome_iso"))
            if macro_news:
                current_script = append_news(current_script, macro_news)
            st.download_button(
                "Scarica Pine NET GAMMA corrente · NQ/MNQ (.pine)",
                data=current_script.encode("utf-8"),
                file_name=f"NDX_NET_GAMMA_CORRENTE_{day:%Y%m%d}.pine",
                mime="text/plain", on_click="ignore",
                key=f"ndx_current_pine_{day:%Y%m%d}",
                use_container_width=True)
            with st.expander("Mostra codice Pine corrente da copiare"):
                st.code(current_script, language="pine")
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            st.info("Pine corrente non disponibile per la fotografia "
                    f"selezionata: {str(exc)[:220]}")
    else:
        st.info("Per esportare il Pine corrente occorrono sia il profilo "
                "0DTE sia il Weekly della fotografia selezionata.")

    with st.expander("Pine per orari · 07:30 / 15:50 / 20:30",
                     expanded=False):
        render_timed_pine_exports(
            'NDX', day, reference, band_pct, basis,
            extension=show_extension, macro_news=macro_news)
    st.caption('Il Pine corrente usa la fotografia selezionata; quello '
               'delle 07:30 rimane disponibile come esportazione autonoma '
               'assieme ai confronti 07:30→15:50 e 15:50→20:30.')
    
