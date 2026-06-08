from __future__ import annotations

from datetime import date

from adapters.base import ClickAndFindAdapter
from core.models import ClickAndFindEvent


class PlaywrightClickAndFindAdapter(ClickAndFindAdapter):
    """Placeholder adapter for future ClickAndFind browser/API acquisition."""

    def __init__(self, selectors_path: str = "config/selectors.yaml") -> None:
        self.selectors_path = selectors_path

    def login(self) -> None:
        raise NotImplementedError("Playwright login is not implemented yet.")

    def select_company(self, company_name: str) -> None:
        raise NotImplementedError("Company selection is not implemented yet.")

    def set_check_date(self, check_date: date) -> None:
        raise NotImplementedError("Date selection is not implemented yet.")

    def search_vehicle(self, vehicle_id: str) -> None:
        raise NotImplementedError("Vehicle search is not implemented yet.")

    def fetch_events(
        self,
        check_date: date | None = None,
        company: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[ClickAndFindEvent]:
        raise NotImplementedError("Playwright event acquisition is not implemented yet.")

    def logout(self) -> None:
        raise NotImplementedError("Playwright logout is not implemented yet.")

