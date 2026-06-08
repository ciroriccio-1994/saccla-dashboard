from __future__ import annotations

import argparse
from dotenv import load_dotenv

from adapters.mock_adapter import MockClickAndFindAdapter
from core.rules import RuleEngine
from reports.excel_report import write_excel_report
from storage.database import Database, resolve_database_path


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run ClickAndFind operational controls.")
    parser.add_argument("--events", default="data/mock_events.csv")
    parser.add_argument("--rules", default="config/rules.yaml")
    parser.add_argument("--database", default=resolve_database_path())
    parser.add_argument("--report", default="outputs/reports/clickandfind_report.xlsx")
    args = parser.parse_args()

    adapter = MockClickAndFindAdapter(args.events)
    events = adapter.fetch_events()
    evaluated_events = RuleEngine(args.rules).apply(events)

    db = Database(args.database)
    db.save_events(evaluated_events)
    df = db.load_events()
    report_path = write_excel_report(df, args.report)

    critical = int((df["severity"] == "critical").sum())
    high = int((df["severity"] == "high").sum())
    medium = int((df["severity"] == "medium").sum())
    print(f"Saved {len(df)} events to {args.database}")
    print(f"Anomalies: critical={critical}, high={high}, medium={medium}")
    print(f"Excel report: {report_path}")


if __name__ == "__main__":
    main()
