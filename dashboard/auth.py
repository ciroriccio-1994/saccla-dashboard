from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adapters.http_adapter import ClickAndFindHttpAdapter


@dataclass
class AuthenticationResult:
    success: bool
    message: str
    service_session_ready: bool = False
    vehicles: list[dict[str, Any]] = field(default_factory=list)


def authenticate_clickandfind(username: str, company: str, password: str) -> AuthenticationResult:
    if not username.strip() or not company.strip() or not password:
        return AuthenticationResult(False, "Compilare username, company e password.")

    adapter = ClickAndFindHttpAdapter(username=username, company=company, password=password)
    try:
        if not adapter.login():
            return AuthenticationResult(
                False,
                "Accesso ClickAndFind non riuscito. Verificare le credenziali.",
            )
        vehicles_response = adapter.get_vehicles()
        if vehicles_response.get("error"):
            return AuthenticationResult(
                False,
                f"Accesso riuscito, ma la lista mezzi non è disponibile: {vehicles_response['error']}",
            )
        return AuthenticationResult(
            True,
            "Accesso ClickAndFind completato.",
            service_session_ready=True,
            vehicles=vehicles_response.get("records", []),
        )
    except Exception as exc:
        return AuthenticationResult(False, f"Errore di connessione: {type(exc).__name__}.")
    finally:
        adapter.close()
