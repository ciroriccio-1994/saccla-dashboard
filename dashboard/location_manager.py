from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml

from core.location_classifier import classify_location


DEFAULT_PATH = Path("config/location_aliases.yaml")
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


class LocationAliasesError(ValueError):
    """Raised when the location aliases file is malformed."""


def load_location_aliases(path: str | Path = DEFAULT_PATH) -> dict[str, list[dict[str, Any]]]:
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("locations: []\n", encoding="utf-8")
        return {"locations": []}

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise LocationAliasesError(f"Il file {path} contiene YAML non valido: {exc}") from exc
    except OSError as exc:
        raise LocationAliasesError(f"Impossibile leggere il file {path}: {exc}") from exc

    if raw is None:
        raw = {"locations": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("locations", []), list):
        raise LocationAliasesError("Il file deve contenere una struttura YAML con la chiave 'locations' e una lista.")

    locations = []
    for index, alias in enumerate(raw.get("locations", []), start=1):
        if not isinstance(alias, dict):
            raise LocationAliasesError(f"L'alias in posizione {index} non e un oggetto valido.")
        normalized = _normalize_alias(alias)
        errors = validate_location_alias(normalized)
        if errors:
            raise LocationAliasesError(f"Alias {index} non valido: {'; '.join(errors)}")
        locations.append(normalized)
    return {"locations": sorted(locations, key=lambda item: (item["priority"], item["label"].casefold()))}


def save_location_aliases(
    data: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    path: str | Path = DEFAULT_PATH,
) -> Path:
    path = Path(path)
    locations = data.get("locations", []) if isinstance(data, dict) else data
    if not isinstance(locations, list):
        raise LocationAliasesError("I luoghi da salvare devono essere una lista.")

    normalized_locations = []
    for index, alias in enumerate(locations, start=1):
        normalized = _normalize_alias(alias)
        errors = validate_location_alias(normalized)
        if errors:
            raise LocationAliasesError(f"Alias {index} non valido: {'; '.join(errors)}")
        normalized_locations.append(normalized)

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.stem}.backup_{timestamp}{path.suffix}")
        counter = 2
        while backup.exists():
            backup = path.with_name(f"{path.stem}.backup_{timestamp}_{counter}{path.suffix}")
            counter += 1
        shutil.copy2(path, backup)

    payload = {"locations": sorted(normalized_locations, key=lambda item: (item["priority"], item["label"].casefold()))}
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    except OSError as exc:
        raise LocationAliasesError(f"Impossibile salvare il file {path}: {exc}") from exc
    return path


def add_location_alias(
    *,
    match: str,
    location_type: str,
    label: str,
    city: str = "",
    notes: str = "",
    active: bool = True,
    priority: int = 100,
    path: str | Path = DEFAULT_PATH,
) -> dict[str, Any]:
    data = load_location_aliases(path)
    alias = _normalize_alias(
        {
            "match": match,
            "city": city,
            "location_type": location_type,
            "label": label,
            "notes": notes,
            "active": active,
            "priority": priority,
        }
    )
    errors = validate_location_alias(alias)
    if errors:
        raise LocationAliasesError("; ".join(errors))
    if any(item["match"].casefold() == alias["match"].casefold() for item in data["locations"]):
        raise LocationAliasesError("Esiste gia un alias con la stessa stringa di ricerca.")
    data["locations"].append(alias)
    save_location_aliases(data, path)
    return alias


def update_location_alias(
    alias_id: str,
    *,
    match: str,
    location_type: str,
    label: str,
    city: str = "",
    notes: str = "",
    active: bool = True,
    priority: int = 100,
    path: str | Path = DEFAULT_PATH,
) -> dict[str, Any]:
    data = load_location_aliases(path)
    index = _find_index(data["locations"], alias_id)
    updated = _normalize_alias(
        {
            "id": alias_id,
            "match": match,
            "city": city,
            "location_type": location_type,
            "label": label,
            "notes": notes,
            "active": active,
            "priority": priority,
        }
    )
    errors = validate_location_alias(updated)
    if errors:
        raise LocationAliasesError("; ".join(errors))
    data["locations"][index] = updated
    save_location_aliases(data, path)
    return updated


def delete_location_alias(alias_id: str, path: str | Path = DEFAULT_PATH) -> None:
    data = load_location_aliases(path)
    index = _find_index(data["locations"], alias_id)
    del data["locations"][index]
    save_location_aliases(data, path)


def validate_location_alias(alias: dict[str, Any]) -> list[str]:
    errors = []
    if not str(alias.get("match", "")).strip():
        errors.append("Il campo match e obbligatorio.")
    if not str(alias.get("label", "")).strip():
        errors.append("Il campo label e obbligatorio.")
    if alias.get("location_type") not in LOCATION_TYPES:
        errors.append("Il tipo luogo non e valido.")
    try:
        int(alias.get("priority", 100))
    except (TypeError, ValueError):
        errors.append("La priorita deve essere un numero intero.")
    return errors


def classify_test_location(text: str, path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    result = classify_location(location_name=text, raw_text=text, address=text, aliases_path=path)
    return {
        "location_type": result.location_type,
        "label": result.label,
        "matched_alias_id": result.matched_alias_id,
        "location_confidence": result.location_confidence,
        "location_rule_source": result.location_rule_source,
        "notes": result.notes,
    }


def _normalize_alias(alias: dict[str, Any]) -> dict[str, Any]:
    match = str(alias.get("match", "") or "").strip()
    city = str(alias.get("city", "") or "").strip()
    label = str(alias.get("label", "") or "").strip()
    try:
        priority = int(alias.get("priority", 100))
    except (TypeError, ValueError) as exc:
        raise LocationAliasesError("La priorita deve essere un numero intero.") from exc
    return {
        "id": str(alias.get("id") or uuid5(NAMESPACE_URL, f"clickandfind:{match}:{city}:{label}")),
        "match": match,
        "city": city,
        "location_type": str(alias.get("location_type", "") or "").strip(),
        "label": label,
        "notes": str(alias.get("notes", "") or "").strip(),
        "active": _to_bool(alias.get("active", True)),
        "priority": priority,
    }


def _find_index(locations: list[dict[str, Any]], alias_id: str) -> int:
    for index, alias in enumerate(locations):
        if alias["id"] == alias_id:
            return index
    raise LocationAliasesError("Il luogo selezionato non esiste piu.")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}
