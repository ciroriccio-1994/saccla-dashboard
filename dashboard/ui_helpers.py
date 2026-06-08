from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st


SESSION_DEFAULTS = {
    "authenticated_dashboard": False,
    "cf_username": "",
    "cf_company": "",
    "cf_password": "",
    "cf_session_ready": False,
    "cf_vehicles": [],
}

SEVERITY_LABELS = {
    "critical": "Critica",
    "high": "Alta",
    "medium": "Media",
    "low": "Bassa",
    "info": "Informativa",
    "ok": "OK",
}
EVENT_TYPE_LABELS = {
    "load": "Carico/Programmazione",
    "unload": "Scarico",
    "unloading": "Scarico",
    "stop_or_pause": "Pausa/Sosta",
    "stop": "Sosta",
    "operation": "Operazione",
    "alarm": "Allarme",
    "door_opening": "Apertura portellone",
    "portellone": "Portellone",
    "valve_opening": "Apertura valvola",
    "valvole": "Valvole",
    "coupler_opening": "Apertura accoppiatore",
}
LOCATION_TYPE_LABELS = {
    "parking": "Parcheggio",
    "refinery": "Raffineria",
    "depot": "Deposito",
    "gas_station": "Pompa di benzina",
    "workshop": "Officina",
    "service_area": "Area di servizio",
    "suspicious": "Zona sospetta",
    "road_or_highway": "Autostrada/Tangenziale",
    "unknown": "Sconosciuto",
}


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {
            --cf-bg: #f8fafb;
            --cf-card: #ffffff;
            --cf-border: #e8edf2;
            --cf-text: #0f1923;
            --cf-muted: #64748b;
            --cf-green: #16a34a;
            --cf-green-light: #dcfce7;
            --cf-green-mid: #bbf7d0;
            --cf-red: #dc2626;
            --cf-red-light: #fee2e2;
            --cf-red-mid: #fecaca;
            --cf-orange: #ea580c;
            --cf-orange-light: #ffedd5;
            --cf-yellow: #ca8a04;
            --cf-yellow-light: #fef9c3;
            --cf-accent: #15803d;
        }

        * { font-family: 'Inter', sans-serif; }
        .stApp { background: var(--cf-bg); color: var(--cf-text); }
        .block-container { max-width: 1500px; padding: 1.75rem 2.1rem 3rem; }
        h1, h2, h3 { color: var(--cf-text); letter-spacing: -.01em; }

        /* Sidebar */
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--cf-border);
        }
        [data-testid="stSidebar"] .block-container { padding: 1.3rem 1rem; }
        [data-testid="stSidebar"] details {
            border: 1px solid var(--cf-border);
            border-radius: 10px;
            background: #fbfcfe;
            margin-bottom: .65rem;
        }

        /* Forms */
        [data-testid="stForm"] {
            background: var(--cf-card);
            border: 1px solid var(--cf-border);
            border-radius: 14px;
            padding: 1.35rem 1.4rem;
            box-shadow: 0 4px 20px rgba(0,0,0,.05);
        }

        /* Login */
        .cf-login-shell {
            max-width: 480px;
            margin: 6vh auto 1rem;
            text-align: center;
        }
        .cf-login-logo {
            width: 56px; height: 56px;
            background: var(--cf-green);
            border-radius: 16px;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 1.6rem;
            margin-bottom: .9rem;
            box-shadow: 0 4px 18px rgba(22,163,74,.3);
        }
        .cf-login-brand {
            display: block;
            color: var(--cf-accent);
            font-weight: 800;
            font-size: .8rem;
            text-transform: uppercase;
            letter-spacing: .12em;
            margin-bottom: .3rem;
        }
        .cf-login-shell h1 { margin: .4rem 0 .3rem; font-size: 1.85rem; }
        .cf-login-shell p { margin: 0 0 1.5rem; color: var(--cf-muted); font-size: .92rem; }
        .cf-security-note {
            margin-top: .8rem;
            color: var(--cf-muted);
            font-size: .8rem;
        }

        /* Page header */
        .cf-page-header {
            display: flex;
            justify-content: space-between;
            gap: 1.5rem;
            align-items: flex-start;
            background: var(--cf-card);
            border: 1px solid var(--cf-border);
            border-left: 4px solid var(--cf-green);
            border-radius: 14px;
            padding: 1.4rem 1.55rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 18px rgba(0,0,0,.04);
        }
        .cf-page-header h1 { margin: 0; font-size: 1.85rem; line-height: 1.2; }
        .cf-page-header p { margin: .4rem 0 0; color: var(--cf-muted); font-size: .9rem; }
        .cf-header-meta { text-align: right; color: var(--cf-muted); font-size: .8rem; line-height: 1.7; }
        .cf-header-meta strong { color: var(--cf-text); }

        /* KPI Cards */
        .cf-kpi-card {
            --accent: var(--cf-green);
            background: var(--cf-card);
            border: 1px solid var(--cf-border);
            border-top: 4px solid var(--accent);
            border-radius: 12px;
            padding: 1.1rem 1.15rem;
            min-height: 130px;
            box-shadow: 0 4px 16px rgba(0,0,0,.045);
        }
        .cf-kpi-top { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
        .cf-kpi-icon {
            width: 36px; height: 36px; display: grid; place-items: center;
            border-radius: 10px;
            background: color-mix(in srgb, var(--accent) 12%, white);
            font-size: 1rem;
        }
        .cf-kpi-title { color: var(--cf-muted); font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
        .cf-kpi-value { color: var(--cf-text); font-size: 2.1rem; font-weight: 800; margin-top: .6rem; line-height: 1; }
        .cf-kpi-help { color: var(--cf-muted); font-size: .77rem; margin-top: .5rem; }

        /* Section header */
        .cf-section-header { margin: 1.2rem 0 .7rem; }
        .cf-section-header h3 { margin: 0; font-size: 1rem; font-weight: 700; }
        .cf-section-header p { margin: .2rem 0 0; color: var(--cf-muted); font-size: .84rem; }

        /* Status strip */
        .cf-status-strip {
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem;
            background: var(--cf-card); border: 1px solid var(--cf-border); border-radius: 12px;
            padding: .9rem 1rem; margin-bottom: 1rem;
        }
        .cf-status-item { color: var(--cf-muted); font-size: .75rem; font-weight: 500; }
        .cf-status-item strong { display: block; color: var(--cf-text); font-size: .87rem; margin-top: .15rem; font-weight: 700; }

        /* Badges */
        .cf-badge {
            display: inline-flex; align-items: center; border-radius: 999px;
            padding: .22rem .6rem; font-size: .71rem; font-weight: 700; letter-spacing: .03em;
        }

        /* OK / anomalia row highlight */
        .cf-row-ok { background: #f0fdf4 !important; }
        .cf-row-error { background: #fef2f2 !important; }

        /* Alert banner */
        .cf-alert-ok {
            background: var(--cf-green-light);
            border: 1px solid var(--cf-green-mid);
            border-left: 4px solid var(--cf-green);
            border-radius: 10px;
            padding: .8rem 1rem;
            color: #14532d;
            font-weight: 600;
            font-size: .88rem;
            margin: .5rem 0;
        }
        .cf-alert-error {
            background: var(--cf-red-light);
            border: 1px solid var(--cf-red-mid);
            border-left: 4px solid var(--cf-red);
            border-radius: 10px;
            padding: .8rem 1rem;
            color: #7f1d1d;
            font-weight: 600;
            font-size: .88rem;
            margin: .5rem 0;
        }

        /* Empty state */
        .cf-empty {
            text-align: center; padding: 2.5rem; background: #fff;
            border: 1px dashed #cbd5e1; border-radius: 12px; color: var(--cf-muted);
        }

        /* Tables */
        div[data-testid="stDataFrame"] {
            background: #fff; border: 1px solid var(--cf-border);
            border-radius: 10px; padding: .25rem; box-shadow: 0 2px 10px rgba(0,0,0,.03);
        }
        div[data-testid="stPlotlyChart"] {
            background: #fff; border: 1px solid var(--cf-border);
            border-radius: 12px; padding: .35rem; box-shadow: 0 3px 14px rgba(0,0,0,.04);
        }

        /* Buttons */
        .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] button {
            border-radius: 9px; border: 1px solid #d1d5db; font-weight: 600; min-height: 2.5rem;
        }
        .stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button {
            background: var(--cf-green); color: white; border-color: var(--cf-green);
        }
        .stButton > button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover {
            background: var(--cf-accent); border-color: var(--cf-accent);
        }

        /* Tabs */
        div[data-baseweb="tab-list"] {
            gap: .2rem; background: #fff; padding: .3rem;
            border: 1px solid var(--cf-border); border-radius: 11px;
            box-shadow: 0 2px 10px rgba(0,0,0,.03);
        }
        button[data-baseweb="tab"] { border-radius: 8px; padding-left: .8rem; padding-right: .8rem; font-weight: 500; }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: var(--cf-green-light) !important;
            color: var(--cf-accent) !important;
            font-weight: 700 !important;
        }

        hr { border-color: var(--cf-border); margin: 1.3rem 0; }

        @media (max-width: 900px) {
            .block-container { padding: 1rem; }
            .cf-page-header { display: block; }
            .cf-header-meta { text-align: left; margin-top: 1rem; }
            .cf-status-strip { grid-template-columns: 1fr 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, badge: str | None = None, meta: str | None = None) -> None:
    badge_html = f'<span class="cf-badge" style="background:#dcfce7;color:#15803d">{escape(badge)}</span>' if badge else ""
    meta_html = f'<div class="cf-header-meta">{escape(meta).replace(chr(10), "<br>")}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="cf-page-header">
          <div>{badge_html}<h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>
          {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(
    title: str,
    value: object,
    icon: str,
    color: str,
    help_text: str | None = None,
) -> None:
    st.markdown(
        f"""
        <div class="cf-kpi-card" style="--accent:{escape(color)}">
          <div class="cf-kpi-top">
            <div class="cf-kpi-title">{escape(title)}</div>
            <div class="cf-kpi-icon">{escape(icon)}</div>
          </div>
          <div class="cf-kpi-value">{escape(str(value))}</div>
          <div class="cf-kpi-help">{escape(help_text or "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_card(title: str, content: str = "") -> None:
    st.markdown(
        f'<div class="cf-section-header"><h3>{escape(title)}</h3><p>{escape(content)}</p></div>',
        unsafe_allow_html=True,
    )


def render_alert(message: str, ok: bool = True) -> None:
    css_class = "cf-alert-ok" if ok else "cf-alert-error"
    icon = "✅" if ok else "🚨"
    st.markdown(
        f'<div class="{css_class}">{icon} {escape(message)}</div>',
        unsafe_allow_html=True,
    )


def severity_badge(severity: str) -> str:
    key = str(severity or "info").lower()
    label = translate_severity(key)
    colors = {
        "critical": ("#fee2e2", "#b91c1c"),
        "high":     ("#ffedd5", "#c2410c"),
        "medium":   ("#fef9c3", "#854d0e"),
        "low":      ("#dcfce7", "#15803d"),
        "info":     ("#f1f5f9", "#475569"),
        "ok":       ("#dcfce7", "#15803d"),
    }
    background, foreground = colors.get(key, colors["info"])
    return f'<span class="cf-badge" style="background:{background};color:{foreground}">{escape(label)}</span>'


def translate_severity(severity: object) -> str:
    return SEVERITY_LABELS.get(str(severity or "info").lower(), str(severity or "Informativa"))


def translate_event_type(event_type: object) -> str:
    key = str(event_type or "")
    return EVENT_TYPE_LABELS.get(key, key or "Non disponibile")


def translate_location_type(location_type: object) -> str:
    key = str(location_type or "")
    return LOCATION_TYPE_LABELS.get(key, key or "Non disponibile")


def safe_dataframe(
    df: pd.DataFrame,
    column_mapping: dict[str, str] | None = None,
    *,
    hide_index: bool = True,
) -> None:
    if df is None or df.empty:
        render_empty_state("Nessun dato disponibile.")
        return
    shown = df.rename(columns=column_mapping or {})
    st.dataframe(shown, width="stretch", hide_index=hide_index)


def render_empty_state(message: str, icon: str = "ℹ️") -> None:
    st.markdown(
        f'<div class="cf-empty"><div style="font-size:1.5rem;margin-bottom:.5rem">{escape(icon)}</div><div>{escape(message)}</div></div>',
        unsafe_allow_html=True,
    )


def initialize_dashboard_session() -> None:
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_dashboard_session() -> None:
    adapter = st.session_state.get("cf_adapter")
    if adapter is not None:
        try:
            adapter.close()
        except Exception:
            pass
    for key in [
        "cf_password",
        "cf_username",
        "cf_company",
        "authenticated_dashboard",
        "cf_session_ready",
        "cf_vehicles",
        "cf_adapter",
    ]:
        st.session_state.pop(key, None)


def store_authenticated_session(
    username: str,
    company: str,
    password: str,
    vehicles: list[dict[str, Any]],
) -> None:
    st.session_state.authenticated_dashboard = True
    st.session_state.cf_username = username.strip()
    st.session_state.cf_company = company.strip()
    st.session_state.cf_password = password
    st.session_state.cf_session_ready = True
    st.session_state.cf_vehicles = vehicles
