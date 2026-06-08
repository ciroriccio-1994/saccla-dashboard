from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from network_classification import RELEVANT_ENDPOINT_TYPES, classify_endpoint, merged_parameters, url_without_query


NETWORK_DIR = Path("outputs/network_logs")
SUMMARY_PATH = NETWORK_DIR / "network_summary.csv"
JSON_DIR = NETWORK_DIR / "json_responses"
XML_DIR = NETWORK_DIR / "xml_responses"
TEXT_DIR = NETWORK_DIR / "text_responses"


def main() -> None:
    if not SUMMARY_PATH.exists():
        raise SystemExit(f"Missing {SUMMARY_PATH}. Run scripts/inspect_network.py first.")

    df = pd.read_csv(SUMMARY_PATH).fillna("")
    if "endpoint_type" not in df.columns:
        df["endpoint_type"] = [
            classify_endpoint(row.url, getattr(row, "post_data_preview", ""))
            for row in df.itertuples(index=False)
        ]
    print(f"Captured responses: {len(df)}")
    print(f"Saved JSON files: {len(list(JSON_DIR.glob('response_*.json')))}")
    print(f"Saved XML files: {len(list(XML_DIR.glob('response_*.xml')))}")
    print(f"Saved TXT files: {len(list(TEXT_DIR.glob('response_*.txt')))}")
    print()

    print("Endpoint counts by endpoint_type:")
    endpoint_counts = Counter(df["endpoint_type"])
    for endpoint_type, count in endpoint_counts.most_common():
        print(f"- {endpoint_type}: {count}")
    print()

    relevant = df[df["endpoint_type"].isin(RELEVANT_ENDPOINT_TYPES)].copy()
    print("Unique relevant ClickAndFind endpoint URLs:")
    unique_urls = sorted({url_without_query(url) for url in relevant["url"]})
    if unique_urls:
        for url in unique_urls:
            print(f"- {url}")
    else:
        print("- None")
    print()

    print("Examples of query parameters by endpoint:")
    examples = _parameter_examples(relevant)
    if examples:
        for endpoint, params in examples.items():
            print(f"- {endpoint}")
            for key, values in sorted(params.items()):
                joined = ", ".join(values[:5])
                print(f"  {key}: {joined}")
    else:
        print("- None")
    print()

    for parameter in ["codtrasp", "startdate", "op"]:
        values = _collect_parameter_values(df, parameter)
        print(f"Examples of {parameter} values:")
        if values:
            for value in values[:10]:
                print(f"- {value}")
        else:
            print("- None")
        print()


def _parameter_examples(df: pd.DataFrame) -> dict[str, dict[str, list[str]]]:
    examples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in df.itertuples(index=False):
        endpoint = url_without_query(row.url)
        params = merged_parameters(row.url, getattr(row, "post_data_preview", ""))
        for key, values in params.items():
            for value in values:
                if value and value not in examples[endpoint][key]:
                    examples[endpoint][key].append(value)
    return examples


def _collect_parameter_values(df: pd.DataFrame, parameter: str) -> list[str]:
    values: list[str] = []
    for row in df.itertuples(index=False):
        params = merged_parameters(row.url, getattr(row, "post_data_preview", ""))
        for value in params.get(parameter, []):
            if value and value not in values:
                values.append(value)
    return values


if __name__ == "__main__":
    main()
