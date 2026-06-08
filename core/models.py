from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class ClickAndFindEvent:
    event_id: str
    check_date: date
    company: str
    vehicle_id: str
    tractor_id: str
    trailer_id: str
    event_type: str
    timestamp_start: datetime
    timestamp_end: datetime
    duration_minutes: float
    latitude: float | None
    longitude: float | None
    location_name: str
    location_type: str
    raw_text: str
    source_section: str
    severity: str = "info"
    reasons: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    risk_score: int = 0
    control_status: str = "OK"
    codtrasp: str = ""
    tractor_plate: str = ""
    semitrailer_plate: str = ""
    terminal_id: str = ""
    raw_type: str = ""
    raw_op: str = ""
    rule_id: str = ""
    suggested_action: str = ""
    product: str = ""
    is_last_unload_for_product: bool = False
    has_residual: bool = False
    has_stop_on_residual: bool = False
    has_stop_on_unload: bool = False
    is_programming_like_load: bool = False
    operation_duration_minutes: float = 0
    location_confidence: float = 0
    location_rule_source: str = ""
    location_notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required_str(self.event_id, "event_id"))
        object.__setattr__(self, "check_date", _to_date(self.check_date, "check_date"))
        object.__setattr__(self, "company", _required_str(self.company, "company"))
        object.__setattr__(self, "vehicle_id", _required_str(self.vehicle_id, "vehicle_id"))
        object.__setattr__(self, "tractor_id", _optional_str(self.tractor_id))
        object.__setattr__(self, "trailer_id", _optional_str(self.trailer_id))
        object.__setattr__(self, "event_type", _required_str(self.event_type, "event_type").lower())
        object.__setattr__(self, "timestamp_start", _to_datetime(self.timestamp_start, "timestamp_start"))
        object.__setattr__(self, "timestamp_end", _to_datetime(self.timestamp_end, "timestamp_end"))
        object.__setattr__(self, "duration_minutes", _to_float(self.duration_minutes, "duration_minutes"))
        object.__setattr__(self, "latitude", _to_optional_float(self.latitude))
        object.__setattr__(self, "longitude", _to_optional_float(self.longitude))
        object.__setattr__(self, "location_name", _optional_str(self.location_name))
        object.__setattr__(self, "location_type", _optional_str(self.location_type).lower())
        object.__setattr__(self, "raw_text", _optional_str(self.raw_text))
        object.__setattr__(self, "source_section", _optional_str(self.source_section))
        object.__setattr__(self, "severity", _optional_str(self.severity).lower() or "info")
        object.__setattr__(self, "reasons", _to_reasons(self.reasons))
        object.__setattr__(self, "rule_ids", _to_reasons(self.rule_ids))
        object.__setattr__(self, "explanations", _to_reasons(self.explanations))
        object.__setattr__(self, "suggested_actions", _to_reasons(self.suggested_actions))
        object.__setattr__(self, "risk_score", int(self.risk_score or 0))
        object.__setattr__(self, "control_status", _optional_str(self.control_status).upper() or "OK")
        object.__setattr__(self, "codtrasp", _optional_str(self.codtrasp))
        object.__setattr__(self, "tractor_plate", _optional_str(self.tractor_plate))
        object.__setattr__(self, "semitrailer_plate", _optional_str(self.semitrailer_plate))
        object.__setattr__(self, "terminal_id", _optional_str(self.terminal_id))
        object.__setattr__(self, "raw_type", _optional_str(self.raw_type))
        object.__setattr__(self, "raw_op", _optional_str(self.raw_op))
        object.__setattr__(self, "rule_id", _optional_str(self.rule_id) or (self.rule_ids[0] if self.rule_ids else ""))
        object.__setattr__(
            self,
            "suggested_action",
            _optional_str(self.suggested_action) or (self.suggested_actions[0] if self.suggested_actions else ""),
        )
        object.__setattr__(self, "product", _optional_str(self.product))
        object.__setattr__(self, "is_last_unload_for_product", _to_bool(self.is_last_unload_for_product))
        object.__setattr__(self, "has_residual", _to_bool(self.has_residual))
        object.__setattr__(self, "has_stop_on_residual", _to_bool(self.has_stop_on_residual))
        object.__setattr__(self, "has_stop_on_unload", _to_bool(self.has_stop_on_unload))
        object.__setattr__(self, "is_programming_like_load", _to_bool(self.is_programming_like_load))
        object.__setattr__(self, "operation_duration_minutes", _to_float(self.operation_duration_minutes, "operation_duration_minutes"))
        object.__setattr__(self, "location_confidence", _to_float(self.location_confidence, "location_confidence"))
        object.__setattr__(self, "location_rule_source", _optional_str(self.location_rule_source))
        object.__setattr__(self, "location_notes", _optional_str(self.location_notes))
        self._validate()

    def _validate(self) -> None:
        if self.timestamp_end < self.timestamp_start:
            raise ValueError("timestamp_end cannot be before timestamp_start")
        if self.duration_minutes < 0:
            raise ValueError("duration_minutes cannot be negative")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if self.severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError("severity must be one of info, low, medium, high, critical")
        if self.control_status not in {"OK", "WARNING", "HIGH_RISK", "CRITICAL"}:
            raise ValueError("control_status must be one of OK, WARNING, HIGH_RISK, CRITICAL")

    def with_decision(self, decision: "RuleDecision") -> "ClickAndFindEvent":
        return ClickAndFindEvent(**{**self.to_dict(), **decision.to_event_updates()})

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["check_date"] = self.check_date.isoformat()
        row["timestamp_start"] = self.timestamp_start.isoformat()
        row["timestamp_end"] = self.timestamp_end.isoformat()
        row["reasons"] = "; ".join(self.reasons)
        row["rule_ids"] = "; ".join(self.rule_ids)
        row["explanations"] = "; ".join(self.explanations)
        row["suggested_actions"] = "; ".join(self.suggested_actions)
        return row

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ClickAndFindEvent":
        return cls(
            event_id=row.get("event_id", ""),
            check_date=row.get("check_date"),
            company=row.get("company", ""),
            vehicle_id=row.get("vehicle_id", ""),
            tractor_id=row.get("tractor_id", ""),
            trailer_id=row.get("trailer_id", ""),
            event_type=row.get("event_type", ""),
            timestamp_start=row.get("timestamp_start"),
            timestamp_end=row.get("timestamp_end"),
            duration_minutes=row.get("duration_minutes", 0),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            location_name=row.get("location_name", ""),
            location_type=row.get("location_type", ""),
            raw_text=row.get("raw_text", ""),
            source_section=row.get("source_section", ""),
            severity=row.get("severity", "info"),
            reasons=row.get("reasons", []),
            rule_ids=row.get("rule_ids", []),
            explanations=row.get("explanations", []),
            suggested_actions=row.get("suggested_actions", []),
            risk_score=row.get("risk_score", 0),
            control_status=row.get("control_status", "OK"),
            codtrasp=row.get("codtrasp", ""),
            tractor_plate=row.get("tractor_plate", ""),
            semitrailer_plate=row.get("semitrailer_plate", ""),
            terminal_id=row.get("terminal_id", ""),
            raw_type=row.get("raw_type", ""),
            raw_op=row.get("raw_op", ""),
            rule_id=row.get("rule_id", ""),
            suggested_action=row.get("suggested_action", ""),
            product=row.get("product", ""),
            is_last_unload_for_product=row.get("is_last_unload_for_product", False),
            has_residual=row.get("has_residual", False),
            has_stop_on_residual=row.get("has_stop_on_residual", False),
            has_stop_on_unload=row.get("has_stop_on_unload", False),
            is_programming_like_load=row.get("is_programming_like_load", False),
            operation_duration_minutes=row.get("operation_duration_minutes", 0),
            location_confidence=row.get("location_confidence", 0),
            location_rule_source=row.get("location_rule_source", ""),
            location_notes=row.get("location_notes", ""),
        )


@dataclass(frozen=True)
class RuleDecision:
    severity: str
    reasons: list[str]
    ignored: bool = False
    matched_rules: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)

    def to_event_updates(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "reasons": self.reasons,
            "rule_ids": self.matched_rules,
            "explanations": self.explanations or self.reasons,
            "suggested_actions": self.suggested_actions,
            "rule_id": self.matched_rules[0] if self.matched_rules else "",
            "suggested_action": self.suggested_actions[0] if self.suggested_actions else "",
            "risk_score": severity_to_score(self.severity),
        }


def events_to_dataframe(events: Iterable[ClickAndFindEvent]):
    import pandas as pd

    return pd.DataFrame([event.to_dict() for event in events])


def events_from_dataframe(dataframe) -> list[ClickAndFindEvent]:
    return [ClickAndFindEvent.from_dict(row) for row in dataframe.to_dict("records")]


def severity_to_score(severity: str) -> int:
    return {"critical": 100, "high": 75, "medium": 50, "low": 25, "info": 10, "ok": 0}.get(severity, 0)


def _required_str(value: Any, field_name: str) -> str:
    value = _optional_str(value)
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


def _optional_str(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_date(value: Any, field_name: str) -> date:
    if _is_missing(value):
        raise ValueError(f"{field_name} is required")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).strip()).date()


def _to_datetime(value: Any, field_name: str) -> datetime:
    if _is_missing(value):
        raise ValueError(f"{field_name} is required")
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).strip())


def _to_float(value: Any, field_name: str) -> float:
    if _is_missing(value):
        raise ValueError(f"{field_name} is required")
    return float(value)


def _to_optional_float(value: Any) -> float | None:
    if _is_missing(value) or value == "":
        return None
    return float(value)


def _to_reasons(value: Any) -> list[str]:
    if _is_missing(value):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(";") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _to_bool(value: Any) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "s"}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
