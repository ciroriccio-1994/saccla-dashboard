from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.clickandfind_internal_api import ClickAndFindInternalApiAdapter


OUTPUT_DIR = Path("outputs/api_diagnostics")
VEHICLE_FIELDS = {
    "codtrasp": ["codtrasp", "CodTrasp", "id", "terminal_id", "codice"],
    "tractor_plate": ["tractor_plate", "targa_motrice", "motrice", "targa", "plate", "targamotrice"],
    "semitrailer_plate": ["semitrailer_plate", "targa_semirimorchio", "semirimorchio", "trailer", "targasemi"],
    "terminal_id": ["terminal_id", "terminale", "terminal", "imei", "idterminale"],
    "driver": ["driver", "autista", "nome_autista", "conducente"],
    "compagnie": ["compagnie", "compagnia", "company", "azienda"],
    "parking": ["parking", "parcheggio", "parking_name"],
}


def main() -> None:
    load_dotenv()
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    adapter = ClickAndFindInternalApiAdapter()
    try:
        adapter.login()
        print(f"Login mode used: {adapter.login_mode_used}")
        print(f"Service session activation: {adapter.service_session_activation}")
        print(f"Service session activated automatically: {adapter.service_session_activation == 'automatic'}")
        print(f"Manual fallback required: {adapter.manual_fallback_required}")

        vehicles = safe_call("get_vehicles", adapter.get_vehicles)
        print_response_summary("vehicles", vehicles)
        vehicle_records = response_records(vehicles)
        write_csv(vehicle_records, OUTPUT_DIR / "vehicles.csv")
        print(f"Vehicles found: {len(vehicle_records)}")
        print_vehicle_examples(vehicle_records[:10])

        parking_areas = safe_call("get_parking_areas", adapter.get_parking_areas)
        print_response_summary("parking_areas", parking_areas)
        parking_records = response_records(parking_areas)
        write_csv(parking_records, OUTPUT_DIR / "parking_areas.csv")
        print(f"Parking areas found: {len(parking_records)}")

        tracking = safe_call("get_tracking", adapter.get_tracking, args.codtrasp, args.date, args.tag)
        print_response_summary("tracking", tracking)
        tracking_records = response_records(tracking)
        write_csv(tracking_records, OUTPUT_DIR / f"tracking_{args.codtrasp}_{args.date}.csv")
        print(f"Tracking records: {len(tracking_records)}")

        driver_status = safe_call("get_driver_status", adapter.get_driver_status, args.codtrasp, args.date)
        print_response_summary("driver_status", driver_status)
        print(f"Driver status records: {len(response_records(driver_status))}")

        operations = safe_call("get_all_operations", adapter.get_all_operations, args.codtrasp, args.date)
        print_operation_summaries(operations)
        operation_records = combined_operation_records(operations)
        write_csv(operation_records, OUTPUT_DIR / f"operations_{args.codtrasp}_{args.date}.csv")
        print(f"Operation records: {len(operation_records)}")

        alarms = safe_call("get_alarms", adapter.get_alarms, args.codtrasp, args.date)
        print_response_summary("alarms", alarms)
        alarm_records = response_records(alarms)
        write_csv(alarm_records, OUTPUT_DIR / f"alarms_{args.codtrasp}_{args.date}.csv")
        print(f"Alarm records: {len(alarm_records)}")

    finally:
        adapter.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose ClickAndFind internal API endpoints.")
    parser.add_argument("--codtrasp", default="9939")
    parser.add_argument("--date", default="2026-05-27")
    parser.add_argument("--tag", default=None)
    return parser.parse_args()


def safe_call(name: str, func, *args: Any) -> dict[str, Any]:
    try:
        return func(*args)
    except Exception as exc:
        print(f"{name} failed: {type(exc).__name__}: {exc}")
        return {"error": str(exc), "records": []}


def response_records(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        records = response.get("records", [])
        return records if isinstance(records, list) else []
    return []


def print_response_summary(name: str, response: Any) -> None:
    if not isinstance(response, dict):
        print(f"{name}: invalid response object")
        return
    print(
        f"{name}: type={response.get('response_type', '')} "
        f"node_type={response.get('record_node_type', '')} "
        f"records={len(response_records(response))} "
        f"parse_error={response.get('parse_error', '')} "
        f"raw_path={response.get('raw_path', '')}"
    )


def print_operation_summaries(operations: Any) -> None:
    if not isinstance(operations, dict):
        print("operations: invalid response object")
        return
    for op, response in operations.items():
        print_response_summary(f"operations[{op}]", response)


def combined_operation_records(operations: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not isinstance(operations, dict):
        return records
    for op, response in operations.items():
        for record in response_records(response):
            records.append({"op": op, **record})
    return records


def write_csv(records: list[dict[str, Any]], path: Path) -> None:
    dataframe = pd.DataFrame(records)
    dataframe.to_csv(path, index=False)
    print(f"Saved {path}")


def print_vehicle_examples(records: list[dict[str, Any]]) -> None:
    if not records:
        print("No vehicle examples available.")
        return
    print("First vehicles:")
    for record in records:
        values = {field: first_value(record, candidates) for field, candidates in VEHICLE_FIELDS.items()}
        print(
            "- "
            f"codtrasp={values['codtrasp']} | "
            f"tractor_plate={values['tractor_plate']} | "
            f"semitrailer_plate={values['semitrailer_plate']} | "
            f"terminal_id={values['terminal_id']} | "
            f"driver={values['driver']} | "
            f"compagnie={values['compagnie']} | "
            f"parking={values['parking']}"
        )


def first_value(record: dict[str, Any], candidates: list[str]) -> str:
    normalized = {key.lower().replace("-", "_"): value for key, value in record.items()}
    for candidate in candidates:
        key = candidate.lower().replace("-", "_")
        if key in normalized and normalized[key] not in ("", None):
            return str(normalized[key])
    return ""


if __name__ == "__main__":
    main()
