from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml


SOURCE_PATH = Path("outputs/network_logs/relevant_endpoints.csv")
OUTPUT_PATH = Path("config/internal_endpoints.yaml")
ENDPOINT_TYPES = [
    "vehicles_list",
    "parking_list",
    "tracking",
    "operations",
    "alarms",
    "driver_status",
]
EXPECTED_METHODS = {
    "vehicles_list": "POST",
    "parking_list": "POST",
    "tracking": "GET",
    "operations": "GET",
    "alarms": "GET",
    "driver_status": "GET",
}


def main() -> None:
    if not SOURCE_PATH.exists():
        raise SystemExit(f"Missing {SOURCE_PATH}. Run the network inspector first.")

    endpoints: dict[str, dict[str, str]] = {}
    with SOURCE_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for endpoint_type in ENDPOINT_TYPES:
        matching = [row for row in rows if row.get("endpoint_type") == endpoint_type and row.get("url")]
        if not matching:
            print(f"No captured URL found for {endpoint_type}")
            continue
        preferred = next(
            (row for row in matching if row.get("method", "").upper() == EXPECTED_METHODS[endpoint_type]),
            matching[0],
        )
        endpoints[endpoint_type] = {
            "url": without_query(preferred["url"]),
            "method": EXPECTED_METHODS[endpoint_type],
        }
        print(f"{endpoint_type}: {EXPECTED_METHODS[endpoint_type]} {endpoints[endpoint_type]['url']}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump({"endpoints": endpoints}, handle, sort_keys=False, allow_unicode=False)
    print(f"Saved {OUTPUT_PATH}")


def without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


if __name__ == "__main__":
    main()
