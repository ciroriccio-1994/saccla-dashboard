from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from adapters.base import ClickAndFindAdapter
from core.models import ClickAndFindEvent, events_from_dataframe


class MockClickAndFindAdapter(ClickAndFindAdapter):
    def __init__(self, csv_path: str | Path = "data/mock_events.csv") -> None:
        self.csv_path = Path(csv_path)

    def fetch_events(
        self,
        check_date: date | None = None,
        company: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[ClickAndFindEvent]:
        df = pd.read_csv(self.csv_path)
        if check_date is not None:
            df = df[pd.to_datetime(df["check_date"]).dt.date == check_date]
        if company:
            df = df[df["company"] == company]
        if vehicle_id:
            df = df[df["vehicle_id"] == vehicle_id]
        return events_from_dataframe(df)

