from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.clickandfind_internal_api import ClickAndFindInternalApiAdapter
from core.clickandfind_real_normalizer import find_vehicle_metadata, normalize_vehicle_check
from core.models import events_to_dataframe
from core.rules import RuleEngine
from reports.excel_report import write_excel_report
from storage.database import Database, resolve_database_path


def main() -> None:
    load_dotenv()
    args = parse_args()

    adapter = ClickAndFindInternalApiAdapter()
    try:
        adapter.login()
        vehicles_response = adapter.get_vehicles()
        vehicle_metadata = find_vehicle_metadata(vehicles_response.get("records", []), args.codtrasp)
        if not vehicle_metadata:
            print(f"Warning: no vehicle metadata found for codtrasp={args.codtrasp}")

        raw_check = adapter.run_vehicle_check(args.codtrasp, args.date, tag=args.tag)
        events = normalize_vehicle_check(
            raw_check,
            vehicle_metadata=vehicle_metadata,
            check_date=args.date,
            company=os.getenv("CLICKANDFIND_COMPANY", "ClickAndFind"),
            include_tracking=args.include_tracking,
        )
    finally:
        adapter.close()

    evaluated_events = RuleEngine(args.rules).apply(events)
    database = Database(args.database)
    database.save_events(evaluated_events)
    report_path = write_excel_report(events_to_dataframe(evaluated_events), args.report)

    severities = [event.severity for event in evaluated_events]
    anomalies = [severity for severity in severities if severity in {"critical", "high", "medium"}]
    print(f"Events normalized: {len(evaluated_events)}")
    print(f"Anomalies found: {len(anomalies)}")
    print(f"Critical: {severities.count('critical')}")
    print(f"High: {severities.count('high')}")
    print(f"Medium: {severities.count('medium')}")
    print(f"Database path: {args.database}")
    print(f"Report path: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real single-vehicle ClickAndFind check.")
    parser.add_argument("--codtrasp", default="9939")
    parser.add_argument("--date", default="2026-05-27")
    parser.add_argument("--tag", default=None)
    parser.add_argument("--include-tracking", action="store_true")
    parser.add_argument("--rules", default="config/rules.yaml")
    parser.add_argument("--database", default=resolve_database_path())
    parser.add_argument(
        "--report",
        default="outputs/reports/clickandfind_real_check.xlsx",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
