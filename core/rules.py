from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml

from core.models import ClickAndFindEvent, RuleDecision
from core.normalizer import normalize_event_type, normalize_location_type
from core.risk_score import vehicle_control_status


SEVERITY_RANK = {"ok": 0, "info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}


class RuleEngine:
    def __init__(
        self,
        rules_path: str | Path = "config/rules.yaml",
        config: dict[str, Any] | None = None,
    ) -> None:
        if config is None:
            with Path(rules_path).open("r", encoding="utf-8") as handle:
                config = yaml.safe_load(handle) or {}
        self.config = config
        self.thresholds = dict(config.get("thresholds") or {})
        self.rules = _normalize_rules(config)

    def evaluate(self, event: ClickAndFindEvent) -> RuleDecision:
        event_type = normalize_event_type(event.event_type)
        raw_type = normalize_event_type(event.raw_type)
        ignored_types = {normalize_event_type(item) for item in self.config.get("ignored_event_types", [])}
        if event_type in ignored_types or raw_type in ignored_types:
            explanation = f"Tipo evento ignorato: {event.event_type}"
            return RuleDecision("info", [explanation], ignored=True, explanations=[explanation])

        matches = [
            rule
            for rule in self.rules
            if _to_bool(rule.get("enabled", True)) and self._matches(event, rule)
        ]
        if not matches:
            return RuleDecision("info", ["Nessuna anomalia rilevata"], explanations=["Nessuna anomalia rilevata"])

        matches.sort(key=lambda rule: (int(rule.get("priority", 100)), rule["id"]))
        severity = max(
            (str(rule.get("severity", "INFO")).lower() for rule in matches),
            key=lambda value: SEVERITY_RANK.get(value, 0),
        )
        explanations = [str(rule.get("explanation") or rule["id"]) for rule in matches]
        actions = [str(rule.get("suggested_action") or "Verificare l'evento operativo.") for rule in matches]
        return RuleDecision(
            severity=severity,
            reasons=explanations,
            matched_rules=[rule["id"] for rule in matches],
            explanations=explanations,
            suggested_actions=actions,
        )

    def apply(self, events: Iterable[ClickAndFindEvent]) -> list[ClickAndFindEvent]:
        evaluated = [event.with_decision(self.evaluate(event)) for event in events]
        statuses = self.vehicle_statuses(evaluated)
        return [
            ClickAndFindEvent(**{**event.to_dict(), "control_status": statuses.get(event.vehicle_id, "OK")})
            for event in evaluated
        ]

    @staticmethod
    def vehicle_statuses(events: Iterable[ClickAndFindEvent]) -> dict[str, str]:
        by_vehicle: dict[str, list[str]] = {}
        for event in events:
            by_vehicle.setdefault(event.vehicle_id, []).append(event.severity)
        return {vehicle_id: vehicle_control_status(severities) for vehicle_id, severities in by_vehicle.items()}

    def _matches(self, event: ClickAndFindEvent, rule: dict[str, Any]) -> bool:
        event_type = normalize_event_type(event.event_type)
        if rule.get("id") in {"door_opening_in_unauthorized_area", "suspected_washing"}:
            if event_type == "portellone" and not _is_door_opening(event):
                return False
        configured_event_types = {
            normalize_event_type(value) for value in rule.get("event_types", [])
        }
        if configured_event_types and event_type not in configured_event_types:
            return False

        if rule.get("source_sections") and event.source_section not in rule["source_sections"]:
            return False
        if rule.get("raw_ops") and event.raw_op not in rule["raw_ops"]:
            return False

        location_type = _location_alias(normalize_location_type(event.location_type))
        allowed = {
            _location_alias(normalize_location_type(value))
            for value in rule.get("allowed_location_types", [])
        }
        forbidden = {
            _location_alias(normalize_location_type(value))
            for value in rule.get("forbidden_location_types", [])
        }
        conditions = dict(rule.get("conditions") or {})
        if conditions.get("allowed_location_types"):
            allowed |= {
                _location_alias(normalize_location_type(value))
                for value in conditions["allowed_location_types"]
            }
        if conditions.get("forbidden_location_types"):
            forbidden |= {
                _location_alias(normalize_location_type(value))
                for value in conditions["forbidden_location_types"]
            }

        if conditions.get("location_type_in_forbidden") and location_type not in forbidden:
            return False
        if conditions.get("location_type_not_in_allowed") and location_type in allowed:
            return False
        if rule.get("location_types") and location_type not in {
            _location_alias(normalize_location_type(value)) for value in rule["location_types"]
        }:
            return False
        if rule.get("location_types_not_in") and location_type in {
            _location_alias(normalize_location_type(value)) for value in rule["location_types_not_in"]
        }:
            return False

        for field in [
            "has_residual",
            "has_stop_on_residual",
            "has_stop_on_unload",
            "is_last_unload_for_product",
            "is_programming_like_load",
        ]:
            if field in conditions and bool(getattr(event, field, False)) != _to_bool(conditions[field]):
                return False

        if not _contains_any(event.raw_type, conditions.get("raw_type_contains_any", [])):
            return False
        if not _contains_any(event.raw_text, conditions.get("raw_text_contains_any", [])):
            return False

        duration = event.operation_duration_minutes or event.duration_minutes
        greater = self._numeric_condition(conditions, "duration_greater_than_minutes")
        if greater is not None and duration <= greater:
            return False
        less = self._numeric_condition(conditions, "duration_less_than_minutes")
        if less is not None and duration >= less:
            return False

        if rule.get("context_terms") and not _context_contains(event, rule["context_terms"]):
            return False
        return True

    def _numeric_condition(self, conditions: dict[str, Any], key: str) -> float | None:
        value = conditions.get(key)
        if value is None:
            named = conditions.get("named_threshold")
            if named and key == "duration_greater_than_minutes":
                value = self.thresholds.get(str(named))
        if isinstance(value, str) and value in self.thresholds:
            value = self.thresholds[value]
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _normalize_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rules = config.get("rules", {})
    if isinstance(raw_rules, dict):
        return [
            {"id": str(rule_id), **_normalize_rule(rule, config)}
            for rule_id, rule in raw_rules.items()
            if isinstance(rule, dict)
        ]
    if isinstance(raw_rules, list):
        return [
            {"id": str(rule.get("id", f"rule_{index}")), **_normalize_rule(rule, config)}
            for index, rule in enumerate(raw_rules, start=1)
            if isinstance(rule, dict)
        ]
    return []


def _normalize_rule(rule: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(rule)
    normalized.setdefault("enabled", True)
    normalized.setdefault("priority", 100)
    normalized.setdefault("conditions", {})
    if rule.get("condition") and not normalized["conditions"]:
        event_types, allowed, forbidden, conditions = _legacy_condition(str(rule["condition"]), config)
        normalized["event_types"] = normalized.get("event_types") or event_types
        normalized["allowed_location_types"] = normalized.get("allowed_location_types") or allowed
        normalized["forbidden_location_types"] = normalized.get("forbidden_location_types") or forbidden
        normalized["conditions"] = conditions
    return normalized


def _legacy_condition(
    condition: str,
    config: dict[str, Any],
) -> tuple[list[str], list[str], list[str], dict[str, Any]]:
    allowed_config = config.get("allowed_location_types", {})
    if condition == "pause_in_suspicious_area":
        allowed = allowed_config.get("pause", [])
        return ["stop_or_pause", "stop"], allowed, [], {"location_type_not_in_allowed": True}
    if condition == "stop_on_residual":
        return ["unload", "stop_or_pause", "stop"], [], [], {"has_stop_on_residual": True}
    if condition == "missing_residual_on_last_unload":
        return ["unload"], [], [], {"is_last_unload_for_product": True, "has_residual": False}
    if condition == "stop_on_last_unload":
        return ["unload"], [], [], {"is_last_unload_for_product": True, "has_stop_on_unload": True}
    if condition == "programming_in_unauthorized_area":
        allowed = allowed_config.get("programming", [])
        return ["load", "programming"], allowed, [], {"location_type_not_in_allowed": True}
    if condition == "unload_in_unauthorized_area":
        allowed = allowed_config.get("unload", [])
        return ["unload", "unloading"], allowed, [], {"location_type_not_in_allowed": True}
    if condition == "door_opening_in_unauthorized_area":
        allowed = allowed_config.get("opening", [])
        return ["portellone", "door_opening"], allowed, [], {
            "location_type_not_in_allowed": True,
            "raw_type_contains_any": ["portellone", "door"],
        }
    if condition == "valve_opening_in_unauthorized_area":
        allowed = allowed_config.get("opening", [])
        return ["valvole", "valve_opening"], allowed, [], {
            "location_type_not_in_allowed": True,
            "raw_type_contains_any": ["valvole", "valvola", "valve"],
        }
    if condition == "coupler_opening_in_unauthorized_area":
        allowed = allowed_config.get("opening", [])
        return ["coupler_opening"], allowed, [], {
            "location_type_not_in_allowed": True,
            "raw_type_contains_any": ["accoppiatore", "coupler"],
        }
    if condition == "suspected_washing":
        threshold = (
            config.get("suspected_washing", {})
            .get("door_opening_parking_duration_threshold_minutes", 5)
        )
        return ["portellone", "door_opening"], [], ["parking"], {
            "location_type_in_forbidden": True,
            "raw_type_contains_any": ["portellone", "door"],
            "duration_greater_than_minutes": threshold,
        }
    return [], [], [], {}


def _contains_any(value: str, terms: list[str]) -> bool:
    if not terms:
        return True
    normalized = str(value or "").casefold()
    return any(str(term).casefold() in normalized for term in terms)


def _context_contains(event: ClickAndFindEvent, terms: list[str]) -> bool:
    context = " ".join(
        [
            event.event_type,
            event.location_name,
            event.location_type,
            event.raw_text,
            event.source_section,
            " ".join(event.reasons),
        ]
    ).casefold()
    return any(str(term).casefold() in context for term in terms)


def _location_alias(value: str) -> str:
    aliases = {
        "parking_area": "parking",
        "suspicious_area": "suspicious",
        "authorized_point": "depot",
        "customer_site": "gas_station",
        "roadside": "road_or_highway",
    }
    return aliases.get(value, value or "unknown")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "s"}


def _is_door_opening(event: ClickAndFindEvent) -> bool:
    raw = event.raw_text.casefold()
    return (
        '"dati": "1"' in raw
        or '"dati": 1' in raw
        or "apertura" in raw
        or '"open"' in raw
    )
