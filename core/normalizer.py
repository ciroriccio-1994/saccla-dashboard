from __future__ import annotations

import re


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def normalize_location_type(value: str) -> str:
    return normalize_key(value)


def normalize_event_type(value: str) -> str:
    return normalize_key(value)

