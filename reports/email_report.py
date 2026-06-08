from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from reports.excel_report import anomaly_events, top_risky_vehicles


def send_report(subject: str, body: str, attachment_path: str | Path | None = None) -> None:
    load_dotenv()
    host = _required("SMTP_HOST")
    user = _required("SMTP_USERNAME")
    password = _required("SMTP_PASSWORD")
    recipients = [item.strip() for item in _required("REPORT_TO").split(",") if item.strip()]
    port = int(os.getenv("SMTP_PORT", "587"))

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("REPORT_FROM", user)
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    if attachment_path:
        path = Path(attachment_path)
        message.add_attachment(path.read_bytes(), maintype="application", subtype="octet-stream", filename=path.name)

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(message)


def build_weekly_email_body(df: pd.DataFrame) -> str:
    if df.empty:
        return "Weekly ClickAndFind control summary\n\nNo events were checked this week."

    anomalies = anomaly_events(df)
    critical = df[df["severity"] == "critical"]
    high = df[df["severity"] == "high"]
    medium = df[df["severity"] == "medium"]
    risky = top_risky_vehicles(df, limit=5)

    lines = [
        "Weekly ClickAndFind control summary",
        "",
        f"Vehicles checked: {df['vehicle_id'].nunique()}",
        f"Total anomalies: {len(anomalies)}",
        f"Critical anomalies: {len(critical)}",
        f"High anomalies: {len(high)}",
        f"Medium anomalies: {len(medium)}",
        "",
        "Top 5 risky vehicles:",
    ]

    if risky.empty:
        lines.append("- None")
    else:
        for row in risky.itertuples(index=False):
            lines.append(
                f"- {row.vehicle_id} ({row.company}): score {int(row.risk_score_total)}, "
                f"status {row.control_status}, anomalies {int(row.total_anomalies)}"
            )

    lines.extend(["", "Critical events:"])
    if critical.empty:
        lines.append("- None")
    else:
        for row in critical.sort_values("timestamp_start").itertuples(index=False):
            lines.append(
                f"- {row.event_id} | {row.company} | {row.vehicle_id} | {row.event_type} | "
                f"{row.location_name} | {row.explanations}"
            )

    return "\n".join(lines)


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
