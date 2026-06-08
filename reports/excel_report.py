from __future__ import annotations

from pathlib import Path

import pandas as pd


ANOMALY_LEVELS = ["critical", "high", "medium"]


def write_excel_report(df: pd.DataFrame, output_path: str | Path = "outputs/reports/clickandfind_report.xlsx") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = prepare_report_dataframe(df)
    anomalies = anomaly_events(prepared)
    critical = prepared[prepared["severity"] == "critical"] if not prepared.empty else prepared
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        prepared.to_excel(writer, sheet_name="Events", index=False)
        anomalies.to_excel(writer, sheet_name="Anomalies", index=False)
        critical.to_excel(writer, sheet_name="Critical Anomalies", index=False)
        summary_by_company(prepared).to_excel(writer, sheet_name="Summary by Company", index=False)
        summary_by_vehicle(prepared).to_excel(writer, sheet_name="Summary by Vehicle", index=False)
        summary_by_event_type(prepared).to_excel(writer, sheet_name="Summary by Event Type", index=False)
        summary_by_severity(prepared).to_excel(writer, sheet_name="Summary by Severity", index=False)
    return path


def prepare_report_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    if prepared.empty:
        return prepared
    prepared["severity"] = prepared["severity"].fillna("info").str.lower()
    prepared["risk_score"] = pd.to_numeric(prepared["risk_score"], errors="coerce").fillna(0).astype(int)
    prepared["control_status"] = prepared.get("control_status", "OK")
    return prepared


def anomaly_events(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["severity"].isin(ANOMALY_LEVELS)].copy() if not df.empty else df


def summary_by_company(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return _summary(df, ["company"])


def summary_by_vehicle(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    summary = _summary(df, ["company", "vehicle_id"])
    statuses = (
        df.groupby(["company", "vehicle_id"], dropna=False)["control_status"]
        .first()
        .reset_index()
    )
    return summary.merge(statuses, on=["company", "vehicle_id"], how="left").sort_values(
        ["risk_score_total", "critical_anomalies", "high_anomalies"],
        ascending=False,
    )


def summary_by_event_type(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return _summary(df, ["event_type"])


def summary_by_severity(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("severity", dropna=False)
        .agg(events=("event_id", "count"), vehicles=("vehicle_id", "nunique"), risk_score_total=("risk_score", "sum"))
        .reset_index()
        .sort_values("risk_score_total", ascending=False)
    )


def top_risky_vehicles(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    return summary_by_vehicle(df).head(limit)


def _summary(df: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    grouped = (
        df.groupby(group_columns, dropna=False)
        .agg(
            events=("event_id", "count"),
            vehicles=("vehicle_id", "nunique"),
            total_anomalies=("severity", lambda values: values.isin(ANOMALY_LEVELS).sum()),
            critical_anomalies=("severity", lambda values: (values == "critical").sum()),
            high_anomalies=("severity", lambda values: (values == "high").sum()),
            medium_anomalies=("severity", lambda values: (values == "medium").sum()),
            risk_score_total=("risk_score", "sum"),
            risk_score_avg=("risk_score", "mean"),
        )
        .reset_index()
    )
    return grouped.sort_values(["risk_score_total", "critical_anomalies"], ascending=False)
