"""Intentional no-storage adapter for Multi-Market V2.

This module MUST NOT import Supabase or read any Supabase secret.
Archive selection stays disabled until an owner-approved, separate
storage backend is configured. Historic SPX and V1 buckets untouched.
"""
import streamlit as st


def archive_panel(symbol: str):
    with st.expander("RILEVAMENTI CBOE · 07:30 / 15:50 / 20:30", expanded=False):
        st.caption(
            "V2: pipeline e cronjob predisposti, acquisizioni non operative "
            "senza una fonte dati autorizzata e un archivio privato indipendente."
        )
        st.info("Accesso a Supabase disattivato. I file Cboe possono "
                "essere acquisiti manualmente e analizzati senza archivio online.")
    return None
