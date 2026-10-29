"""Independent Streamlit prototype; does not share Supabase or GitHub with Serafini SPX."""
import csv
import io
import math
from datetime import datetime, date
from zoneinfo import ZoneInfo
import plotly.graph_objects as go
import streamlit as st

from markets import MARKETS
from data_sources import download_ndx, NDX_URL
from ndx_engine import (unpack_snapshot, available_expirations, close_from_payload,
                        profile, weekly_target, DEFAULT_BAND_PCT)
from ndx_basis import fetch_basis
from pine_export import make_pine
from macro_events import events_for_pine, CREDITS as MACRO_CREDITS
from pine_news_overlay import append_news
from nq_price_panel import load_nq_candles, chart_compare_nq

ROME=ZoneInfo('Europe/Rome')
st.set_page_config(page_title='Multi-Market NET GAMMA', layout='wide')
st.title('Multi-Market NET GAMMA')
st.caption('App separata da Serafini SPX · moduli NDX/NQ, GLD e USO · 6 mercati nel selettore')

market_key=st.selectbox('Sottostante', list(MARKETS.keys()),
                        format_func=lambda x: MARKETS[x].label)
market=MARKETS[market_key]
if market_key == 'GOLD':
    st.caption('Sottostante ETF GLD (USD) · Opzioni GLD Cboe · '
               'NON future CME GC · livelli soltanto GLD.')
elif market_key == 'WTI':
    st.caption('Sottostante ETF USO (USD) · Opzioni USO Cboe · '
               'NON future NYMEX CL/MCL · livelli soltanto USO.')
else:
    st.caption(f'Opzioni: {market.options} · Future: {market.futures} · Differenziale: {market.basis}')
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


st.subheader('Fotografia Cboe NDX')
col_a,col_b=st.columns([1,2],gap='large')
with col_a:
    if st.button('Leggi fotografia NDX da Cboe', type='primary'):
        try:
            with st.spinner('Acquisizione Cboe...'):
                raw=download_ndx()
                unpack_snapshot(raw)
            st.session_state['ndx_blob']=raw
            st.session_state['ndx_name']='NDX_CBOE_online.json'
            st.session_state['ndx_download_rome']=datetime.now(ROME).strftime('%d/%m/%Y %H:%M:%S Roma')
            st.success('Fotografia NDX ricevuta e verificata nella struttura.')
        except Exception as exc:
            st.error(f'Fonte live non disponibile: {str(exc)[:260]}')
with col_b:
    uploaded=st.file_uploader('Oppure importa un JSON Cboe NDX originale (.json, .gz)',
                              type=['json','gz'], key='ndx_upload')
    if uploaded is not None:
        content=uploaded.getvalue()
        if st.session_state.get('ndx_upload_tag') != (uploaded.name, len(content),hash(content)):
            try:
                unpack_snapshot(content)
                st.session_state['ndx_blob']=content
                st.session_state['ndx_name']=uploaded.name
                st.session_state['ndx_download_rome']=None
                st.session_state['ndx_upload_tag']=(uploaded.name,len(content),hash(content))
            except Exception as exc:
                st.error(f'File NDX non riconosciuto: {exc}')
st.caption(f'Sorgente: {NDX_URL} · l’orario del timestamp Cboe non viene convertito senza fuso dichiarato.')

blob=st.session_state.get('ndx_blob')
if not blob:
    st.info('Carica o acquisisci una fotografia NDX per attivare il calcolo.')
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

now=datetime.now(ROME).date()
non_past=[d for d in expiry_dates if d >= now]
default_exp=non_past[0] if non_past else expiry_dates[-1]
day=st.selectbox('Scadenza 0DTE / giornata analizzata',expiry_dates,
                 index=expiry_dates.index(default_exp),format_func=lambda x:x.strftime('%d/%m/%Y'))
if st.session_state.get('_ndx_basis_target') != day.isoformat():
    st.session_state['_ndx_basis_target']=day.isoformat()
    st.session_state['ndx_basis_value']=''
    st.session_state.pop('ndx_basis_result',None)
    st.session_state.pop('ndx_basis_error',None)
    st.session_state.pop('ndx_basis_attempted',None)
if day!=now:
    st.caption('La scadenza scelta non corrisponde a oggi a Roma: visualizzazione storica o di studio.')
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

# Stessa finestra di prezzo per 0DTE e Weekly, basata sul close indice precedente.
band_low = reference * (1 - band_pct / 100)
band_high = reference * (1 + band_pct / 100)
gamma_values = [r['net_gamma'] for group in profiles.values() for r in group['rows']]
gamma_min = min(0.0, min(gamma_values))
gamma_max = max(0.0, max(gamma_values))
gamma_span = max(gamma_max - gamma_min, 1e-8)
shared_gamma_range = [gamma_min - gamma_span * .06, gamma_max + gamma_span * .06]
price_shift = basis if basis is not None else 0.0
shared_price_range = [band_low + price_shift, band_high + price_shift]

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

cols=st.columns(len(profiles),gap='large')
for (kind,group),column in zip(profiles.items(),cols):
    with column:
        st.markdown(f'**{kind} · scadenza {group["expiry"]}**')
        st.caption(f'{group["contract_count"]} contratti · {group["available_strikes"]} strike disponibili '
                   f'· {group["selected_strikes"]} strike nella fascia ±{band_pct:g}%')
        rows=group['rows']
        y=[r['strike_index']+price_shift for r in rows]
        x=[r['net_gamma'] for r in rows]
        # Evita sovrapposizioni quando gli strike hanno passi inferiori a 5 punti.
        steps=[b-a for a,b in zip(y,y[1:]) if b>a]
        bar_width=min(3.8, min(steps)*0.8) if steps else 3.8
        fg=go.Figure()
        fg.add_trace(go.Bar(x=x,y=y,orientation='h',width=bar_width,
                            marker_color=['#22c55e' if value>=0 else '#ef4444' for value in x],
                            customdata=[[r['strike_index'],r['call_gamma'],r['put_gamma']] for r in rows],
                            hovertemplate='Livello %{y:,.2f}<br>Strike NDX %{customdata[0]:,.2f}<br>NET %{x:+.4f}<br>Call %{customdata[1]:.4f}<br>Put %{customdata[2]:.4f}<extra></extra>'))
        fg.add_vline(x=0,line_color='#6b7280',line_width=1)
        if basis is not None:
            # Close NDX precedente + differenziale NQ−NDX; stessa linea in
            # entrambi i grafici. Non altera Gamma, strike o scala delle barre.
            fg.add_hline(y=previous_close_nq, line_dash='dash',
                         line_width=1.5, line_color='#f0cc65')
            fg.add_annotation(x=0.995, xref='paper',
                              y=previous_close_nq, yref='y',
                              text=f'Close prec. NQ {previous_close_nq:,.2f}',
                              showarrow=False, xanchor='right', yanchor='bottom',
                              font=dict(color='#f0cc65',size=11),
                              bgcolor='rgba(13,17,23,0.85)',borderpad=2)
        fg.update_layout(height=760,margin=dict(l=10,r=10,b=25,t=15),
                         template='plotly_dark',showlegend=False,
                         xaxis=dict(title='NET gamma · unità formula sperimentale',
                                    range=shared_gamma_range, zeroline=True),
                         yaxis=dict(title='Prezzo NQ' if basis is not None else 'Strike NDX',
                                    range=shared_price_range, autorange=False),
                         bargap=0.1)
        st.plotly_chart(fg,use_container_width=True)

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
if '0DTE' in profiles: choices.append(('Solo 0DTE',{'0DTE':profiles['0DTE']}))
if 'Weekly' in profiles: choices.append(('Solo Weekly',{'Weekly':profiles['Weekly']}))
if len(profiles)==2: choices.append(('0DTE + Weekly',profiles))
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
