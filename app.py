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
                        profile, weekly_target)
from ndx_basis import fetch_basis
from pine_export import make_pine

ROME=ZoneInfo('Europe/Rome')
st.set_page_config(page_title='Multi-Market NET GAMMA', layout='wide')
st.title('Multi-Market NET GAMMA')
st.caption('App separata da Serafini SPX · primo modulo NDX/NQ · 6 mercati nel selettore')

market_key=st.selectbox('Sottostante', list(MARKETS.keys()),
                        format_func=lambda x: MARKETS[x].label)
market=MARKETS[market_key]
st.caption(f'Opzioni: {market.options} · Future: {market.futures} · Differenziale: {market.basis}')
if not market.enabled:
    st.info(f'{market.label}: modulo predisposto, non ancora operativo. {market.info} '
            'Nessun livello sarà simulato senza una catena opzioni validata.')
    st.stop()

st.warning('**NDX in validazione:** la formula e la selezione 25+25 strike sono una replica '
           'sperimentale del metodo SPX. Non sono ancora state validate per NDX. '
           'Dati Cboe differiti; non costituiscono un segnale operativo.')

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
if day!=now:
    st.caption('La scadenza scelta non corrisponde a oggi a Roma: visualizzazione storica o di studio.')
weekly_default=weekly_target(day,expiry_dates)
fridays=[x for x in expiry_dates if x.weekday()==4 and x>=day and x!=day]
weekly_exp=st.selectbox('Scadenza Weekly (solo scadenze venerdì realmente presenti)',
                         [None]+fridays,
                         index=fridays.index(weekly_default)+1 if weekly_default in fridays else 0,
                         format_func=lambda x: 'Non disponibile' if x is None else x.strftime('%d/%m/%Y'))

if st.button('Calcola differenziale automatico NQ−NDX (Yahoo 15m)'):
    try:
        with st.spinner('Calcolo chiusure sincronizzate della seduta precedente...'):
            result=fetch_basis(day)
        st.session_state['ndx_basis_result']=result
        st.session_state['ndx_basis_value']=f"{result['basis']:.4f}"
    except Exception as exc:
        st.warning(f'Calcolo automatico non disponibile: {str(exc)[:240]}. Puoi inserire un valore verificato.')
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

profiles={}
for kind,exp in [('0DTE',day),('Weekly',weekly_exp)]:
    if exp is None:continue
    try:
        profiles[kind]=profile(doc,exp,reference)
    except Exception as exc:
        st.warning(f'{kind}: {exc}')
if not profiles:
    st.error('Nessun profilo completo 25+25. Nessun NET GAMMA né Pine viene generato.')
    st.stop()

st.subheader('NET GAMMA — NDX · replica sperimentale')
st.caption('Formula: NET = [(OI+Volume)×Gamma] Call − [(OI+Volume)×Gamma] Put; '
           '50 strike (25 sopra e 25 sotto la chiusura NDX). Non equivale al GEX monetario.')
if basis is None:
    st.warning('Differenziale assente: vengono rappresentati gli strike NDX; esportazione NQ disabilitata.')

cols=st.columns(len(profiles),gap='large')
for (kind,group),column in zip(profiles.items(),cols):
    with column:
        st.markdown(f'**{kind} · scadenza {group["expiry"]}**')
        st.caption(f'{group["contract_count"]} contratti · {group["available_strikes"]} strike disponibili · 50 selezionati')
        rows=group['rows']
        y=[r['strike_index']+(basis or 0) for r in rows]
        x=[r['net_gamma'] for r in rows]
        fg=go.Figure()
        fg.add_trace(go.Bar(x=x,y=y,orientation='h',width=3.8,
                            marker_color=['#22c55e' if value>=0 else '#ef4444' for value in x],
                            customdata=[[r['strike_index'],r['call_gamma'],r['put_gamma']] for r in rows],
                            hovertemplate='Livello %{y:,.2f}<br>Strike NDX %{customdata[0]:,.2f}<br>NET %{x:+.4f}<br>Call %{customdata[1]:.4f}<br>Put %{customdata[2]:.4f}<extra></extra>'))
        fg.add_vline(x=0,line_color='#6b7280',line_width=1)
        fg.update_layout(height=760,margin=dict(l=10,r=10,b=25,t=15),
                         template='plotly_dark',showlegend=False,
                         xaxis_title='NET gamma · unità formula sperimentale',
                         yaxis_title='Prezzo NQ' if basis is not None else 'Strike NDX',
                         bargap=0.1)
        st.plotly_chart(fg,use_container_width=True)

st.subheader('Esportazione Pine Script v6')
if basis is None:
    st.info('Inserisci il differenziale NQ–NDX per esportare gli strike sul grafico NQ.')
    st.stop()

choices=[]
if '0DTE' in profiles: choices.append(('Solo 0DTE',{'0DTE':profiles['0DTE']}))
if 'Weekly' in profiles: choices.append(('Solo Weekly',{'Weekly':profiles['Weekly']}))
if len(profiles)==2: choices.append(('0DTE + Weekly',profiles))
exports=[]
for title,data in choices:
    try:
        code=make_pine(data,basis,day,day.strftime('%d/%m'))
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
