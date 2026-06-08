from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import shutil
import tempfile
from typing import Any

import yaml

from core.models import ClickAndFindEvent
from core.rules import RuleEngine


DEFAULT_PATH = Path("config/rules.yaml")
SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
EVENT_TYPES = [
    "load",
    "unload",
    "stop_or_pause",
    "operation",
    "alarm",
    "door_opening",
    "valve_opening",
    "coupler_opening",
    "portellone",
    "valvole",
]
LOCATION_TYPES = [
    "parking",
    "refinery",
    "depot",
    "gas_station",
    "workshop",
    "service_area",
    "suspicious",
    "road_or_highway",
    "unknown",
]
SEVERITY_LABELS = {
    "CRITICAL": "Critica",
    "HIGH": "Alta",
    "MEDIUM": "Media",
    "LOW": "Bassa",
    "INFO": "Informativa",
    "OK": "OK",
}
EVENT_TYPE_LABELS = {
    "load": "Carico/Programmazione",
    "unload": "Scarico",
    "stop_or_pause": "Pausa/Sosta",
    "operation": "Operazione",
    "alarm": "Allarme",
    "door_opening": "Apertura portellone",
    "valve_opening": "Apertura valvola",
    "coupler_opening": "Apertura accoppiatore",
    "portellone": "Portellone",
    "valvole": "Valvole",
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
KNOWN_RULE_NAMES = {
    "pause_in_suspicious_area": "Pausa in zona sospetta",
    "stop_on_residual": "Stop sul residuo",
    "missing_residual_on_last_unload": "Residuo mancante sull'ultimo scarico",
    "stop_on_last_unload": "Stop sullo scarico nell'ultimo scarico",
    "programming_in_unauthorized_area": "Programmazione/carico in zona non autorizzata",
    "unload_in_unauthorized_area": "Scarico in zona non autorizzata",
    "door_opening_in_unauthorized_area": "Apertura portellone in zona non autorizzata",
    "valve_opening_in_unauthorized_area": "Apertura valvola in zona non autorizzata",
    "coupler_opening_in_unauthorized_area": "Apertura accoppiatore in zona non autorizzata",
    "suspected_washing": "Possibile lavaggio",
}
KNOWN_RULE_PRIORITIES = {
    "suspected_washing": 5,
    "missing_residual_on_last_unload": 10,
    "stop_on_last_unload": 15,
    "stop_on_residual": 20,
    "programming_in_unauthorized_area": 30,
    "unload_in_unauthorized_area": 30,
    "door_opening_in_unauthorized_area": 40,
    "valve_opening_in_unauthorized_area": 40,
    "coupler_opening_in_unauthorized_area": 40,
    "pause_in_suspicious_area": 100,
}


class RulesConfigError(ValueError):
    """Raised when config/rules.yaml is malformed."""


def load_rules(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("rules: {}\nthresholds: {}\n", encoding="utf-8")
        return {"rules": {}, "thresholds": {}, "ignored_event_types": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise RulesConfigError(f"Il file {path} contiene YAML non valido: {exc}") from exc
    except OSError as exc:
        raise RulesConfigError(f"Impossibile leggere il file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RulesConfigError("Il file regole deve contenere una mappa YAML.")
    return _normalize_config(raw)


def save_rules(data: dict[str, Any], path: str | Path = DEFAULT_PATH) -> Path:
    normalized = _normalize_config(data)
    for rule_id, rule in normalized["rules"].items():
        errors = validate_rule({"id": rule_id, **rule})
        if errors:
            raise RulesConfigError(f"Regola {rule_id} non valida: {'; '.join(errors)}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_rules(path)
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            yaml.safe_dump(normalized, handle, allow_unicode=True, sort_keys=False)
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    except OSError as exc:
        raise RulesConfigError(f"Impossibile salvare il file {path}: {exc}") from exc
    return path


def backup_rules(path: str | Path = DEFAULT_PATH) -> Path:
    path = Path(path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.backup_{timestamp}{path.suffix}")
    counter = 2
    while backup.exists():
        backup = path.with_name(f"{path.stem}.backup_{timestamp}_{counter}{path.suffix}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def add_rule(rule_id: str, rule: dict[str, Any], path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    data = load_rules(path)
    rule_id = _normalize_rule_id(rule_id)
    if rule_id in data["rules"]:
        raise RulesConfigError("Esiste gia una regola con questo ID.")
    normalized = _normalize_rule(rule_id, rule)
    errors = validate_rule({"id": rule_id, **normalized})
    if errors:
        raise RulesConfigError("; ".join(errors))
    data["rules"][rule_id] = normalized
    save_rules(data, path)
    return normalized


def update_rule(rule_id: str, rule: dict[str, Any], path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    data = load_rules(path)
    if rule_id not in data["rules"]:
        raise RulesConfigError("La regola selezionata non esiste.")
    normalized = _normalize_rule(rule_id, rule)
    errors = validate_rule({"id": rule_id, **normalized})
    if errors:
        raise RulesConfigError("; ".join(errors))
    data["rules"][rule_id] = normalized
    save_rules(data, path)
    return normalized


def delete_rule(rule_id: str, path: str | Path = DEFAULT_PATH) -> None:
    data = load_rules(path)
    if rule_id not in data["rules"]:
        raise RulesConfigError("La regola selezionata non esiste.")
    del data["rules"][rule_id]
    save_rules(data, path)


def enable_rule(rule_id: str, path: str | Path = DEFAULT_PATH) -> None:
    _set_rule_enabled(rule_id, True, path)


def disable_rule(rule_id: str, path: str | Path = DEFAULT_PATH) -> None:
    _set_rule_enabled(rule_id, False, path)


def get_rule_by_id(rule_id: str, path: str | Path = DEFAULT_PATH) -> dict[str, Any] | None:
    data = load_rules(path)
    rule = data["rules"].get(rule_id)
    return {"id": rule_id, **rule} if rule else None


def validate_rule(rule: dict[str, Any]) -> list[str]:
    errors = []
    if not str(rule.get("id", "")).strip():
        errors.append("ID regola obbligatorio.")
    if str(rule.get("severity", "")).upper() not in SEVERITIES:
        errors.append("Severita non valida.")
    if not str(rule.get("explanation", "")).strip():
        errors.append("Spiegazione obbligatoria.")
    if not str(rule.get("suggested_action", "")).strip():
        errors.append("Azione suggerita obbligatoria.")
    for key in ["event_types", "allowed_location_types", "forbidden_location_types"]:
        if not isinstance(rule.get(key, []), list):
            errors.append(f"{key} deve essere una lista.")
    if not isinstance(rule.get("conditions", {}), dict):
        errors.append("conditions deve essere una mappa.")
    try:
        int(rule.get("priority", 100))
    except (TypeError, ValueError):
        errors.append("Priorita deve essere un numero intero.")
    return errors


def test_rule_on_event(rule: dict[str, Any], event_dict: dict[str, Any]) -> dict[str, Any]:
    rule_id = _normalize_rule_id(rule.get("id", "test_rule"))
    config = {"rules": {rule_id: _normalize_rule(rule_id, rule)}, "thresholds": {}}
    decision = RuleEngine(config=config).evaluate(_event_from_dict(event_dict))
    return _decision_dict(decision)


def test_all_rules_on_event(event_dict: dict[str, Any], path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    decision = RuleEngine(config=load_rules(path)).evaluate(_event_from_dict(event_dict))
    return _decision_dict(decision)


def _set_rule_enabled(rule_id: str, enabled: bool, path: str | Path) -> None:
    data = load_rules(path)
    if rule_id not in data["rules"]:
        raise RulesConfigError("La regola selezionata non esiste.")
    data["rules"][rule_id]["enabled"] = enabled
    save_rules(data, path)


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    thresholds = dict(raw.get("thresholds") or {})
    legacy_washing = raw.get("suspected_washing", {})
    if "suspected_washing_duration_minutes" not in thresholds and isinstance(legacy_washing, dict):
        thresholds["suspected_washing_duration_minutes"] = legacy_washing.get(
            "door_opening_parking_duration_threshold_minutes",
            5,
        )
    thresholds.setdefault("long_pause_minutes", 30)
    thresholds.setdefault("min_pause_minutes", 5)
    rules = raw.get("rules", {})
    if isinstance(rules, list):
        normalized_rules = {
            _normalize_rule_id(rule.get("id", f"rule_{index}")): _normalize_rule(
                rule.get("id", f"rule_{index}"),
                rule,
                legacy_config=raw,
            )
            for index, rule in enumerate(rules, start=1)
            if isinstance(rule, dict)
        }
    elif isinstance(rules, dict):
        normalized_rules = {
            _normalize_rule_id(rule_id): _normalize_rule(rule_id, rule)
            for rule_id, rule in rules.items()
            if isinstance(rule, dict)
        }
    else:
        raise RulesConfigError("La chiave rules deve essere una lista o una mappa.")
    return {
        "ignored_event_types": list(raw.get("ignored_event_types", [])),
        "thresholds": thresholds,
        "rules": dict(sorted(normalized_rules.items(), key=lambda item: (item[1].get("priority", 100), item[0]))),
    }


def _normalize_rule(rule_id: str, rule: dict[str, Any], legacy_config: dict[str, Any] | None = None) -> dict[str, Any]:
    rule_id = _normalize_rule_id(rule_id)
    conditions = dict(rule.get("conditions") or {})
    legacy_condition = rule.get("condition")
    if legacy_condition and not conditions:
        conditions = _legacy_conditions(str(legacy_condition), legacy_config or {})
    allowed_locations = list(
        rule.get("allowed_location_types")
        or conditions.pop("allowed_location_types", [])
        or []
    )
    forbidden_locations = list(
        rule.get("forbidden_location_types")
        or conditions.pop("forbidden_location_types", [])
        or []
    )
    generated_name = _title_from_id(rule_id)
    current_name = str(rule.get("name_it") or "")
    name_it = KNOWN_RULE_NAMES.get(rule_id, current_name or generated_name)
    if current_name and current_name != generated_name:
        name_it = current_name
    if rule_id == "suspected_washing" and "duration_greater_than_minutes" in conditions:
        conditions["duration_greater_than_minutes"] = "suspected_washing_duration_minutes"
    severity = str(rule.get("severity", "INFO")).upper()
    if rule_id == "stop_on_residual" and severity == "HIGH":
        severity = "CRITICAL"
    return {
        "enabled": _to_bool(rule.get("enabled", True)),
        "name_it": name_it,
        "severity": severity,
        "event_types": list(rule.get("event_types") or _legacy_event_types(rule_id, conditions)),
        "source_sections": list(rule.get("source_sections") or []),
        "raw_ops": list(rule.get("raw_ops") or []),
        "allowed_location_types": allowed_locations,
        "forbidden_location_types": forbidden_locations,
        "conditions": conditions,
        "explanation": str(rule.get("explanation") or rule.get("reason") or rule_id),
        "suggested_action": str(rule.get("suggested_action") or "Verificare l'evento operativo."),
        "category": str(rule.get("category") or _category_from_id(rule_id)),
        "priority": int(
            KNOWN_RULE_PRIORITIES.get(rule_id, rule.get("priority", 100))
            if int(rule.get("priority", 100)) == 100
            else rule.get("priority", 100)
        ),
    }


def _legacy_conditions(condition: str, legacy_config: dict[str, Any]) -> dict[str, Any]:
    allowed = legacy_config.get("allowed_location_types", {})
    washing = legacy_config.get("suspected_washing", {})
    if condition == "pause_in_suspicious_area":
        return {"location_type_not_in_allowed": True, "allowed_location_types": allowed.get("pause", [])}
    if condition == "stop_on_residual":
        return {"has_stop_on_residual": True}
    if condition == "missing_residual_on_last_unload":
        return {"is_last_unload_for_product": True, "has_residual": False}
    if condition == "stop_on_last_unload":
        return {"is_last_unload_for_product": True, "has_stop_on_unload": True}
    if condition == "programming_in_unauthorized_area":
        return {"location_type_not_in_allowed": True, "allowed_location_types": allowed.get("programming", [])}
    if condition == "unload_in_unauthorized_area":
        return {"location_type_not_in_allowed": True, "allowed_location_types": allowed.get("unload", [])}
    if condition == "door_opening_in_unauthorized_area":
        return {"raw_type_contains_any": ["portellone", "door"], "location_type_not_in_allowed": True, "allowed_location_types": allowed.get("opening", [])}
    if condition == "valve_opening_in_unauthorized_area":
        return {"raw_type_contains_any": ["valvole", "valvola", "valve"], "location_type_not_in_allowed": True, "allowed_location_types": allowed.get("opening", [])}
    if condition == "coupler_opening_in_unauthorized_area":
        return {"raw_type_contains_any": ["accoppiatore", "coupler"], "location_type_not_in_allowed": True, "allowed_location_types": allowed.get("opening", [])}
    if condition == "suspected_washing":
        return {
            "raw_type_contains_any": ["portellone", "door"],
            "location_type_in_forbidden": True,
            "forbidden_location_types": ["parking"],
            "duration_greater_than_minutes": washing.get("door_opening_parking_duration_threshold_minutes", 5),
        }
    return {}


def _legacy_event_types(rule_id: str, conditions: dict[str, Any]) -> list[str]:
    if "pause" in rule_id:
        return ["stop_or_pause", "stop"]
    if "unload" in rule_id or "residual" in rule_id:
        return ["unload"]
    if "programming" in rule_id:
        return ["load"]
    if "door" in rule_id or "washing" in rule_id:
        return ["portellone", "door_opening", "operation"]
    if "valve" in rule_id:
        return ["valvole", "valve_opening", "operation"]
    if "coupler" in rule_id:
        return ["coupler_opening", "operation"]
    return list(conditions.get("event_types", []))


def _event_from_dict(row: dict[str, Any]) -> ClickAndFindEvent:
    now = datetime.now().replace(microsecond=0)
    return ClickAndFindEvent(
        event_id="simulated-event",
        check_date=date.today(),
        company="Simulazione",
        vehicle_id="SIM",
        tractor_id="",
        trailer_id="",
        event_type=row.get("event_type", "operation"),
        timestamp_start=now,
        timestamp_end=now,
        duration_minutes=float(row.get("duration_minutes") or 0),
        latitude=None,
        longitude=None,
        location_name=row.get("location_name", ""),
        location_type=row.get("location_type", "unknown"),
        raw_text=row.get("raw_text", ""),
        source_section=row.get("source_section", "operations"),
        raw_type=row.get("raw_type", ""),
        raw_op=row.get("raw_op", ""),
        has_residual=row.get("has_residual", False),
        has_stop_on_residual=row.get("has_stop_on_residual", False),
        has_stop_on_unload=row.get("has_stop_on_unload", False),
        is_last_unload_for_product=row.get("is_last_unload_for_product", False),
        operation_duration_minutes=float(row.get("duration_minutes") or 0),
    )


def _decision_dict(decision) -> dict[str, Any]:
    return {
        "severity": decision.severity.upper(),
        "risk_score": _score(decision.severity),
        "matched_rules": decision.matched_rules,
        "reasons": decision.reasons,
        "suggested_actions": decision.suggested_actions,
    }


def _score(severity: str) -> int:
    return {"critical": 100, "high": 75, "medium": 50, "low": 25, "info": 10, "ok": 0}.get(str(severity).lower(), 0)


def _normalize_rule_id(value: str) -> str:
    return "_".join(part for part in str(value).strip().lower().replace("-", "_").split("_") if part)


def _title_from_id(rule_id: str) -> str:
    return " ".join(part.capitalize() for part in rule_id.split("_"))


def _category_from_id(rule_id: str) -> str:
    for category in ["pause", "residual", "unload", "load", "opening", "washing"]:
        if category in rule_id:
            return category
    return "operational"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "s"}
