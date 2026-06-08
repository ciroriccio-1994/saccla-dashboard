from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from core.location_classifier import classify_location
from core.models import ClickAndFindEvent


def find_vehicle_metadata(records: Iterable[dict[str, Any]], codtrasp: str | int) -> dict[str, Any]:
    target = str(codtrasp)
    for record in records:
        if _text(_get(record, "codtrasp")) == target:
            return record
    return {}


def normalize_vehicle_check(
    check_result: dict[str, Any],
    vehicle_metadata: dict[str, Any],
    check_date: str | date,
    company: str,
    include_tracking: bool = False,
) -> list[ClickAndFindEvent]:
    events: list[ClickAndFindEvent] = []
    operations = check_result.get("operations", {})
    if isinstance(operations, dict):
        for op, response in operations.items():
            for record in _records(response):
                events.append(normalize_operation(record, op, vehicle_metadata, check_date, company))

    for record in _records(check_result.get("alarms", {})):
        events.append(normalize_alarm(record, vehicle_metadata, check_date, company))

    if include_tracking:
        for record in _records(check_result.get("tracking", {})):
            events.append(normalize_tracking(record, vehicle_metadata, check_date, company))
    return _post_process_operational_flags(events)


def normalize_operation(
    record: dict[str, Any],
    request_op: str,
    vehicle: dict[str, Any],
    check_date: str | date,
    company: str,
) -> ClickAndFindEvent:
    if request_op == "03":
        event_type = "load"
        raw_type = "carico"
        start = _datetime(record, ["eventdate", "oratestata", "rxdate"], check_date)
        end = start
        duration = 0.0
    elif request_op == "04":
        event_type = "unload"
        raw_type = "scarico"
        start = _datetime(record, ["orareale", "orainiziale", "eventdate"], check_date)
        duration = _duration_minutes(record, ["durataSec", "duration", "durata"])
        end = _datetime(record, ["orafinale", "orarealeFinale"], check_date, fallback=start + timedelta(minutes=duration))
    elif request_op == "pause":
        event_type = "stop_or_pause"
        raw_type = "pausa"
        start = _datetime(record, ["begin", "tempo", "eventdate"], check_date)
        end = _datetime(record, ["end"], check_date, fallback=start)
        duration = _duration_minutes(record, ["duration", "durata", "durataSec"])
        if duration == 0 and end >= start:
            duration = (end - start).total_seconds() / 60
    elif request_op == "0B":
        event_type = "residual_or_other"
        raw_type = _text(_get(record, "op")) or "0B"
        start = _datetime(record, ["tempo", "eventdate", "begin"], check_date)
        end = _datetime(record, ["end", "orafinale"], check_date, fallback=start)
        duration = _duration_minutes(record, ["duration", "durata", "durataSec"])
    else:
        raw_type = _text(_get(record, "op")) or "operation"
        event_type = _normalize_event_name(raw_type) if raw_type else "operation"
        start = _datetime(record, ["tempo", "eventdate", "orareale", "begin", "te_time"], check_date)
        end = _datetime(record, ["end", "orafinale", "orarealeFinale"], check_date, fallback=start)
        duration = _duration_minutes(record, ["duration", "durata", "durataSec"])

    return _event(
        record=record,
        vehicle=vehicle,
        company=company,
        check_date=check_date,
        event_type=event_type,
        source_section="operations",
        raw_type=raw_type,
        raw_op=request_op,
        start=start,
        end=end,
        duration=duration,
        product=_product(record),
        has_residual=_has_residual(record),
        has_stop_on_residual=_has_stop_on_residual(record),
        has_stop_on_unload=_has_stop_on_unload(record),
    )


def normalize_alarm(
    record: dict[str, Any],
    vehicle: dict[str, Any],
    check_date: str | date,
    company: str,
) -> ClickAndFindEvent:
    raw_type = _text(_get(record, "op")) or "alarm"
    start = _datetime(record, ["tempo", "eventdate", "date"], check_date)
    return _event(
        record=record,
        vehicle=vehicle,
        company=company,
        check_date=check_date,
        event_type="alarm",
        source_section="alarms",
        raw_type=raw_type,
        raw_op="allarmi2",
        start=start,
        end=start,
        duration=0,
        product=_product(record),
    )


def normalize_tracking(
    record: dict[str, Any],
    vehicle: dict[str, Any],
    check_date: str | date,
    company: str,
) -> ClickAndFindEvent:
    start = _datetime(record, ["tempo", "eventdate", "date"], check_date)
    return _event(
        record=record,
        vehicle=vehicle,
        company=company,
        check_date=check_date,
        event_type="tracking_position",
        source_section="tracking",
        raw_type="position",
        raw_op="tracking",
        start=start,
        end=start,
        duration=0,
        product=_product(record),
    )


def _event(
    record: dict[str, Any],
    vehicle: dict[str, Any],
    company: str,
    check_date: str | date,
    event_type: str,
    source_section: str,
    raw_type: str,
    raw_op: str,
    start: datetime,
    end: datetime,
    duration: float,
    product: str = "",
    has_residual: bool = False,
    has_stop_on_residual: bool = False,
    has_stop_on_unload: bool = False,
) -> ClickAndFindEvent:
    codtrasp = _text(_get(vehicle, "codtrasp"))
    tractor = _text(_get(vehicle, "tractor_plate", "targa", "motrice"))
    trailer = _text(_get(vehicle, "semitrailer_plate", "trailer", "semirimorchio"))
    terminal = _text(_get(vehicle, "terminal_id", "terminal"))
    vehicle_id = tractor or terminal or codtrasp or "unknown"
    raw_text = json.dumps(record, ensure_ascii=False, default=str, sort_keys=True)
    event_id = _event_id(codtrasp, source_section, raw_op, start, record)
    location_name = _text(_get(record, "ind", "location_name", "address", "indirizzo"))
    classification = classify_location(location_name=location_name, raw_text=raw_text, address=location_name)
    operation_duration = max(duration, 0)
    is_programming_like_load = event_type == "load" and classification.location_type in {
        "parking",
        "suspicious",
        "road_or_highway",
        "unknown",
    }
    return ClickAndFindEvent(
        event_id=event_id,
        check_date=_date(check_date),
        company=company or _text(_get(vehicle, "compagnie", "company")) or "ClickAndFind",
        vehicle_id=vehicle_id,
        tractor_id=tractor,
        trailer_id=trailer,
        event_type=event_type,
        timestamp_start=start,
        timestamp_end=max(end, start),
        duration_minutes=max(duration, 0),
        latitude=_float(_get(record, "lat", "latitude")),
        longitude=_float(_get(record, "lon", "lng", "longitude")),
        location_name=classification.label or location_name,
        location_type=classification.location_type,
        raw_text=raw_text,
        source_section=source_section,
        severity="info",
        reasons=[],
        codtrasp=codtrasp,
        tractor_plate=tractor,
        semitrailer_plate=trailer,
        terminal_id=terminal,
        raw_type=raw_type,
        raw_op=raw_op,
        product=product,
        has_residual=has_residual,
        has_stop_on_residual=has_stop_on_residual,
        has_stop_on_unload=has_stop_on_unload,
        is_programming_like_load=is_programming_like_load,
        operation_duration_minutes=operation_duration,
        location_confidence=classification.confidence,
        location_rule_source=classification.source,
        location_notes=classification.notes,
    )


def _post_process_operational_flags(events: list[ClickAndFindEvent]) -> list[ClickAndFindEvent]:
    processed = _mark_last_unloads(events)
    return _calculate_door_open_durations(processed)


def _mark_last_unloads(events: list[ClickAndFindEvent]) -> list[ClickAndFindEvent]:
    last_ids: set[str] = set()
    groups: dict[tuple[str, date, str], list[ClickAndFindEvent]] = {}
    for event in events:
        if event.event_type != "unload":
            continue
        key = (event.codtrasp, event.check_date, event.product or "unknown")
        groups.setdefault(key, []).append(event)
    for grouped in groups.values():
        last = max(grouped, key=lambda item: item.timestamp_start)
        last_ids.add(last.event_id)
    return [
        ClickAndFindEvent(**{**event.to_dict(), "is_last_unload_for_product": event.event_id in last_ids})
        if event.event_type == "unload"
        else event
        for event in events
    ]


def _calculate_door_open_durations(events: list[ClickAndFindEvent]) -> list[ClickAndFindEvent]:
    by_vehicle: dict[str, list[ClickAndFindEvent]] = {}
    for event in events:
        by_vehicle.setdefault(event.vehicle_id, []).append(event)

    duration_by_id: dict[str, float] = {}
    for vehicle_events in by_vehicle.values():
        open_event: ClickAndFindEvent | None = None
        for event in sorted(vehicle_events, key=lambda item: item.timestamp_start):
            if event.event_type not in {"portellone", "door_opening"}:
                continue
            state = _door_state(event)
            if state == "open":
                open_event = event
            elif state == "closed" and open_event is not None and event.timestamp_start >= open_event.timestamp_start:
                duration_by_id[open_event.event_id] = (event.timestamp_start - open_event.timestamp_start).total_seconds() / 60
                open_event = None

    result: list[ClickAndFindEvent] = []
    for event in events:
        duration = duration_by_id.get(event.event_id)
        if duration is None:
            result.append(event)
            continue
        result.append(
            ClickAndFindEvent(
                **{
                    **event.to_dict(),
                    "duration_minutes": max(event.duration_minutes, duration),
                    "operation_duration_minutes": max(event.operation_duration_minutes, duration),
                }
            )
        )
    return result


def _records(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict) and isinstance(response.get("records"), list):
        return response["records"]
    return []


def _event_id(
    codtrasp: str,
    section: str,
    op: str,
    timestamp: datetime,
    record: dict[str, Any],
) -> str:
    native_id = _text(_get(record, "eventid", "prog", "progstop", "id"))
    seed = f"{codtrasp}|{section}|{op}|{timestamp.isoformat()}|{native_id}|{json.dumps(record, sort_keys=True, default=str)}"
    return f"real-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def _get(record: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        value = normalized.get(name.lower())
        if not _missing(value):
            return value
    return None


def _datetime(
    record: dict[str, Any],
    fields: list[str],
    check_date: str | date,
    fallback: datetime | None = None,
) -> datetime:
    for field in fields:
        value = _get(record, field)
        parsed = _parse_datetime(value, check_date)
        if parsed:
            return parsed
    return fallback or datetime.combine(_date(check_date), datetime.min.time())


def _parse_datetime(value: Any, check_date: str | date) -> datetime | None:
    if _missing(value):
        return None
    text = str(value).strip()
    for candidate in [text, f"{_date(check_date).isoformat()} {text}"]:
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _duration_minutes(record: dict[str, Any], fields: list[str]) -> float:
    for field in fields:
        value = _float(_get(record, field))
        if value is not None:
            return value / 60 if field.lower() == "duratasec" else value
    return 0.0


def _product(record: dict[str, Any]) -> str:
    return _text(
        _get(
            record,
            "prodotto",
            "product",
            "descprodotto",
            "nomeprodotto",
            "carburante",
        )
    )


def _has_residual(record: dict[str, Any]) -> bool:
    raw = _record_text(record)
    value = _get(record, "residuo", "residual", "rnera", "r_nera")
    return _truthy(value) or "r nera" in raw or "residuo" in raw


def _has_stop_on_unload(record: dict[str, Any]) -> bool:
    raw = _record_text(record)
    value = _get(record, "stopScarico", "stop_scarico", "sbianca", "s_bianca")
    return _truthy(value) or "s bianca" in raw or "stop scarico" in raw


def _has_stop_on_residual(record: dict[str, Any]) -> bool:
    raw = _record_text(record)
    value = _get(record, "stopResiduo", "stop_residuo", "snera", "s_nera")
    return _truthy(value) or "s nera" in raw or "stop residuo" in raw


def _door_state(event: ClickAndFindEvent) -> str:
    raw = event.raw_text.lower()
    if '"dati": "1"' in raw or '"dati": 1' in raw or "apertura" in raw or "open" in raw:
        return "open"
    if '"dati": "0"' in raw or '"dati": 0' in raw or "chiusura" in raw or "closed" in raw or "close" in raw:
        return "closed"
    return ""


def _record_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, default=str).casefold()


def _truthy(value: Any) -> bool:
    if _missing(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().casefold()
    return text not in {"", "0", "false", "no", "n", "none", "null"}


def _date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _float(value: Any) -> float | None:
    if _missing(value):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _text(value: Any) -> str:
    return "" if _missing(value) else str(value).strip()


def _missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null"}


def _normalize_event_name(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "_" for character in value)
    return "_".join(part for part in normalized.split("_") if part) or "operation"
