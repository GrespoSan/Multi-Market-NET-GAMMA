"""Read-only ratio capture and Pine v6 exports for GC/MGC and CL/MCL.

Freeze an exactly time-matched pair once per original Cboe snapshot;
never substitute the previous daily close or fake synchronized prices.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from etf_future_pine import ASSETS, make_etf_future_pine
from future_ratio import CONTRACTS, AUTO_OIL_CONTRACT, choose_contract, fetch_pair, fetch_gold_pair, fetch_oil_pair, manual_pair


def _source_day(stamp, fallback):
    try:
        d = date.fromisoformat(str(stamp)[:10])
        return d, True
    except (ValueError, TypeError):
        return fallback, False


def prepare_locked_chart_mapping(symbol):
    """Reuse the snapshot-locked ratio from Pine for on-screen future plots.

    Called before charts; zero widgets and at most one acquisition per
    snapshot+contract. No assumed prices or silent fallback to ETF strikes.
    """
    if symbol not in ("GLD", "USO"):
        return None
    prefix = symbol.lower() + "_cboe_"
    if symbol == "USO" and not st.session_state.get("uso_auto_roll_initialized"):
        st.session_state["uso_ratio_contract"] = AUTO_OIL_CONTRACT
        st.session_state["uso_auto_roll_initialized"] = True
    selections = ([AUTO_OIL_CONTRACT] + list(CONTRACTS[symbol]["contracts"])
                  if symbol == "USO" else list(CONTRACTS[symbol]["contracts"]))
    selected = st.session_state.get(f"{symbol.lower()}_ratio_contract", selections[0])
    if selected not in selections:
        st.session_state[f"{symbol.lower()}_ratio_contract"] = selections[0]
        selected = selections[0]
    is_auto = symbol == "USO" and selected == AUTO_OIL_CONTRACT
    tv_symbol = "CL automatico" if is_auto else choose_contract(symbol, selected)[1]
    try:
        captured = datetime.fromisoformat(str(st.session_state.get(prefix + "import_rome")))
        if captured.tzinfo is None:
            raise ValueError("Timezone assente")
        snapshot_day = captured.astimezone(ZoneInfo("America/New_York")).date()
    except (ValueError, TypeError):
        st.session_state[f"{symbol.lower()}_ratio_error"] = (
            "Ora della fotografia Cboe senza fuso verificabile")
        return None
    source_sha = st.session_state.get(prefix + "sha256", "")
    version = "gold_capture_v2" if symbol == "GLD" else "oil_capture_v2"
    token = f"{version}|{source_sha}|{snapshot_day.isoformat()}|{captured.isoformat()}|{tv_symbol}"
    state_key, tried_key, error_key = (
        f"{symbol.lower()}_ratio_locked",
        f"{symbol.lower()}_ratio_tried",
        f"{symbol.lower()}_ratio_error")
    locked = st.session_state.get(state_key)
    if locked and locked.get("_token") == token:
        return locked
    if locked:
        st.session_state.pop(state_key, None)
    if st.session_state.get(tried_key) == token:
        return None
    st.session_state[tried_key] = token
    try:
        try:
            api_key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
        except Exception:
            api_key = ""
        pair = (fetch_gold_pair(selected, captured, api_key)
                if symbol == "GLD" else fetch_oil_pair(selected, captured, api_key))
        pair["_token"] = token
        st.session_state[state_key] = pair
        st.session_state.pop(error_key, None)
        return pair
    except Exception as exc:
        st.session_state[error_key] = str(exc)[:320]
        return None


def render_etf_pine_exports(symbol, calculated, reference, day,
                            source_sha=None, cboe_stamp=None):
    if symbol not in ASSETS:
        raise ValueError("Modulo Pine non supportato.")
    # Read optional snapshot metadata from the Streamlit session, keeping the
    # public 4-argument interface backward compatible with live page reloads.
    prefix = symbol.lower() + "_cboe_"
    if source_sha is None:
        source_sha = st.session_state.get(prefix + "sha256", "")
    if cboe_stamp is None:
        cboe_stamp = st.session_state.get(prefix + "timestamp")
    market = ASSETS[symbol]["label"]
    st.subheader(f"Esportazione Pine Script v6 · {market}")
    st.caption("Fonte dei Gamma: opzioni ETF Cboe, NON opzioni sui futures. "
               "Trasposizione del SOLO PREZZO degli strike, senza alterare NET GAMMA.")
    if symbol == "GLD":
        st.caption("I livelli trasferiti sono una proiezione indicativa degli strike "
                   "ETF, non livelli ricavati dalle opzioni native COMEX.")
    else:
        st.warning("La proiezione ETF → future è indicativa, non una resistenza o un "
                   "supporto certificato dalle opzioni native CME/NYMEX.")

    usable = {k: v for k, v in calculated.items()
              if k in ("0DTE", "Principale", "Weekly") and v.get("usable") and v.get("rows")}
    if not usable:
        st.info("Esportazione Pine non disponibile: serve almeno un profilo Cboe valido.")
        return

    today_ny = datetime.now(ZoneInfo("America/New_York")).date()
    snapshot_day, date_from_source = _source_day(cboe_stamp, today_ny)
    capture_time = st.session_state.get(prefix + "import_rome")
    if symbol in ("GLD", "USO"):
        # Original Cboe timestamp lacks timezone; use verified acquisition time.
        try:
            capture_dt = datetime.fromisoformat(str(capture_time))
            if capture_dt.tzinfo is None:
                raise ValueError()
            snapshot_day = capture_dt.astimezone(ZoneInfo("America/New_York")).date()
        except (ValueError, TypeError):
            capture_dt = None
        if capture_dt is None:
            st.warning(f"{symbol}: ora di acquisizione con fuso non verificabile. "
                       "Nessun rapporto automatico può essere bloccato.")
        product = "GC" if symbol == "GLD" else "CL"
        st.caption(f"{symbol}→{product}: prezzi della stessa barra da 5 minuti "
                   "completata prima della fotografia Cboe, anche se appartiene "
                   "alla precedente seduta ETF USA. Nessuna anticipazione dei prezzi.")
    else:
        capture_dt = None
        if not date_from_source:
            st.warning("Timestamp Cboe non interpretabile: per l'allineamento si usa "
                       "la data odierna di New York, NON un istante Cboe accertato.")
        st.caption(f"Data della fotografia Cboe: {snapshot_day:%d/%m/%Y} "
                   "(la timezone del timestamp originale non è dichiarata). "
                   "I prezzi ETF e future devono avere lo STESSO timestamp.")

    selections = ([AUTO_OIL_CONTRACT] + list(CONTRACTS[symbol]["contracts"])
                  if symbol == "USO" else list(CONTRACTS[symbol]["contracts"]))
    # One-time migration of the pre-automatic V2 session, preserving any
    # manual override that the user makes after this version is loaded.
    if symbol == "USO" and not st.session_state.get("uso_auto_roll_initialized"):
        st.session_state["uso_ratio_contract"] = AUTO_OIL_CONTRACT
        st.session_state["uso_auto_roll_initialized"] = True
    selected = st.selectbox("Contratto future da usare come riferimento",
                            selections, key=f"{symbol.lower()}_ratio_contract")
    is_auto = symbol == "USO" and selected == AUTO_OIL_CONTRACT
    yahoo_symbol, tv_symbol = (("Massive CL", "CL automatico")
                               if is_auto else choose_contract(symbol, selected))
    product = "GC" if symbol == "GLD" else "CL"
    if is_auto:
        st.caption("CL: selezione automatica fra le prime due scadenze tramite "
                   "il volume della seduta precedente alla fotografia Cboe. "
                   "Il contratto scelto verrà mostrato con il rapporto. "
                   "Puoi disattivare l'automatismo dal menu.")
    else:
        st.caption(f"Contratto {product} di riferimento: {tv_symbol}; "
                   f"prezzi future Massive e {symbol} Yahoo, barra 5m sincronizzata. "
                   "Il rapporto resta specifico del contratto selezionato.")

    state_key = f"{symbol.lower()}_ratio_locked"
    tried_key = f"{symbol.lower()}_ratio_tried"
    error_key = f"{symbol.lower()}_ratio_error"
    capture_id = capture_dt.isoformat() if capture_dt is not None else ""
    snapshot_token = (
        f"gold_capture_v2|{source_sha}|{snapshot_day.isoformat()}|{capture_id}|{tv_symbol}"
        if symbol == "GLD" else
        f"oil_capture_v2|{source_sha}|{snapshot_day.isoformat()}|{capture_id}|{tv_symbol}"
    )
    result = st.session_state.get(state_key)
    if result and result.get("_token") != snapshot_token:
        st.session_state.pop(state_key, None)
        result = None

    retry_label = ("Riprova calcolo rapporto GLD → GC" if symbol == "GLD"
                   else "Riprova calcolo rapporto USO → CL")
    do_retry = st.button(retry_label, key=f"{symbol.lower()}_ratio_retry")
    # One automatic attempt per unique snapshot + dated futures contract,
    # never on every Streamlit rerun. A failure does not invent a ratio.
    if st.session_state.get(tried_key) != snapshot_token or do_retry:
        st.session_state[tried_key] = snapshot_token
        try:
            with st.spinner(f"Confronto barre chiuse ETF {symbol} e {tv_symbol} a 5 minuti..."):
                if symbol == "GLD":
                    if capture_dt is None:
                        raise ValueError("Ora di acquisizione GLD non verificabile.")
                    try:
                        api_key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
                    except Exception:
                        api_key = ""
                    pair = fetch_gold_pair(selected, capture_dt, api_key)
                else:
                    if capture_dt is None:
                        raise ValueError("Ora di acquisizione USO non verificabile.")
                    try:
                        api_key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
                    except Exception:
                        api_key = ""
                    pair = fetch_oil_pair(selected, capture_dt, api_key)
            pair["_token"] = snapshot_token
            st.session_state[state_key] = pair
            st.session_state.pop(error_key, None)
            result = pair
            if do_retry:
                st.rerun()
        except Exception as exc:
            st.session_state[error_key] = str(exc)[:320]
            if do_retry:
                st.session_state.pop(state_key, None)
                result = None

    if st.session_state.get(error_key) and not result:
        st.warning("Rapporto automatico non disponibile: " + st.session_state[error_key] +
                   ". Nessun Pine con livelli arbitrari viene generato.")

    with st.expander("Inserisci manualmente due prezzi allo stesso orario (alternativa)", expanded=False):
        st.caption("Utilizza questo metodo SOLO se hai verificato due prezzi ETF e future "
                   "alla stessa ora. La sincronizzazione è dichiarata da chi li inserisce, "
                   "non verificata automaticamente dall'app.")
        a, b, c = st.columns(3)
        with a:
            etf_manual = st.number_input(f"Prezzo {symbol} ETF", min_value=0.0,
                                          value=0.0, format="%.4f",
                                          key=f"{symbol.lower()}_manual_etf")
        with b:
            future_manual = st.number_input(f"Prezzo future {tv_symbol}",
                                             min_value=0.0, value=0.0, format="%.4f",
                                             key=f"{symbol.lower()}_manual_future")
        with c:
            time_manual = st.text_input("Ora New York HH:MM", value="15:30",
                                        key=f"{symbol.lower()}_manual_time")
        if st.button("Conferma e blocca coppia manuale",
                     key=f"{symbol.lower()}_ratio_manual"):
            try:
                if is_auto:
                    raise ValueError("Per inserire prezzi manuali, seleziona prima "
                                     "un contratto CL specifico nel menu.")
                pair = manual_pair(etf_manual, future_manual, symbol,
                                   selected, snapshot_day, time_manual)
                pair["_token"] = snapshot_token
                st.session_state[state_key] = pair
                st.session_state.pop(error_key, None)
                result = pair
                st.rerun()
            except Exception as exc:
                st.error(f"Coppia manuale non valida: {str(exc)[:250]}")

    if not result or result.get("_token") != snapshot_token:
        st.info("Per esportare serve un rapporto ETF/future bloccato, "
                "ottenuto da barre sincronizzate o da una coppia manuale dichiarata.")
        return

    ratio = float(result["ratio"])
    actual_contract = result["future_tv_symbol"]
    if symbol == "USO" and result.get("auto_contract"):
        a = result["auto_contract"]
        st.caption(f"Rollover automatico · seduta {a['reference_date']} · "
                   f"{a['front_ticker']}: {a['front_volume']:,} contratti; "
                   f"{a['second_ticker']}: {a['second_volume']:,} contratti. "
                   f"Selezionato **{actual_contract}**. "
                   "Riferimento per il grafico, non replica del portafoglio USO.")
    st.markdown(f"**Rapporto BLOCCATO {symbol} → {actual_contract}: {ratio:.8f}**")
    st.caption(f"ETF {result['etf_price']:,.4f} · Future {result['future_price']:,.4f} "
               f"· Barra {result['bar_ny']} (New York) · {result['source']}.")
    st.caption("Il rapporto resterà IDENTICO fino alla successiva acquisizione esplicita. "
               "Il Pine nasce in modalità Bloccato. Modalità Dinamico facoltativa "
               "nelle impostazioni TradingView: aggiorna soltanto con barre 5m chiuse "
               "e timestamp coincidenti, poi conserva l'ultimo rapporto valido.")

    main_key = "0DTE" if "0DTE" in usable else "Principale"
    choices = []
    if main_key in usable:
        choices.append((f"Solo {main_key}", {main_key: usable[main_key]}))
    if "Weekly" in usable:
        choices.append(("Solo Weekly", {"Weekly": usable["Weekly"]}))
    if main_key in usable and "Weekly" in usable:
        choices.append((f"{main_key} + Weekly", usable))

    exports = {}
    for title, selected_profiles in choices:
        try:
            exports[title] = make_etf_future_pine(
                symbol, selected_profiles, reference, day, title, result)
        except Exception as exc:
            st.warning(f"Esportazione {title} non disponibile: {str(exc)[:250]}")
    if not exports:
        return

    cols = st.columns(len(exports))
    for col, (title, script) in zip(cols, exports.items()):
        with col:
            file_part = title.replace(" ", "_").replace("+", "e")
            st.download_button(
                f"Scarica Pine · {title}",
                data=script.encode("utf-8"),
                file_name=f"{symbol}_{actual_contract.split(':')[-1]}_{day:%Y%m%d}_{file_part}.pine",
                mime="text/plain", on_click="ignore",
                use_container_width=True,
                key=f"{symbol.lower()}_pine_{file_part}",
            )
    with st.expander("Mostra codice Pine da copiare e incollare"):
        choice = st.selectbox("Pine da copiare", list(exports),
                              key=f"{symbol.lower()}_pine_choice")
        st.code(exports[choice], language="javascript")
    st.caption("Ogni Pine conserva i Gamma originali e il rapporto della fotografia. "
               "Verifica ticker e contratto futuro prima dell'utilizzo.")
