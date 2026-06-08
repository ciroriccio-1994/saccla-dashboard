from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from dashboard.auth import authenticate_clickandfind
from dashboard.location_manager import (
    LOCATION_TYPE_LABELS as MANAGER_LOCATION_TYPE_LABELS,
    LOCATION_TYPES,
    LocationAliasesError,
    add_location_alias,
    classify_test_location,
    delete_location_alias,
    load_location_aliases,
    update_location_alias,
)
from dashboard.rule_manager import (
    EVENT_TYPES as RULE_EVENT_TYPES,
    EVENT_TYPE_LABELS as RULE_EVENT_TYPE_LABELS,
    LOCATION_TYPES as RULE_LOCATION_TYPES,
    LOCATION_TYPE_LABELS as RULE_LOCATION_TYPE_LABELS,
    SEVERITIES as RULE_SEVERITIES,
    SEVERITY_LABELS as RULE_SEVERITY_LABELS,
    RulesConfigError,
    add_rule,
    delete_rule,
    disable_rule,
    enable_rule,
    load_rules,
    save_rules,
    test_all_rules_on_event,
    update_rule,
)
from dashboard.sync import sync_clickandfind_data, unique_vehicles, vehicle_codtrasp, vehicle_label
from dashboard.ui_helpers import (
    clear_dashboard_session,
    inject_custom_css,
    initialize_dashboard_session,
    render_empty_state,
    render_kpi_card,
    render_page_header,
    render_section_card,
    severity_badge,
    store_authenticated_session,
    translate_event_type,
    translate_location_type,
    translate_severity,
)
from reports.excel_report import (
    ANOMALY_LEVELS,
    anomaly_events,
    prepare_report_dataframe,
    summary_by_company,
    summary_by_event_type,
    summary_by_severity,
    summary_by_vehicle,
    top_risky_vehicles,
)
from storage.database import Database, resolve_database_path


SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
SEVERITY_LABELS = {
    "critical": "Critica",
    "high": "Alta",
    "medium": "Media",
    "low": "Bassa",
    "info": "Informativa",
}
SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high":     "#ea580c",
    "medium":   "#ca8a04",
    "low":      "#16a34a",
    "info":     "#16a34a",
}
EVENT_TYPE_LABELS = {
    "load": "Carico",
    "unload": "Scarico",
    "alarm": "Allarme",
    "stop_or_pause": "Sosta/Pausa",
    "portellone": "Portellone",
    "valvole": "Valvole",
    "quadro": "Quadro",
    "ciclo": "Ciclo",
    "speed_alarm": "Allarme velocita",
    "valve_opening": "Apertura valvola",
    "door_opening": "Apertura portellone",
    "coupler_opening": "Apertura accoppiatore",
    "residual_event": "Residuo",
    "programming": "Programmazione",
    "unloading": "Scarico",
    "stop": "Sosta",
}
SOURCE_LABELS = {
    "operations": "Operazioni",
    "alarms": "Allarmi",
    "loads_unloads": "Carichi/Scarichi",
    "tracking": "Tracciamento",
}
LOCATION_TYPE_LABELS = {
    "parking": "Parcheggio",
    "refinery": "Raffineria",
    "depot": "Deposito",
    "gas_station": "Pompa di benzina",
    "workshop": "Officina",
    "service_area": "Punto di servizio",
    "suspicious": "Sospetto",
    "road_or_highway": "Autostrada/Tangenziale",
    "unknown": "Sconosciuto",
    "parking_area": "Parcheggio",
    "suspicious_area": "Sospetto",
}
CONTROL_STATUS_LABELS = {
    "OK": "OK",
    "WARNING": "Attenzione",
    "HIGH_RISK": "Alto rischio",
    "CRITICAL": "Critico",
}
COLUMN_LABELS = {
    "event_id": "ID evento",
    "check_date": "Data controllo",
    "company": "Compagnia",
    "vehicle_id": "Mezzo",
    "codtrasp": "Codice trasportatore",
    "tractor_plate": "Targa trattore",
    "semitrailer_plate": "Targa semirimorchio",
    "tractor_id": "Trattore",
    "trailer_id": "Rimorchio",
    "event_type": "Tipo evento",
    "source_section": "Sezione",
    "timestamp_start": "Inizio",
    "timestamp_end": "Fine",
    "duration_minutes": "Durata minuti",
    "latitude": "Latitudine",
    "longitude": "Longitudine",
    "location_name": "Luogo",
    "location_type": "Tipo luogo",
    "severity": "Severita",
    "reasons": "Motivazioni",
    "rule_ids": "Regole",
    "explanations": "Spiegazioni",
    "suggested_actions": "Azioni suggerite",
    "suggested_action": "Azione suggerita",
    "risk_score": "Punteggio rischio",
    "control_status": "Stato controllo",
    "raw_text": "Dato grezzo",
    "raw_type": "Tipo grezzo",
    "raw_op": "Operazione grezza",
    "product": "Prodotto",
    "is_last_unload_for_product": "Ultimo scarico prodotto",
    "has_residual": "Residuo presente",
    "has_stop_on_residual": "Stop residuo",
    "has_stop_on_unload": "Stop scarico",
    "is_programming_like_load": "Carico/programmazione sospetta",
    "operation_duration_minutes": "Durata operativa minuti",
    "location_confidence": "Confidenza luogo",
    "location_rule_source": "Fonte classificazione luogo",
    "location_notes": "Note luogo",
    "esito": "Esito",
}
REPORT_PATH = Path("outputs/reports/clickandfind_real_check.xlsx")


st.set_page_config(page_title="SACCLA · Controllo Flotta", page_icon="🛢️", layout="wide")
load_dotenv()


def apply_style() -> None:
    inject_custom_css()


@st.cache_data(show_spinner=False)
def load_data(database_path: str) -> pd.DataFrame:
    df = Database(database_path).load_events()
    if df.empty:
        return df
    df = prepare_report_dataframe(df)
    df = ensure_columns(df)
    df["check_date"] = pd.to_datetime(df["check_date"], errors="coerce")
    df["timestamp_start"] = pd.to_datetime(df["timestamp_start"], errors="coerce")
    df["timestamp_end"] = pd.to_datetime(df["timestamp_end"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["risk_score"] = pd.to_numeric(df["risk_score"], errors="coerce").fillna(0)
    df["severity"] = df["severity"].fillna("info").astype(str).str.lower()
    return df


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "event_id": "",
        "check_date": pd.NaT,
        "company": "",
        "vehicle_id": "",
        "codtrasp": "",
        "tractor_plate": "",
        "semitrailer_plate": "",
        "event_type": "",
        "source_section": "",
        "timestamp_start": pd.NaT,
        "timestamp_end": pd.NaT,
        "duration_minutes": 0,
        "latitude": pd.NA,
        "longitude": pd.NA,
        "location_name": "",
        "location_type": "",
        "severity": "info",
        "reasons": "",
        "rule_ids": "",
        "explanations": "",
        "suggested_actions": "",
        "suggested_action": "",
        "risk_score": 0,
        "control_status": "OK",
        "raw_text": "",
        "product": "",
        "is_last_unload_for_product": False,
        "has_residual": False,
        "has_stop_on_residual": False,
        "has_stop_on_unload": False,
        "is_programming_like_load": False,
        "operation_duration_minutes": 0,
        "location_confidence": 0,
        "location_rule_source": "",
        "location_notes": "",
    }
    prepared = df.copy()
    for column, default in defaults.items():
        if column not in prepared.columns:
            prepared[column] = default
    return prepared


def italian_severity(value: object) -> str:
    return translate_severity(value)


def italian_event_type(value: object) -> str:
    return EVENT_TYPE_LABELS.get(str(value or ""), translate_event_type(value))


def italian_source(value: object) -> str:
    key = str(value or "")
    return SOURCE_LABELS.get(key, key or "Non disponibile")


def italian_location_type(value: object) -> str:
    return LOCATION_TYPE_LABELS.get(str(value or ""), translate_location_type(value))


def italian_status(value: object) -> str:
    key = str(value or "OK")
    return CONTROL_STATUS_LABELS.get(key, key)


def display_frame(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    shown = df.copy()
    if columns:
        existing = [column for column in columns if column in shown.columns]
        shown = shown[existing]
    if "severity" in shown.columns:
        shown["severity"] = shown["severity"].map(italian_severity)
    if "event_type" in shown.columns:
        shown["event_type"] = shown["event_type"].map(italian_event_type)
    if "source_section" in shown.columns:
        shown["source_section"] = shown["source_section"].map(italian_source)
    if "control_status" in shown.columns:
        shown["control_status"] = shown["control_status"].map(italian_status)
    if "location_type" in shown.columns:
        shown["location_type"] = shown["location_type"].map(italian_location_type)
    for column in [
        "is_last_unload_for_product",
        "has_residual",
        "has_stop_on_residual",
        "has_stop_on_unload",
        "is_programming_like_load",
    ]:
        if column in shown.columns:
            shown[column] = shown[column].map(lambda value: "Si" if dashboard_bool(value) else "No")
    return shown.rename(columns=COLUMN_LABELS)


def dashboard_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "s"}


def severity_badge_style(row: pd.Series) -> list[str]:
    severity = str(row.get("Severita", "")).lower()
    color = {
        "critica": "#fee2e2",
        "alta": "#ffedd5",
        "media": "#fef9c3",
        "informativa": "#dcfce7",
    }.get(severity, "#ffffff")
    return [f"background-color: {color}" for _ in row]


def excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    prepared = ensure_columns(df)
    anomalies = anomaly_events(prepared)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        prepared.to_excel(writer, sheet_name="Events", index=False)
        anomalies.to_excel(writer, sheet_name="Anomalies", index=False)
        prepared[prepared["severity"] == "critical"].to_excel(writer, sheet_name="Critical Anomalies", index=False)
        summary_by_company(prepared).to_excel(writer, sheet_name="Summary by Company", index=False)
        summary_by_vehicle(prepared).to_excel(writer, sheet_name="Summary by Vehicle", index=False)
        summary_by_event_type(prepared).to_excel(writer, sheet_name="Summary by Event Type", index=False)
        summary_by_severity(prepared).to_excel(writer, sheet_name="Summary by Severity", index=False)
    return output.getvalue()


def kpi_card(label: str, value: object, note: str = "", severity: str = "info") -> None:
    styles = {
        "critical": ("🚨", "#dc2626"),
        "high":     ("⚠️", "#ea580c"),
        "medium":   ("●",  "#ca8a04"),
        "info":     ("◆",  "#16a34a"),
        "ok":       ("✓",  "#16a34a"),
    }
    icon, color = styles.get(severity, styles["info"])
    render_kpi_card(label, value, icon, color, note)


def safe_multiselect(label: str, values: list, key: str, formatter=lambda value: value) -> list:
    values = [value for value in values if pd.notna(value)]
    return st.multiselect(label, values, default=values, format_func=formatter, key=key)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    valid_dates = df["check_date"].dropna()
    if valid_dates.empty:
        min_date = max_date = datetime.now().date()
    else:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()

    with st.sidebar.expander("🔎 Filtri dashboard", expanded=True):
        date_range = st.date_input(
            "Intervallo date",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="date_range",
        )
        start_date, end_date = date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (min_date, max_date)

        companies = sorted(df["company"].fillna("").unique())
        vehicles = sorted(df["vehicle_id"].fillna("").unique())
        codtrasp_values = sorted(df["codtrasp"].fillna("").astype(str).unique())
        severities = [severity for severity in SEVERITY_ORDER if severity in set(df["severity"].fillna("info"))]
        event_types = sorted(df["event_type"].fillna("").unique())
        source_sections = sorted(df["source_section"].fillna("").unique())

        selected_companies = safe_multiselect("Compagnia", companies, "companies")
        selected_vehicles = safe_multiselect("Mezzo / targa", vehicles, "vehicles")
        selected_codtrasp = safe_multiselect("Codice trasportatore", codtrasp_values, "codtrasp")
        selected_severities = safe_multiselect("Severita", severities, "severities", italian_severity)
        selected_event_types = safe_multiselect("Tipo evento", event_types, "event_types", italian_event_type)
        selected_sections = safe_multiselect("Sezione sorgente", source_sections, "sections", italian_source)
        only_anomalies = st.toggle("Solo anomalie", value=False, key="only_anomalies")

    mask = pd.Series(True, index=df.index)
    if not df["check_date"].dropna().empty:
        mask &= df["check_date"].dt.date.between(start_date, end_date)
    mask &= df["company"].fillna("").isin(selected_companies)
    mask &= df["vehicle_id"].fillna("").isin(selected_vehicles)
    mask &= df["codtrasp"].fillna("").astype(str).isin(selected_codtrasp)
    mask &= df["severity"].fillna("info").isin(selected_severities)
    mask &= df["event_type"].fillna("").isin(selected_event_types)
    mask &= df["source_section"].fillna("").isin(selected_sections)
    if only_anomalies:
        mask &= df["severity"].isin(ANOMALY_LEVELS)
    return df[mask].copy()


def chart_layout(fig, title: str, x_title: str | None = None, y_title: str | None = None):
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=380,
        margin=dict(l=24, r=24, t=64, b=36),
        legend_title_text="Legenda",
        font=dict(family="Inter, Arial, sans-serif", color="#344054"),
        title_font=dict(size=17, color="#172033"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hoverlabel=dict(bgcolor="#172033", font_color="#ffffff"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#e5eaf1")
    fig.update_yaxes(gridcolor="#eef1f5", zeroline=False)
    if x_title:
        fig.update_xaxes(title=x_title)
    if y_title:
        fig.update_yaxes(title=y_title)
    return fig


def render_map(map_df: pd.DataFrame) -> None:
    if map_df.empty:
        st.info("Nessun dato con latitudine e longitudine disponibile.")
        return
    try:
        plot_df = map_df.copy()
        plot_df["Severita"] = plot_df["severity"].map(italian_severity)
        plot_df["Tipo evento"] = plot_df["event_type"].map(italian_event_type)
        plot_df["Sezione"] = plot_df["source_section"].map(italian_source)
        map_kwargs = {
            "data_frame": plot_df,
            "lat": "latitude",
            "lon": "longitude",
            "color": "Severita",
            "hover_name": "vehicle_id",
            "hover_data": {
                "company": True,
                "Tipo evento": True,
                "Sezione": True,
                "location_name": True,
                "location_type": True,
                "latitude": ":.6f",
                "longitude": ":.6f",
            },
            "zoom": 5,
            "height": 560,
            "color_discrete_map": {
                "Critica": SEVERITY_COLORS["critical"],
                "Alta": SEVERITY_COLORS["high"],
                "Media": SEVERITY_COLORS["medium"],
                "Informativa": SEVERITY_COLORS["info"],
            },
        }
        if hasattr(px, "scatter_map"):
            fig = px.scatter_map(**map_kwargs)
            fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, width="stretch")
        elif hasattr(px, "scatter_mapbox"):
            fig = px.scatter_mapbox(**map_kwargs)
            fig.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("La visualizzazione mappa non e disponibile con la versione Plotly installata.")
            st.dataframe(display_frame(map_df), width="stretch", hide_index=True)
    except Exception as exc:
        st.warning(f"La mappa non puo essere visualizzata: {exc}")
        st.dataframe(display_frame(map_df), width="stretch", hide_index=True)


def render_downloads(filtered: pd.DataFrame) -> None:
    st.download_button(
        "Scarica CSV filtrato",
        data=display_frame(filtered).to_csv(index=False).encode("utf-8"),
        file_name="clickandfind_eventi_filtrati.csv",
        mime="text/csv",
        disabled=filtered.empty,
        key="download_csv",
    )
    st.download_button(
        "Scarica Excel filtrato",
        data=excel_bytes(filtered),
        file_name="clickandfind_eventi_filtrati.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=filtered.empty,
        key="download_excel",
    )
    if REPORT_PATH.exists():
        st.success(f"Report Excel disponibile: `{REPORT_PATH}`")
        st.download_button(
            "Scarica report Excel generato",
            data=REPORT_PATH.read_bytes(),
            file_name=REPORT_PATH.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_existing_report",
        )
    else:
        st.info(f"Report Excel non trovato in `{REPORT_PATH}`.")


def render_location_manager() -> None:
    render_section_card(
        "Gestione luoghi",
        "Configura alias, priorità e classificazione degli indirizzi operativi",
    )
    try:
        locations = load_location_aliases()["locations"]
    except LocationAliasesError as exc:
        st.error(str(exc))
        st.warning("Il file originale non e stato modificato. Correggere il YAML oppure ripristinare un backup.")
        return

    configured, add_new, edit_existing, test_location = st.tabs(
        ["Luoghi configurati", "Aggiungi nuovo luogo", "Modifica luogo esistente", "Test classificazione luogo"]
    )

    with configured:
        table = pd.DataFrame(locations)
        if table.empty:
            st.info("Nessun luogo configurato.")
        else:
            table["location_type"] = table["location_type"].map(
                lambda value: MANAGER_LOCATION_TYPE_LABELS.get(value, value)
            )
            table = table[["id", "match", "city", "location_type", "label", "notes", "active", "priority"]]
            table = table.rename(
                columns={
                    "id": "ID",
                    "match": "Stringa di ricerca",
                    "city": "Citta",
                    "location_type": "Tipo luogo",
                    "label": "Etichetta",
                    "notes": "Note",
                    "active": "Attivo",
                    "priority": "Priorita",
                }
            )
            st.dataframe(table, width="stretch", hide_index=True)
            st.download_button(
                "Scarica elenco luoghi CSV",
                data=table.to_csv(index=False).encode("utf-8"),
                file_name="clickandfind_location_aliases.csv",
                mime="text/csv",
                key="download_location_aliases",
            )

    with add_new:
        with st.form("add_location_alias_form", clear_on_submit=True):
            match = st.text_input("Stringa da cercare *", key="add_location_match")
            city = st.text_input("Citta", key="add_location_city")
            location_type = st.selectbox(
                "Tipo luogo *",
                LOCATION_TYPES,
                format_func=lambda value: MANAGER_LOCATION_TYPE_LABELS[value],
                key="add_location_type",
            )
            label = st.text_input("Etichetta *", key="add_location_label")
            notes = st.text_area("Note", key="add_location_notes")
            active = st.checkbox("Attivo", value=True, key="add_location_active")
            priority = int(
                st.number_input("Priorita", min_value=0, max_value=10000, value=100, step=1, key="add_location_priority")
            )
            submitted = st.form_submit_button("Aggiungi luogo")
        if submitted:
            try:
                add_location_alias(
                    match=match,
                    city=city,
                    location_type=location_type,
                    label=label,
                    notes=notes,
                    active=active,
                    priority=priority,
                )
                st.success("Luogo aggiunto correttamente. Backup YAML creato.")
                st.rerun()
            except LocationAliasesError as exc:
                st.error(str(exc))

    with edit_existing:
        if not locations:
            st.info("Non ci sono luoghi da modificare.")
        else:
            location_by_id = {location["id"]: location for location in locations}
            selected_id = st.selectbox(
                "Seleziona luogo",
                list(location_by_id),
                format_func=lambda alias_id: (
                    f"{location_by_id[alias_id]['label']} - {location_by_id[alias_id]['match']}"
                ),
                key="selected_location_alias",
            )
            selected = location_by_id[selected_id]
            form_key = f"edit_location_alias_form_{selected_id}"
            with st.form(form_key):
                edit_match = st.text_input("Stringa da cercare *", value=selected["match"])
                edit_city = st.text_input("Citta", value=selected["city"])
                edit_type = st.selectbox(
                    "Tipo luogo *",
                    LOCATION_TYPES,
                    index=LOCATION_TYPES.index(selected["location_type"]),
                    format_func=lambda value: MANAGER_LOCATION_TYPE_LABELS[value],
                )
                edit_label = st.text_input("Etichetta *", value=selected["label"])
                edit_notes = st.text_area("Note", value=selected["notes"])
                edit_active = st.checkbox("Attivo", value=selected["active"])
                edit_priority = int(
                    st.number_input(
                        "Priorita",
                        min_value=0,
                        max_value=10000,
                        value=int(selected["priority"]),
                        step=1,
                    )
                )
                save_changes = st.form_submit_button("Salva modifiche")
            if save_changes:
                try:
                    update_location_alias(
                        selected_id,
                        match=edit_match,
                        city=edit_city,
                        location_type=edit_type,
                        label=edit_label,
                        notes=edit_notes,
                        active=edit_active,
                        priority=edit_priority,
                    )
                    st.success("Modifiche salvate. Backup YAML creato.")
                    st.rerun()
                except LocationAliasesError as exc:
                    st.error(str(exc))

            action_col1, action_col2 = st.columns(2)
            if action_col1.button("Disattiva luogo", key=f"disable_location_{selected_id}", width="stretch"):
                try:
                    update_location_alias(
                        selected_id,
                        match=selected["match"],
                        city=selected["city"],
                        location_type=selected["location_type"],
                        label=selected["label"],
                        notes=selected["notes"],
                        active=False,
                        priority=selected["priority"],
                    )
                    st.success("Luogo disattivato.")
                    st.rerun()
                except LocationAliasesError as exc:
                    st.error(str(exc))

            confirm_delete = st.checkbox(
                "Confermo l'eliminazione definitiva del luogo selezionato",
                key=f"confirm_delete_location_{selected_id}",
            )
            if action_col2.button(
                "Elimina luogo",
                key=f"delete_location_{selected_id}",
                disabled=not confirm_delete,
                width="stretch",
            ):
                try:
                    delete_location_alias(selected_id)
                    st.success("Luogo eliminato. Backup YAML creato.")
                    st.rerun()
                except LocationAliasesError as exc:
                    st.error(str(exc))

    with test_location:
        test_text = st.text_input(
            "Testo o indirizzo da classificare",
            placeholder="Via Garibaldi Volla",
            key="location_classification_test",
        )
        if st.button("Testa classificazione", key="test_location_classification"):
            if not test_text.strip():
                st.warning("Inserire un testo da classificare.")
            else:
                try:
                    result = classify_test_location(test_text)
                    result_table = pd.DataFrame(
                        [
                            {
                                "Tipo luogo": MANAGER_LOCATION_TYPE_LABELS.get(
                                    result["location_type"], result["location_type"]
                                ),
                                "Etichetta": result["label"] or "N/D",
                                "Alias corrispondente": result["matched_alias_id"] or "Nessuno",
                                "Confidenza": f"{result['location_confidence']:.0%}",
                                "Fonte regola": result["location_rule_source"],
                                "Note": result["notes"] or "",
                            }
                        ]
                    )
                    st.dataframe(result_table, width="stretch", hide_index=True)
                except LocationAliasesError as exc:
                    st.error(str(exc))


def render_rule_manager() -> None:
    render_section_card(
        "Gestione regole",
        "Amministra condizioni, severità, soglie e simulazioni del motore operativo",
    )
    try:
        config = load_rules()
    except RulesConfigError as exc:
        st.error(str(exc))
        st.warning("Il file originale non e stato modificato. Correggere il YAML oppure ripristinare un backup.")
        return

    configured, add_new, edit_existing, thresholds_tab, test_rules = st.tabs(
        [
            "Regole configurate",
            "Aggiungi nuova regola",
            "Modifica regola esistente",
            "Soglie operative",
            "Test regole",
        ]
    )
    rules = config["rules"]

    with configured:
        rows = []
        for rule_id, rule in rules.items():
            rows.append(
                {
                    "ID regola": rule_id,
                    "Nome": rule["name_it"],
                    "Attiva": rule["enabled"],
                    "Severita": RULE_SEVERITY_LABELS.get(rule["severity"], rule["severity"]),
                    "Categoria": rule["category"],
                    "Tipi evento": ", ".join(
                        RULE_EVENT_TYPE_LABELS.get(value, value) for value in rule["event_types"]
                    ),
                    "Luoghi vietati": ", ".join(
                        RULE_LOCATION_TYPE_LABELS.get(value, value)
                        for value in rule["forbidden_location_types"]
                    ),
                    "Luoghi consentiti": ", ".join(
                        RULE_LOCATION_TYPE_LABELS.get(value, value)
                        for value in rule["allowed_location_types"]
                    ),
                    "Priorita": rule["priority"],
                    "Spiegazione": rule["explanation"],
                    "Azione suggerita": rule["suggested_action"],
                }
            )
        rules_table = pd.DataFrame(rows)
        if rules_table.empty:
            st.info("Nessuna regola configurata.")
        else:
            st.dataframe(rules_table, width="stretch", hide_index=True)
            st.download_button(
                "Scarica regole CSV",
                data=rules_table.to_csv(index=False).encode("utf-8"),
                file_name="clickandfind_regole.csv",
                mime="text/csv",
                key="download_rules_csv",
            )

    with add_new:
        with st.form("add_rule_form", clear_on_submit=True):
            new_id = st.text_input("ID regola *", key="new_rule_id")
            new_name = st.text_input("Nome italiano *", key="new_rule_name")
            new_enabled = st.checkbox("Attiva", value=True, key="new_rule_enabled")
            new_severity = st.selectbox(
                "Severita",
                RULE_SEVERITIES,
                format_func=lambda value: RULE_SEVERITY_LABELS[value],
                key="new_rule_severity",
            )
            new_category = st.text_input("Categoria", value="operational", key="new_rule_category")
            new_event_types = st.multiselect(
                "Tipi evento",
                RULE_EVENT_TYPES,
                format_func=lambda value: RULE_EVENT_TYPE_LABELS[value],
                key="new_rule_event_types",
            )
            new_allowed = st.multiselect(
                "Luoghi consentiti",
                RULE_LOCATION_TYPES,
                format_func=lambda value: RULE_LOCATION_TYPE_LABELS[value],
                key="new_rule_allowed",
            )
            new_forbidden = st.multiselect(
                "Luoghi vietati",
                RULE_LOCATION_TYPES,
                format_func=lambda value: RULE_LOCATION_TYPE_LABELS[value],
                key="new_rule_forbidden",
            )
            st.markdown("#### Condizioni")
            new_has_residual = _condition_selectbox("Residuo presente", "new_has_residual")
            new_stop_residual = _condition_selectbox("Stop sul residuo", "new_stop_residual")
            new_stop_unload = _condition_selectbox("Stop sullo scarico", "new_stop_unload")
            new_last_unload = _condition_selectbox("Ultimo scarico prodotto", "new_last_unload")
            new_raw_types = st.text_input("Raw type contiene (separati da virgola)", key="new_raw_types")
            new_raw_text = st.text_input("Raw text contiene (separati da virgola)", key="new_raw_text")
            new_duration = st.number_input(
                "Durata maggiore di minuti (0 = non impostata)",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key="new_duration",
            )
            new_explanation = st.text_area("Spiegazione *", key="new_rule_explanation")
            new_action = st.text_area("Azione suggerita *", key="new_rule_action")
            new_priority = int(
                st.number_input("Priorita", min_value=0, max_value=10000, value=100, step=1, key="new_rule_priority")
            )
            add_submitted = st.form_submit_button("Aggiungi regola")
        if add_submitted:
            try:
                add_rule(
                    new_id,
                    _rule_form_payload(
                        name_it=new_name,
                        enabled=new_enabled,
                        severity=new_severity,
                        category=new_category,
                        event_types=new_event_types,
                        allowed=new_allowed,
                        forbidden=new_forbidden,
                        has_residual=new_has_residual,
                        stop_residual=new_stop_residual,
                        stop_unload=new_stop_unload,
                        last_unload=new_last_unload,
                        raw_types=new_raw_types,
                        raw_text=new_raw_text,
                        duration=new_duration,
                        explanation=new_explanation,
                        action=new_action,
                        priority=new_priority,
                    ),
                )
                st.success("Regola aggiunta. Backup YAML creato.")
                st.rerun()
            except RulesConfigError as exc:
                st.error(str(exc))

    with edit_existing:
        if not rules:
            st.info("Non ci sono regole da modificare.")
        else:
            selected_id = st.selectbox(
                "Seleziona regola",
                list(rules),
                format_func=lambda rule_id: f"{rules[rule_id]['name_it']} - {rule_id}",
                key="selected_rule_id",
            )
            selected = rules[selected_id]
            conditions = selected.get("conditions", {})
            with st.form(f"edit_rule_form_{selected_id}"):
                edit_name = st.text_input("Nome italiano *", value=selected["name_it"])
                edit_enabled = st.checkbox("Attiva", value=selected["enabled"])
                edit_severity = st.selectbox(
                    "Severita",
                    RULE_SEVERITIES,
                    index=RULE_SEVERITIES.index(selected["severity"]),
                    format_func=lambda value: RULE_SEVERITY_LABELS[value],
                )
                edit_category = st.text_input("Categoria", value=selected["category"])
                edit_event_types = st.multiselect(
                    "Tipi evento",
                    RULE_EVENT_TYPES,
                    default=[value for value in selected["event_types"] if value in RULE_EVENT_TYPES],
                    format_func=lambda value: RULE_EVENT_TYPE_LABELS[value],
                )
                edit_allowed = st.multiselect(
                    "Luoghi consentiti",
                    RULE_LOCATION_TYPES,
                    default=[value for value in selected["allowed_location_types"] if value in RULE_LOCATION_TYPES],
                    format_func=lambda value: RULE_LOCATION_TYPE_LABELS[value],
                )
                edit_forbidden = st.multiselect(
                    "Luoghi vietati",
                    RULE_LOCATION_TYPES,
                    default=[value for value in selected["forbidden_location_types"] if value in RULE_LOCATION_TYPES],
                    format_func=lambda value: RULE_LOCATION_TYPE_LABELS[value],
                )
                edit_has_residual = _condition_selectbox(
                    "Residuo presente", f"edit_has_residual_{selected_id}", conditions.get("has_residual")
                )
                edit_stop_residual = _condition_selectbox(
                    "Stop sul residuo", f"edit_stop_residual_{selected_id}", conditions.get("has_stop_on_residual")
                )
                edit_stop_unload = _condition_selectbox(
                    "Stop sullo scarico", f"edit_stop_unload_{selected_id}", conditions.get("has_stop_on_unload")
                )
                edit_last_unload = _condition_selectbox(
                    "Ultimo scarico prodotto",
                    f"edit_last_unload_{selected_id}",
                    conditions.get("is_last_unload_for_product"),
                )
                edit_raw_types = st.text_input(
                    "Raw type contiene",
                    value=", ".join(conditions.get("raw_type_contains_any", [])),
                )
                edit_raw_text = st.text_input(
                    "Raw text contiene",
                    value=", ".join(conditions.get("raw_text_contains_any", [])),
                )
                edit_duration = st.number_input(
                    "Durata maggiore di minuti",
                    min_value=0.0,
                    value=_condition_numeric_value(
                        conditions.get("duration_greater_than_minutes"),
                        config.get("thresholds", {}),
                    ),
                    step=1.0,
                )
                edit_explanation = st.text_area("Spiegazione *", value=selected["explanation"])
                edit_action = st.text_area("Azione suggerita *", value=selected["suggested_action"])
                edit_priority = int(
                    st.number_input(
                        "Priorita",
                        min_value=0,
                        max_value=10000,
                        value=int(selected["priority"]),
                        step=1,
                    )
                )
                save_submitted = st.form_submit_button("Salva modifiche")
            if save_submitted:
                try:
                    update_rule(
                        selected_id,
                        _rule_form_payload(
                            name_it=edit_name,
                            enabled=edit_enabled,
                            severity=edit_severity,
                            category=edit_category,
                            event_types=edit_event_types,
                            allowed=edit_allowed,
                            forbidden=edit_forbidden,
                            has_residual=edit_has_residual,
                            stop_residual=edit_stop_residual,
                            stop_unload=edit_stop_unload,
                            last_unload=edit_last_unload,
                            raw_types=edit_raw_types,
                            raw_text=edit_raw_text,
                            duration=edit_duration,
                            explanation=edit_explanation,
                            action=edit_action,
                            priority=edit_priority,
                        ),
                    )
                    st.success("Regola aggiornata. Backup YAML creato.")
                    st.rerun()
                except RulesConfigError as exc:
                    st.error(str(exc))

            action_col1, action_col2 = st.columns(2)
            toggle_label = "Disattiva regola" if selected["enabled"] else "Riattiva regola"
            if action_col1.button(toggle_label, key=f"toggle_rule_{selected_id}", width="stretch"):
                try:
                    disable_rule(selected_id) if selected["enabled"] else enable_rule(selected_id)
                    st.success("Stato regola aggiornato.")
                    st.rerun()
                except RulesConfigError as exc:
                    st.error(str(exc))
            confirm_delete = st.checkbox(
                "Confermo l'eliminazione definitiva della regola",
                key=f"confirm_delete_rule_{selected_id}",
            )
            if action_col2.button(
                "Elimina regola",
                key=f"delete_rule_{selected_id}",
                disabled=not confirm_delete,
                width="stretch",
            ):
                try:
                    delete_rule(selected_id)
                    st.success("Regola eliminata. Backup YAML creato.")
                    st.rerun()
                except RulesConfigError as exc:
                    st.error(str(exc))

    with thresholds_tab:
        current_thresholds = config.get("thresholds", {})
        with st.form("rule_thresholds_form"):
            washing_threshold = st.number_input(
                "Durata possibile lavaggio (minuti)",
                min_value=0.0,
                value=float(current_thresholds.get("suspected_washing_duration_minutes", 5)),
                step=1.0,
            )
            long_pause = st.number_input(
                "Pausa lunga (minuti)",
                min_value=0.0,
                value=float(current_thresholds.get("long_pause_minutes", 30)),
                step=1.0,
            )
            min_pause = st.number_input(
                "Pausa minima (minuti)",
                min_value=0.0,
                value=float(current_thresholds.get("min_pause_minutes", 5)),
                step=1.0,
            )
            save_thresholds = st.form_submit_button("Salva soglie")
        if save_thresholds:
            config["thresholds"] = {
                "suspected_washing_duration_minutes": washing_threshold,
                "long_pause_minutes": long_pause,
                "min_pause_minutes": min_pause,
            }
            try:
                save_rules(config)
                st.success("Soglie aggiornate. Backup YAML creato.")
                st.rerun()
            except RulesConfigError as exc:
                st.error(str(exc))

    with test_rules:
        with st.form("test_rules_form"):
            test_event_type = st.selectbox(
                "Tipo evento",
                RULE_EVENT_TYPES,
                format_func=lambda value: RULE_EVENT_TYPE_LABELS[value],
            )
            test_location_type = st.selectbox(
                "Tipo luogo",
                RULE_LOCATION_TYPES,
                format_func=lambda value: RULE_LOCATION_TYPE_LABELS[value],
            )
            test_raw_type = st.text_input("Raw type")
            test_raw_text = st.text_area("Raw text")
            test_duration = st.number_input("Durata minuti", min_value=0.0, value=0.0, step=1.0)
            test_has_residual = st.checkbox("Residuo presente")
            test_stop_residual = st.checkbox("Stop sul residuo")
            test_stop_unload = st.checkbox("Stop sullo scarico")
            test_last_unload = st.checkbox("Ultimo scarico prodotto")
            test_submitted = st.form_submit_button("Testa regole")
        if test_submitted:
            try:
                result = test_all_rules_on_event(
                    {
                        "event_type": test_event_type,
                        "location_type": test_location_type,
                        "raw_type": test_raw_type,
                        "raw_text": test_raw_text,
                        "duration_minutes": test_duration,
                        "has_residual": test_has_residual,
                        "has_stop_on_residual": test_stop_residual,
                        "has_stop_on_unload": test_stop_unload,
                        "is_last_unload_for_product": test_last_unload,
                    }
                )
                st.metric("Severita finale", RULE_SEVERITY_LABELS.get(result["severity"], result["severity"]))
                st.metric("Punteggio rischio", result["risk_score"])
                st.write("**Regole applicate:**", ", ".join(result["matched_rules"]) or "Nessuna")
                st.write("**Motivazioni:**", " | ".join(result["reasons"]))
                st.write("**Azioni suggerite:**", " | ".join(result["suggested_actions"]) or "Nessuna")
            except RulesConfigError as exc:
                st.error(str(exc))


def _condition_selectbox(label: str, key: str, current: object = None) -> object:
    options = ["Non impostato", "Vero", "Falso"]
    index = 0 if current is None else (1 if dashboard_bool(current) else 2)
    selected = st.selectbox(label, options, index=index, key=key)
    return None if selected == "Non impostato" else selected == "Vero"


def _condition_numeric_value(value: object, thresholds: dict[str, object]) -> float:
    if isinstance(value, str) and value in thresholds:
        value = thresholds[value]
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _rule_form_payload(**values) -> dict[str, object]:
    conditions = {}
    mapping = {
        "has_residual": values["has_residual"],
        "has_stop_on_residual": values["stop_residual"],
        "has_stop_on_unload": values["stop_unload"],
        "is_last_unload_for_product": values["last_unload"],
    }
    conditions.update({key: value for key, value in mapping.items() if value is not None})
    raw_types = [item.strip() for item in values["raw_types"].split(",") if item.strip()]
    raw_text = [item.strip() for item in values["raw_text"].split(",") if item.strip()]
    if raw_types:
        conditions["raw_type_contains_any"] = raw_types
    if raw_text:
        conditions["raw_text_contains_any"] = raw_text
    if values["duration"] > 0:
        conditions["duration_greater_than_minutes"] = float(values["duration"])
    if values["forbidden"]:
        conditions["location_type_in_forbidden"] = True
    elif values["allowed"]:
        conditions["location_type_not_in_allowed"] = True
    return {
        "enabled": values["enabled"],
        "name_it": values["name_it"],
        "severity": values["severity"],
        "event_types": values["event_types"],
        "allowed_location_types": values["allowed"],
        "forbidden_location_types": values["forbidden"],
        "conditions": conditions,
        "explanation": values["explanation"],
        "suggested_action": values["action"],
        "category": values["category"],
        "priority": values["priority"],
    }

def count_rule(df: pd.DataFrame, rule_id: str) -> int:
    if df.empty or "rule_ids" not in df.columns:
        return 0
    return int(df["rule_ids"].fillna("").astype(str).str.contains(rule_id, regex=False).sum())


def operational_issue_frame(df: pd.DataFrame, rule_ids: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for rule_id in rule_ids:
        mask |= df["rule_ids"].fillna("").astype(str).str.contains(rule_id, regex=False)
    return df[mask].copy()


def last_unloads_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df[
        (df["event_type"].isin(["unload", "unloading"]))
        & (df["is_last_unload_for_product"].map(dashboard_bool))
    ].copy()
    if not result.empty:
        result["esito"] = result.apply(
            lambda row: "Anomalia"
            if not dashboard_bool(row.get("has_residual"))
            or dashboard_bool(row.get("has_stop_on_unload"))
            or dashboard_bool(row.get("has_stop_on_residual"))
            else "OK",
            axis=1,
        )
    return result


def render_login_page() -> None:
    st.markdown(
        """
        <div class="cf-login-shell">
          <div class="cf-login-logo">🛢️</div>
          <span class="cf-login-brand">SACCLA · Sistema di Controllo Flotta</span>
          <h1>Accesso Dashboard</h1>
          <p>Inserisci le credenziali ClickAndFind per accedere al pannello di monitoraggio operativo.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, center, _ = st.columns([1, 1.15, 1])
    with center:
        with st.form("dashboard_login_form", clear_on_submit=False):
            username = st.text_input("Username", key="login_username")
            company = st.text_input("Company", key="login_company")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Accedi", width="stretch")
        st.markdown(
            '<div class="cf-security-note">🔒 Le credenziali vengono usate solo per la sessione corrente e non vengono salvate su disco.</div>',
            unsafe_allow_html=True,
        )

        if submitted:
            with st.spinner("Accesso a ClickAndFind in corso..."):
                result = authenticate_clickandfind(username, company, password)
            if result.success:
                store_authenticated_session(username, company, password, result.vehicles)
                st.success("Accesso completato. Dashboard in caricamento...")
                st.rerun()
            else:
                st.error(result.message)


def render_connection_sidebar(database_path: str) -> None:
    with st.sidebar.expander("👤 Sessione", expanded=True):
        st.caption(f"Utente: `{st.session_state.cf_username}`")
        st.caption(f"Company: `{st.session_state.cf_company}`")
        session_state = "Pronta" if st.session_state.cf_session_ready else "Non pronta"
        st.caption(f"Sessione ClickAndFind: **{session_state}**")
        if st.button("Logout", key="logout_dashboard", width="stretch"):
            clear_dashboard_session()
            st.cache_data.clear()
            st.rerun()

    with st.sidebar.expander("🔄 Sincronizzazione", expanded=True):
        st.caption("La sincronizzazione è limitata alla data selezionata.")
        sync_date = st.date_input("Data controllo", value=date.today(), key="sync_check_date")
        all_vehicles = st.checkbox("Sincronizza tutti i mezzi", value=False, key="sync_all_vehicles")
        max_vehicles = int(
            st.number_input(
                "Numero massimo mezzi",
                min_value=1,
                max_value=100,
                value=5,
                step=1,
                key="sync_max_vehicles",
            )
        )

        vehicles = unique_vehicles(st.session_state.get("cf_vehicles", []))
        vehicle_by_codtrasp = {vehicle_codtrasp(vehicle): vehicle for vehicle in vehicles}
        selected_codtrasp = None
        if all_vehicles:
            st.caption(f"Disponibili: {len(vehicles)} · Limite: {max_vehicles}")
        elif vehicles:
            selected_codtrasp = st.selectbox(
                "Mezzo da sincronizzare",
                list(vehicle_by_codtrasp),
                format_func=lambda codtrasp: vehicle_label(vehicle_by_codtrasp[codtrasp]),
                key="sync_selected_codtrasp",
            )
        else:
            selected_codtrasp = st.text_input("Codice trasportatore", key="sync_selected_codtrasp_text")

        if st.button("Avvia sincronizzazione", key="start_sync", width="stretch", type="primary"):
            if not all_vehicles and not selected_codtrasp:
                st.error("Selezionare un mezzo o inserire un codice trasportatore.")
                return
            progress = st.progress(0)
            status = st.empty()

            def update_progress(current: int, total: int, label: str) -> None:
                ratio = 0 if total <= 0 else min(current / total, 1)
                progress.progress(ratio)
                status.caption(f"Mezzo corrente: {label} ({current}/{total})")

            with st.spinner("Sincronizzazione ClickAndFind in corso..."):
                result = sync_clickandfind_data(
                    username=st.session_state.cf_username,
                    company=st.session_state.cf_company,
                    password=st.session_state.cf_password,
                    check_date=sync_date,
                    all_vehicles=all_vehicles,
                    selected_codtrasp=selected_codtrasp,
                    max_vehicles=max_vehicles,
                    database_path=database_path,
                    progress_callback=update_progress,
                )

            progress.progress(1.0)
            if result.success:
                st.success(
                    f"Completata: {result.vehicles_processed} mezzi, "
                    f"{result.events_normalized} eventi, {result.anomalies_found} anomalie."
                )
                st.caption(f"Database: `{result.database_path}`")
                st.caption(f"Report: `{result.report_path}`")
                st.cache_data.clear()
            else:
                st.error("Sincronizzazione non completata.")
            for error in result.errors[:5]:
                st.warning(error)


apply_style()
initialize_dashboard_session()

if not st.session_state.authenticated_dashboard:
    render_login_page()
    st.stop()

with st.sidebar.expander("🖥️ Sistema", expanded=False):
    database_path = st.text_input("Database SQLite", value=resolve_database_path(), key="database_path")
    st.caption(f"Database attivo: `{database_path}`")
    if st.button("Ricarica database", key="reload_database", width="stretch"):
        st.cache_data.clear()
        st.rerun()
render_connection_sidebar(database_path)

df = load_data(database_path)

if df.empty:
    render_page_header(
        "SACCLA · Controllo Flotta",
        "Monitoraggio operativo di carichi, scarichi, soste, operazioni e allarmi",
        badge="Control Center",
        meta=f"Database: {database_path}\nUtente: {st.session_state.cf_username}",
    )
    render_empty_state(f"Nessun evento trovato in {database_path}. Eseguire prima un controllo mock o reale.", "📭")
    st.stop()

filtered = apply_filters(df)
anomalies = anomaly_events(filtered)
vehicles_with_anomalies = anomalies["vehicle_id"].nunique() if not anomalies.empty else 0
average_risk = filtered["risk_score"].mean() if not filtered.empty else 0

render_page_header(
    "SACCLA · Controllo Flotta",
    "Monitoraggio operativo carichi, scarichi, soste, operazioni e allarmi",
    badge="Control Center",
    meta=(
        f"Database: {database_path}\n"
        f"Utente: {st.session_state.cf_username} · {st.session_state.cf_company}\n"
        f"Sessione: {'Pronta' if st.session_state.cf_session_ready else 'Non pronta'}\n"
        f"Aggiornato: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ),
)

st.markdown(
    f"""
    <div class="cf-status-strip">
      <div class="cf-status-item">Eventi caricati<strong>{len(df)}</strong></div>
      <div class="cf-status-item">Eventi filtrati<strong>{len(filtered)}</strong></div>
      <div class="cf-status-item">Mezzi nel perimetro<strong>{filtered['vehicle_id'].nunique() if not filtered.empty else 0}</strong></div>
      <div class="cf-status-item">Intervallo dati<strong>{filtered['timestamp_start'].min().strftime('%d/%m/%Y') if not filtered.empty and pd.notna(filtered['timestamp_start'].min()) else 'N/D'} - {filtered['timestamp_start'].max().strftime('%d/%m/%Y') if not filtered.empty and pd.notna(filtered['timestamp_start'].max()) else 'N/D'}</strong></div>
    </div>
    """,
    unsafe_allow_html=True,
)

if filtered.empty:
    render_empty_state("Nessun evento corrisponde ai filtri selezionati.", "🔎")

tabs = st.tabs(
    [
        "🏠 Panoramica",
        "✅ Controlli operativi",
        "⛽ Ultimi scarichi",
        "📍 Luoghi e vie",
        "🧼 Possibili lavaggi",
        "🚨 Anomalie",
        "🗺️ Mappa eventi",
        "📈 Timeline mezzo",
        "📄 Dati grezzi",
        "⚙️ Gestione luoghi",
        "🧩 Gestione regole",
    ]
)

with tabs[0]:
    render_section_card("Indicatori principali", "Sintesi del perimetro operativo selezionato")
    row1 = st.columns(3)
    with row1[0]:
        kpi_card("Eventi totali", len(filtered), "Dopo i filtri applicati", "info")
    with row1[1]:
        kpi_card("Anomalie totali", len(anomalies), "Critiche, alte e medie", "high")
    with row1[2]:
        kpi_card("Anomalie critiche", int((filtered["severity"] == "critical").sum()), "Priorita massima", "critical")

    row2 = st.columns(3)
    with row2[0]:
        kpi_card("Anomalie alte", int((filtered["severity"] == "high").sum()), "Rischio elevato", "high")
    with row2[1]:
        kpi_card("Mezzi con anomalie", vehicles_with_anomalies, "Mezzi da verificare", "medium")
    with row2[2]:
        kpi_card("Punteggio rischio medio", f"{average_risk:.1f}", "Media eventi filtrati", "info")

    st.divider()
    render_section_card("Analisi del rischio", "Distribuzione e concentrazione delle anomalie")
    chart_col1, chart_col2 = st.columns(2)
    severity_summary = summary_by_severity(filtered)
    if severity_summary.empty:
        chart_col1.info("Nessun dato severita disponibile.")
    else:
        sev_chart = severity_summary.copy()
        sev_chart["Severita"] = sev_chart["severity"].map(italian_severity)
        fig = px.pie(
            sev_chart,
            names="Severita",
            values="events",
            color="Severita",
            color_discrete_map={
                "Critica": SEVERITY_COLORS["critical"],
                "Alta": SEVERITY_COLORS["high"],
                "Media": SEVERITY_COLORS["medium"],
                "Informativa": SEVERITY_COLORS["info"],
            },
        )
        chart_col1.plotly_chart(chart_layout(fig, "Distribuzione severita"), width="stretch")

    if anomalies.empty:
        chart_col2.info("Nessuna anomalia disponibile per compagnia.")
    else:
        by_company = summary_by_company(anomalies).rename(columns={"company": "Compagnia", "total_anomalies": "Anomalie"})
        fig = px.bar(by_company, x="Compagnia", y="Anomalie", color="critical_anomalies", text="Anomalie")
        chart_col2.plotly_chart(chart_layout(fig, "Anomalie per compagnia", "Compagnia", "Anomalie"), width="stretch")

    chart_col3, chart_col4 = st.columns(2)
    if anomalies.empty:
        chart_col3.info("Nessuna anomalia disponibile per mezzo.")
        chart_col4.info("Nessuna anomalia disponibile per tipo evento.")
    else:
        by_vehicle = summary_by_vehicle(anomalies).head(15).rename(
            columns={"vehicle_id": "Mezzo", "total_anomalies": "Anomalie"}
        )
        fig = px.bar(by_vehicle, x="Mezzo", y="Anomalie", color="control_status", text="Anomalie")
        chart_col3.plotly_chart(chart_layout(fig, "Anomalie per mezzo", "Mezzo", "Anomalie"), width="stretch")

        by_event = summary_by_event_type(anomalies).copy()
        by_event["Tipo evento"] = by_event["event_type"].map(italian_event_type)
        fig = px.bar(by_event.head(15), x="Tipo evento", y="total_anomalies", text="total_anomalies")
        chart_col4.plotly_chart(chart_layout(fig, "Anomalie per tipo evento", "Tipo evento", "Anomalie"), width="stretch")

    st.divider()
    render_section_card("Top mezzi a rischio", "Ordinamento per punteggio rischio e anomalie")
    risky = top_risky_vehicles(filtered, limit=10)
    if risky.empty:
        st.info("Nessun mezzo a rischio nel perimetro filtrato.")
    else:
        st.dataframe(
            display_frame(
                risky,
                [
                    "company",
                    "vehicle_id",
                    "control_status",
                    "events",
                    "total_anomalies",
                    "critical_anomalies",
                    "high_anomalies",
                    "medium_anomalies",
                    "risk_score_total",
                    "risk_score_avg",
                ],
            ).rename(
                columns={
                    "events": "Eventi",
                    "total_anomalies": "Anomalie",
                    "critical_anomalies": "Critiche",
                    "high_anomalies": "Alte",
                    "medium_anomalies": "Medie",
                    "risk_score_total": "Rischio totale",
                    "risk_score_avg": "Rischio medio",
                }
            ),
            width="stretch",
            hide_index=True,
        )

    render_section_card("Ultime anomalie critiche", "Eventi più recenti che richiedono attenzione immediata")
    latest_critical = filtered[filtered["severity"] == "critical"].sort_values("timestamp_start", ascending=False).head(10)
    if latest_critical.empty:
        render_empty_state("Nessuna anomalia critica nel perimetro selezionato.", "✓")
    else:
        st.dataframe(
            display_frame(
                latest_critical,
                [
                    "timestamp_start",
                    "company",
                    "vehicle_id",
                    "event_type",
                    "location_name",
                    "severity",
                    "explanations",
                    "suggested_action",
                ],
            ).style.apply(severity_badge_style, axis=1),
            width="stretch",
            hide_index=True,
        )

with tabs[1]:
    st.markdown("### Controlli operativi")
    row1 = st.columns(4)
    with row1[0]:
        kpi_card(
            "Scarichi non autorizzati",
            count_rule(filtered, "unload_in_unauthorized_area"),
            "Parcheggi, luoghi sospetti o non inerenti",
            "critical",
        )
    with row1[1]:
        kpi_card(
            "Programmazioni/carichi non autorizzati",
            count_rule(filtered, "programming_in_unauthorized_area"),
            "Carichi in aree non consentite",
            "critical",
        )
    with row1[2]:
        kpi_card(
            "Stop su residuo",
            count_rule(filtered, "stop_on_residual"),
            "S nera o stop residuo",
            "high",
        )
    with row1[3]:
        kpi_card(
            "Ultimi scarichi senza residuo",
            count_rule(filtered, "missing_residual_on_last_unload"),
            "R nera non rilevata",
            "critical",
        )

    row2 = st.columns(3)
    opening_rules = [
        "door_opening_in_unauthorized_area",
        "valve_opening_in_unauthorized_area",
        "coupler_opening_in_unauthorized_area",
    ]
    with row2[0]:
        kpi_card(
            "Aperture non autorizzate",
            sum(count_rule(filtered, rule_id) for rule_id in opening_rules),
            "Portellone, valvole, accoppiatori",
            "critical",
        )
    with row2[1]:
        kpi_card(
            "Possibili lavaggi",
            count_rule(filtered, "suspected_washing"),
            "Portellone in parcheggio oltre soglia",
            "critical",
        )
    with row2[2]:
        kpi_card(
            "Pause sospette",
            count_rule(filtered, "pause_in_suspicious_area"),
            "Pause in luoghi non inerenti",
            "high",
        )

    operational = operational_issue_frame(
        filtered,
        [
            "pause_in_suspicious_area",
            "stop_on_residual",
            "missing_residual_on_last_unload",
            "stop_on_last_unload",
            "programming_in_unauthorized_area",
            "unload_in_unauthorized_area",
            "door_opening_in_unauthorized_area",
            "valve_opening_in_unauthorized_area",
            "coupler_opening_in_unauthorized_area",
            "suspected_washing",
        ],
    )
    st.divider()
    if operational.empty:
        st.info("Nessuna anomalia operativa con i filtri selezionati.")
    else:
        st.dataframe(
            display_frame(
                operational.sort_values("timestamp_start", ascending=False),
                [
                    "timestamp_start",
                    "company",
                    "vehicle_id",
                    "codtrasp",
                    "event_type",
                    "product",
                    "location_name",
                    "location_type",
                    "severity",
                    "rule_ids",
                    "explanations",
                    "suggested_action",
                    "operation_duration_minutes",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[2]:
    st.markdown("### Ultimi scarichi")
    last_unloads = last_unloads_frame(filtered)
    if last_unloads.empty:
        st.info("Nessun ultimo scarico prodotto rilevato con i filtri selezionati.")
    else:
        st.dataframe(
            display_frame(
                last_unloads.sort_values("timestamp_start", ascending=False),
                [
                    "vehicle_id",
                    "codtrasp",
                    "product",
                    "timestamp_start",
                    "has_residual",
                    "has_stop_on_unload",
                    "has_stop_on_residual",
                    "severity",
                    "rule_ids",
                    "suggested_action",
                    "esito",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[3]:
    st.markdown("### Luoghi e vie")
    location_df = filtered.copy()
    location_df = location_df[
        location_df["location_name"].fillna("").astype(str).ne("")
        | location_df["location_type"].fillna("").astype(str).ne("")
    ]
    if location_df.empty:
        st.info("Nessuna informazione luogo disponibile.")
    else:
        st.dataframe(
            display_frame(
                location_df.sort_values("timestamp_start", ascending=False),
                [
                    "location_name",
                    "location_type",
                    "location_rule_source",
                    "location_confidence",
                    "event_type",
                    "severity",
                    "location_notes",
                    "vehicle_id",
                    "codtrasp",
                    "timestamp_start",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[4]:
    st.markdown("### Possibili lavaggi")
    washing = operational_issue_frame(filtered, ["suspected_washing"])
    if washing.empty:
        st.info("Nessun possibile lavaggio rilevato con i filtri selezionati.")
    else:
        st.dataframe(
            display_frame(
                washing.sort_values("timestamp_start", ascending=False),
                [
                    "vehicle_id",
                    "codtrasp",
                    "location_name",
                    "operation_duration_minutes",
                    "timestamp_start",
                    "explanations",
                    "suggested_action",
                    "severity",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[5]:
    render_section_card("Anomalie operative", "Risultati ordinati per severità e data evento")
    if anomalies.empty:
        render_empty_state("Nessuna anomalia corrisponde ai filtri selezionati.", "✓")
    else:
        st.markdown(
            " ".join(
                [
                    f"{severity_badge('critical')} <strong>{int((anomalies['severity'] == 'critical').sum())}</strong>",
                    f"{severity_badge('high')} <strong>{int((anomalies['severity'] == 'high').sum())}</strong>",
                    f"{severity_badge('medium')} <strong>{int((anomalies['severity'] == 'medium').sum())}</strong>",
                ]
            ),
            unsafe_allow_html=True,
        )
        anomaly_table = anomalies.copy()
        anomaly_table["severity"] = pd.Categorical(anomaly_table["severity"], categories=SEVERITY_ORDER, ordered=True)
        anomaly_table = anomaly_table.sort_values(["severity", "timestamp_start"])
        shown = display_frame(
            anomaly_table,
            [
                "check_date",
                "company",
                "vehicle_id",
                "codtrasp",
                "event_type",
                "source_section",
                "severity",
                "reasons",
                "explanations",
                "suggested_actions",
                "suggested_action",
                "risk_score",
                "timestamp_start",
                "location_name",
            ],
        )
        st.dataframe(shown.style.apply(severity_badge_style, axis=1), width="stretch", hide_index=True)
        st.download_button(
            "Scarica anomalie CSV",
            data=shown.to_csv(index=False).encode("utf-8"),
            file_name="clickandfind_anomalie_filtrate.csv",
            mime="text/csv",
            key="download_anomalies_csv",
        )

with tabs[6]:
    render_section_card(
        "Distribuzione geografica degli eventi",
        "Eventi filtrati con coordinate disponibili · colori basati sulla severità",
    )
    render_map(filtered.dropna(subset=["latitude", "longitude"]))

with tabs[7]:
    render_section_card("Timeline mezzo", "Sequenza temporale degli eventi per il mezzo selezionato")
    vehicle_options = sorted(filtered["vehicle_id"].dropna().unique()) if not filtered.empty else []
    if not vehicle_options:
        render_empty_state("Nessun mezzo disponibile con i filtri selezionati.", "🚚")
    else:
        selected_vehicle = st.selectbox("Seleziona mezzo", vehicle_options, key="timeline_vehicle")
        vehicle_df = filtered[filtered["vehicle_id"] == selected_vehicle].sort_values("timestamp_start")
        summary_cols = st.columns(4)
        summary_cols[0].metric("Eventi", len(vehicle_df))
        summary_cols[1].metric("Anomalie", int(vehicle_df["severity"].isin(ANOMALY_LEVELS).sum()))
        summary_cols[2].metric("Critiche", int((vehicle_df["severity"] == "critical").sum()))
        summary_cols[3].metric("Rischio medio", f"{vehicle_df['risk_score'].mean():.1f}")
        timeline = vehicle_df.dropna(subset=["timestamp_start", "timestamp_end"])
        if timeline.empty:
            st.info("Nessun dato temporale disponibile per il mezzo selezionato.")
        else:
            timeline_plot = timeline.copy()
            timeline_plot["Severita"] = timeline_plot["severity"].map(italian_severity)
            timeline_plot["Tipo evento"] = timeline_plot["event_type"].map(italian_event_type)
            fig = px.timeline(
                timeline_plot,
                x_start="timestamp_start",
                x_end="timestamp_end",
                y="Tipo evento",
                color="Severita",
                hover_data=["company", "source_section", "location_name", "risk_score"],
                color_discrete_map={
                    "Critica": SEVERITY_COLORS["critical"],
                    "Alta": SEVERITY_COLORS["high"],
                    "Media": SEVERITY_COLORS["medium"],
                    "Informativa": SEVERITY_COLORS["info"],
                },
            )
            fig.update_yaxes(autorange="reversed", title="Tipo evento")
            st.plotly_chart(chart_layout(fig, f"Timeline eventi - {selected_vehicle}", "Orario", "Tipo evento"), width="stretch")

        if not vehicle_df.empty:
            trend = (
                vehicle_df.dropna(subset=["timestamp_start"])
                .assign(giorno=lambda data: data["timestamp_start"].dt.floor("h"))
                .groupby(["giorno", "severity"], dropna=False)
                .size()
                .reset_index(name="eventi")
            )
            if not trend.empty:
                trend["Severita"] = trend["severity"].map(italian_severity)
                fig = px.line(trend, x="giorno", y="eventi", color="Severita", markers=True)
                st.plotly_chart(chart_layout(fig, "Andamento temporale eventi/anomalie", "Ora", "Eventi"), width="stretch")

        st.markdown("#### Eventi del mezzo")
        st.dataframe(
            display_frame(
                vehicle_df,
                [
                    "timestamp_start",
                    "timestamp_end",
                    "company",
                    "vehicle_id",
                    "codtrasp",
                    "event_type",
                    "source_section",
                    "severity",
                    "risk_score",
                    "location_name",
                    "reasons",
                    "suggested_action",
                    "suggested_actions",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[8]:
    st.markdown("### Dati grezzi filtrati")
    render_downloads(filtered)
    st.divider()
    if filtered.empty:
        st.info("Nessun dato da mostrare.")
    else:
        st.dataframe(display_frame(filtered), width="stretch", hide_index=True)

with tabs[9]:
    render_location_manager()

with tabs[10]:
    render_rule_manager()
