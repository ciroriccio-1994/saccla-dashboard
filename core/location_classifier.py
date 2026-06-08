from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml


DEFAULT_ALIASES_PATH = Path("config/location_aliases.yaml")


@dataclass(frozen=True)
class LocationClassification:
    location_type: str
    label: str
    confidence: float
    source: str
    notes: str = ""
    matched_alias_id: str = ""

    @property
    def location_confidence(self) -> float:
        return self.confidence

    @property
    def location_rule_source(self) -> str:
        return self.source


KEYWORD_RULES = [
    ("parking", ["parcheggio", "parking", "sosta"]),
    ("refinery", ["raffineria", "refinery"]),
    ("depot", ["deposito", "depot"]),
    ("workshop", ["officina", "workshop"]),
    ("gas_station", ["pompa", "benzina", "stazione servizio", "stazione di servizio", "distributore"]),
    ("service_area", ["area servizio", "area di servizio", "autogrill"]),
    ("suspicious", ["isolato", "zona sospetta", "luogo sospetto"]),
    ("road_or_highway", ["autostrada", "tangenziale", "raccordo", "svincolo"]),
    ("unknown", ["sconosciuto", "unknown"]),
]


def classify_location(
    location_name: str = "",
    raw_text: str = "",
    address: str = "",
    aliases_path: str | Path = DEFAULT_ALIASES_PATH,
) -> LocationClassification:
    haystack = _normalize(" ".join([location_name or "", address or "", raw_text or ""]))
    if not haystack:
        return LocationClassification("unknown", "", 0.0, "empty")

    for alias in _load_aliases(aliases_path):
        match = _normalize(alias.get("match", ""))
        if match and match in haystack:
            return LocationClassification(
                location_type=str(alias.get("location_type", "unknown")).strip() or "unknown",
                label=str(alias.get("label") or alias.get("match") or "").strip(),
                confidence=0.95,
                source="location_aliases",
                notes=str(alias.get("notes", "") or "").strip(),
                matched_alias_id=_alias_id(alias),
            )

    for location_type, keywords in KEYWORD_RULES:
        if any(keyword in haystack for keyword in keywords):
            return LocationClassification(
                location_type=location_type,
                label=location_name or address,
                confidence=0.65,
                source="keyword",
            )

    return LocationClassification("unknown", location_name or address, 0.2, "fallback")


def _load_aliases(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    aliases = config.get("locations", config if isinstance(config, list) else [])
    if not isinstance(aliases, list):
        return []
    active_aliases = [alias for alias in aliases if isinstance(alias, dict) and _to_bool(alias.get("active", True))]
    return sorted(active_aliases, key=_priority)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(value).casefold()).split())


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _priority(alias: dict[str, Any]) -> int:
    try:
        return int(alias.get("priority", 100))
    except (TypeError, ValueError):
        return 100


def _alias_id(alias: dict[str, Any]) -> str:
    existing = str(alias.get("id", "") or "").strip()
    if existing:
        return existing
    match = str(alias.get("match", "") or "").strip()
    city = str(alias.get("city", "") or "").strip()
    label = str(alias.get("label", "") or "").strip()
    return str(uuid5(NAMESPACE_URL, f"clickandfind:{match}:{city}:{label}"))
