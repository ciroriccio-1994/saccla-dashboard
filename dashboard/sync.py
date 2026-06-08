from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from adapters.http_adapter import ClickAndFindHttpAdapter as ClickAndFindInternalApiAdapter
from core.clickandfind_real_normalizer import find_vehicle_metadata, normalize_vehicle_check
from core.models import ClickAndFindEvent
from core.rules import RuleEngine
from reports.excel_report import write_excel_report
from storage.database import Database, resolve_database_path


ProgressCallback = Callable[[int, int, str], None]
DEFAULT_REPORT_PATH = Path("outputs/reports/clickandfind_dashboard_sync.xlsx")


@dataclass
class SyncResult:
    success: bool
    vehicles_processed: int = 0
    events_normalized: int = 0
    anomalies_found: int = 0
    database_path: str = ""
    report_path: str = ""
    errors: list[str] = field(default_factory=list)


def vehicle_codtrasp(record: dict[str, Any]) -> str:
    return _text(_get(record, "codtrasp"))


def vehicle_label(record: dict[str, Any]) -> str:
    codtrasp = vehicle_codtrasp(record) or "N/D"
    tractor = _text(_get(record, "tractor_plate", "targa", "motrice"))
    trailer = _text(_get(record, "semitrailer_plate", "trailer", "semirimorchio"))
    terminal = _text(_get(record, "terminal_id", "terminal"))
    details = " / ".join(value for value in [tractor, trailer, terminal] if value)
    return f"{codtrasp} - {details}" if details else codtrasp


def unique_vehicles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        codtrasp = vehicle_codtrasp(record)
        if not codtrasp or codtrasp in seen:
            continue
        seen.add(codtrasp)
        result.append(record)
    return sorted(result, key=vehicle_label)


def sync_clickandfind_data(
    *,
    username: str,
    company: str,
    password: str,
    check_date: date,
    all_vehicles: bool = True,
    selected_codtrasp: str | None = None,
    max_vehicles: int = 5,
    database_path: str | None = None,
    rules_path: str = "config/rules.yaml",
    report_path: str | Path = DEFAULT_REPORT_PATH,
    progress_callback: ProgressCallback | None = None,
) -> SyncResult:
    database_path = resolve_database_path(database_path)
    report_path = Path(report_path)
    result = SyncResult(False, database_path=database_path, report_path=str(report_path))
    adapter = ClickAndFindInternalApiAdapter(
        username=username,
        company=company,
        password=password,
        login_mode="human_like",
        allow_manual_fallback=False,
        diagnostics_enabled=False,
    )
    evaluated_by_id: dict[str, ClickAndFindEvent] = {}

    try:
        if not adapter.login():
            result.errors.append("Login o attivazione della sessione servizi non riusciti.")
            return result

        vehicles_response = adapter.get_vehicles()
        available_vehicles = unique_vehicles(vehicles_response.get("records", []))
        selected = _select_vehicles(available_vehicles, all_vehicles, selected_codtrasp, max_vehicles)
        if not selected:
            result.errors.append("Nessun mezzo disponibile per la sincronizzazione.")
            return result

        rule_engine = RuleEngine(rules_path)
        for index, vehicle in enumerate(selected, start=1):
            codtrasp = vehicle_codtrasp(vehicle)
            label = vehicle_label(vehicle)
            if progress_callback:
                progress_callback(index - 1, len(selected), label)
            try:
                raw_check = adapter.run_vehicle_check(codtrasp, check_date)
                metadata = find_vehicle_metadata(available_vehicles, codtrasp) or vehicle
                events = normalize_vehicle_check(
                    raw_check,
                    vehicle_metadata=metadata,
                    check_date=check_date,
                    company=company,
                    include_tracking=False,
                )
                for event in rule_engine.apply(events):
                    evaluated_by_id[event.event_id] = event
                result.vehicles_processed += 1
            except Exception as exc:
                result.errors.append(f"{label}: {type(exc).__name__}: {exc}")
            if progress_callback:
                progress_callback(index, len(selected), label)

        evaluated_events = list(evaluated_by_id.values())
        database = Database(database_path)
        database.save_events(evaluated_events)
        report_df = database.load_events()
        if not report_df.empty and "check_date" in report_df.columns:
            report_df = report_df[report_df["check_date"].astype(str) == check_date.isoformat()]
        report_path = write_excel_report(report_df, report_path)
        result.events_normalized = len(evaluated_events)
        result.anomalies_found = sum(
            event.severity in {"critical", "high", "medium"} for event in evaluated_events
        )
        result.report_path = str(report_path)
        result.success = result.vehicles_processed > 0
        return result
    except Exception as exc:
        result.errors.append(f"Sincronizzazione interrotta: {type(exc).__name__}: {exc}")
        return result
    finally:
        adapter.close()


def _select_vehicles(
    available: list[dict[str, Any]],
    all_vehicles: bool,
    selected_codtrasp: str | None,
    max_vehicles: int,
) -> list[dict[str, Any]]:
    if all_vehicles:
        return available[: max(1, max_vehicles)]
    target = str(selected_codtrasp or "").strip()
    if not target:
        return []
    match = next((record for record in available if vehicle_codtrasp(record) == target), None)
    return [match or {"codtrasp": target}]


def _get(record: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None and str(value).strip():
            return value
    return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
