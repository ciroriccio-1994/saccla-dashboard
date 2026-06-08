from __future__ import annotations


def risk_score(severity: str) -> int:
    return {"critical": 100, "high": 70, "medium": 40, "low": 10, "info": 0}.get(severity.lower(), 0)


def vehicle_control_status(severities: list[str]) -> str:
    normalized = {severity.lower() for severity in severities}
    if "critical" in normalized:
        return "CRITICAL"
    if "high" in normalized:
        return "HIGH_RISK"
    if "medium" in normalized:
        return "WARNING"
    return "OK"
