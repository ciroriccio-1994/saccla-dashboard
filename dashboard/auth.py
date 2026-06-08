from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adapters.clickandfind_internal_api import ClickAndFindInternalApiAdapter


@dataclass
class AuthenticationResult:
    success: bool
    message: str
    service_session_ready: bool = False
    vehicles: list[dict[str, Any]] = field(default_factory=list)


def authenticate_clickandfind(username: str, company: str, password: str) -> AuthenticationResult:
    if not username.strip() or not company.strip() or not password:
        return AuthenticationResult(False, "Compilare username, company e password.")

    adapter = ClickAndFindInternalApiAdapter(
        username=username.strip(),
        company=company.strip(),
        password=password,
        login_mode="human_like",
        allow_manual_fallback=False,
        diagnostics_enabled=False,
    )
    try:
        if not adapter.login():
            return AuthenticationResult(
                False,
                "Accesso ClickAndFind non riuscito o sessione servizi non disponibile.",
            )
        vehicles_response = adapter.get_vehicles()
        if vehicles_response.get("parse_error"):
            return AuthenticationResult(
                False,
                f"Accesso riuscito, ma la lista mezzi non e disponibile: {vehicles_response['parse_error']}",
            )
        return AuthenticationResult(
            True,
            "Accesso ClickAndFind completato.",
            service_session_ready=True,
            vehicles=vehicles_response.get("records", []),
        )
    except Exception as exc:
        return AuthenticationResult(False, f"Accesso ClickAndFind non riuscito: {type(exc).__name__}.")
    finally:
        adapter.close()
