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
from market_ui import render_acquisition_controls, render_empty_snapshot
from data_sources import download_ndx, NDX_URL
from ndx_engine import (unpack_snapshot, available_expirations, close_from_payload,
                        profile, weekly_target, DEFAULT_BAND_PCT)
from ndx_basis import fetch_basis
from pine_export import make_pine
from macro_events import events_for_pine, CREDITS as MACRO_CREDITS
from pine_news_overlay import append_news
from nq_price_panel import load_nq_candles, chart_compare_nq

ROME=ZoneInfo('Europe/Rome')


def render_selected_market(market_key):
    market=MARKETS[market_key]
    if market_key == 'GOLD':
        from gld_cboe_view import render_gld_cboe
        render_gld_cboe()
        st.stop()
    if market_key == 'WTI':
        from uso_cboe_view import render_uso_cboe
        render_uso_cboe()
        st.stop()
    
    if not market.enabled:
        st.info(f'{market.label}: modulo predisposto, non ancora operativo. {market.info} '
                'Nessun livello sarà simulato senza una catena opzioni validata.')
        st.stop()
    
    
    st.subheader("Fotografia opzioni Cboe · NDX")
    snapshot_placement = st.container()
    with st.expander("Acquisizione manuale / importazione JSON", expanded=False):
        fetch_pressed,uploaded=render_acquisition_controls('NDX',NDX_URL, show_header=False)
        if fetch_pressed:
            try:
                with st.spinner('Lettura fotografia NDX da Cboe...'):
                    raw=download_ndx()
                    unpack_snapshot(raw)
                prefer_manual_source('NDX')
                st.session_state['ndx_blob']=raw
                st.session_state['ndx_name']='NDX_CBOE_online.json'
                st.session_state['ndx_download_rome']=datetime.now(ROME).strftime('%d/%m/%Y %H:%M:%S Roma')
                st.success('Fotografia NDX ricevuta e verificata nella struttura.')
            except Exception as exc:
                st.error(f'Fonte live non disponibile: {str(exc)[:260]}')
        if uploaded is not None:
            content=uploaded.getvalue()
            if st.session_state.get('ndx_upload_tag') != (uploaded.name, len(content),hash(content)):
                try:
                    unpack_snapshot(content)
                    prefer_manual_source('NDX')
                    st.session_state['ndx_blob']=content
                    st.session_state['ndx_name']=uploaded.name
                    st.session_state['ndx_download_rome']=None
                    st.session_state['ndx_upload_tag']=(uploaded.name,len(content),hash(content))
                    st.success('JSON originale NDX importato e validato.')
                except Exception as exc:
                    st.error(f'File NDX non riconosciuto: {exc}')
    with snapshot_placement:
        archive_selected=archive_panel('NDX')
        if archive_selected is not None:
            scheduled_raw, scheduled_name=archive_selected
            try:
                unpack_snapshot(scheduled_raw)
                st.session_state['ndx_blob']=scheduled_raw
                st.session_state['ndx_name']=scheduled_name
                st.session_state['ndx_download_rome']=(
                    st.session_state.get('v2_archive_capture_rome_NDX')
                    or 'Archivio privato · ora acquisizione non verificabile')
                st.success('Fotografia programmata NDX validata e caricata.')
            except Exception as exc:
                st.error(f'Archivio NDX non valido: {str(exc)[:230]}')
    
    blob=st.session_state.get('ndx_blob')
    if not blob:
        render_empty_snapshot('NDX')
        st.stop()
    try:
        doc=unpack_snapshot(blob)
        expiry_dates=available_expirations(doc)
    except Exception as exc:
        st.error(f'Fotografia non valida: {exc}')
        st.stop()
    if not expiry_dates:
        st.error('Nessuna scadenza NDX/NDXP riconosciuta: controllare il formato dei contratti.')
        st.stop()
    
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
        st.stop()
    
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
        return fetch_basis(target_day)
    
    def _calculate_and_store_basis():
        try:
            result=_cached_basis(day)
            st.session_state['ndx_basis_result']=result
            st.session_state['ndx_basis_value']=f"{result['basis']:.4f}"
            st.session_state.pop('ndx_basis_error',None)
        except Exception as exc:
            st.session_state.pop('ndx_basis_result',None)
            st.session_state['ndx_basis_error']=str(exc)[:240]
    
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
                                 'NQ=F può non coincidere con il contratto NQ di TradingView.')
    try:
        basis=float(basis_text.replace(',','.').strip()) if basis_text.strip() else None
        if basis is not None and not math.isfinite(basis):raise ValueError()
    except ValueError:
        st.error('Differenziale non numerico o non finito')
        st.stop()
    if st.session_state.get('ndx_basis_result'):
        res=st.session_state['ndx_basis_result']
        st.caption(f"Proposta automatica {res['basis']:+.2f} pt · seduta {res['reference_date']} · "
                   f"{res['bar_count']} barre comuni · min {res['minimum']:+.2f} / max {res['maximum']:+.2f}. "
                   'Verificare il contratto NQ utilizzato.')
    
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
        st.stop()
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
    
    st.subheader(f'NET GAMMA — NDX · fascia ±{band_pct:g}%')
    st.caption('Formula invariata: NET = [(OI+Volume)×Gamma] Call − [(OI+Volume)×Gamma] Put. '
               'Tutti gli strike Cboe disponibili tra '
               f'**{band_low:,.2f} e {band_high:,.2f} NDX** (±{band_pct:g}% dal close precedente). '
               'Stessa fascia prezzi e stessa scala Gamma per 0DTE e Weekly.')
    if basis is None:
        st.warning('Differenziale assente: vengono rappresentati gli strike NDX; esportazione NQ disabilitata.')
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
                source=st.session_state.get('ndx_name', ''))
            st.subheader(title)
            st.caption(source_details)
            st.caption(f'{group["contract_count"]} contratti · '
                       f'{group["available_strikes"]} strike disponibili · '
                       f'{group["selected_strikes"]} originali · '
                       f'{visual_notes[kind].get("extra", 0)} aggiuntivi solo grafica/Pine')
            _, capture_label = capture_display(
                doc.get('timestamp'), st.session_state.get('ndx_download_rome'),
                st.session_state.get('ndx_name', ''))
            fg = profile_chart(
                visual_profiles[kind]['rows'], 'NDX', reference,
                (spx_shared_gamma_bounds([visual_profiles[kind]], field='net_gamma')
                 if independent_scale else shared_gamma_range),
                shared_price_range, level_field='strike_index',
                gamma_field='net_gamma', price_shift=price_shift,
                ndx=True, show_close=basis is not None,
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
        st.stop()
    
    choices=[]
    if '0DTE' in visual_profiles: choices.append(('Solo 0DTE',{'0DTE':visual_profiles['0DTE']}))
    if 'Weekly' in visual_profiles: choices.append(('Solo Weekly',{'Weekly':visual_profiles['Weekly']}))
    if len(visual_profiles)==2: choices.append(('0DTE + Weekly',visual_profiles))
    # Le linee macro usano gli eventi già pubblicati dal calendario Finance Calendar,
    # con conversione in Europe/Rome; nessun orario inventato per news senza timestamp.
    try:
        with st.spinner('Verifica calendario macro USA...'):
            macro_news=events_for_pine(day)
        st.caption(f"News macro nel Pine: {len(macro_news)} orari distinti/registrazioni "
                   f"per il {day:%d/%m/%Y} · Fonte: [Finance Calendar]({MACRO_CREDITS}). "
                   "Le linee rosse/arancioni possono essere disattivate nei parametri Pine.")
    except Exception:
        macro_news=[]
        st.warning('Calendario macro USA temporaneamente non disponibile: '
                   'i Pine saranno esportati SENZA linee news, non con orari presunti.')
    exports=[]
    for title,data in choices:
        try:
            code=make_pine(data,basis,day,day.strftime('%d/%m'))
            if macro_news:
                code=append_news(code,macro_news)
            exports.append((title,code))
        except Exception as exc:
            st.error(f'{title}: {exc}')
    if exports:
        c=st.columns(len(exports))
        for column,(title,code) in zip(c,exports):
            with column:
                st.download_button(f'Scarica Pine · {title}',data=code.encode('utf-8'),
                                   file_name=f'NDX_NQ_{day:%Y%m%d}_{title.replace(" ","_")}.pine',
                                   mime='text/plain',on_click='ignore',use_container_width=True)
        with st.expander('Mostra codice Pine da copiare'):
            name=st.selectbox('Profilo', [x[0] for x in exports])
            st.code(dict(exports)[name],language='javascript')
    st.caption('I file Pine contengono gli strike statici della fotografia scelta. '
               'Per aggiornare il grafico, esporta nuovamente dopo una nuova fotografia.')
    
