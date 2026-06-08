from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from core.models import ClickAndFindEvent


class ClickAndFindAdapter(ABC):
    """Replaceable boundary for ClickAndFind data acquisition."""

    @abstractmethod
    def fetch_events(
        self,
        check_date: date | None = None,
        company: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[ClickAndFindEvent]:
        """Return normalized ClickAndFind events."""

    def close(self) -> None:
        """Release resources when an adapter uses external connections."""

