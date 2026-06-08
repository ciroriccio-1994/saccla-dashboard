from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


AUTOMATIC_PATH = Path("outputs/login_diagnostics/automatic_login_network.csv")
MANUAL_PATH = Path("outputs/login_diagnostics/manual_login_network.csv")
INITIALIZER_HINTS = (
    "session",
    "gestione_utenti",
    "gestione_mezzi",
    "list_terminals",
    "lista_terminali",
    "get_parametri_sessione",
    "funzioni_utente",
    "visibility",
    "user_filters",
)


def main() -> None:
    automatic = read_capture(AUTOMATIC_PATH)
    manual = read_capture(MANUAL_PATH)

    automatic_requests = request_keys(automatic)
    manual_requests = request_keys(manual)
    only_manual = sorted(manual_requests - automatic_requests)
    only_automatic = sorted(automatic_requests - manual_requests)

    print("Requests present only in manual login:")
    print_requests(only_manual)
    print()

    print("Requests present only in automatic login:")
    print_requests(only_automatic)
    print()

    print("Endpoint URLs that may initialize the service session:")
    candidates = sorted(
        {
            url
            for method, url in only_manual
            if any(hint in url.lower() for hint in INITIALIZER_HINTS)
        }
    )
    if candidates:
        for url in candidates:
            print(f"- {url}")
    else:
        print("- No obvious initializer found; inspect all manual-only requests above.")
    print()

    print(f"Cookies after automatic login: {metadata(automatic, 'cookie_names')}")
    print(f"Cookies after manual login: {metadata(manual, 'cookie_names')}")
    print(f"Page URL after automatic login: {metadata(automatic, 'page_url')}")
    print(f"Page URL after manual login: {metadata(manual, 'page_url')}")


def read_capture(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing {path}")
    return pd.read_csv(path).fillna("")


def request_keys(df: pd.DataFrame) -> set[tuple[str, str]]:
    return {
        (str(row.method).upper(), without_query(str(row.url)))
        for row in df.itertuples(index=False)
        if str(row.url)
    }


def without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def print_requests(requests: list[tuple[str, str]]) -> None:
    if not requests:
        print("- None")
        return
    for method, url in requests:
        print(f"- {method} {url}")


def metadata(df: pd.DataFrame, column: str) -> str:
    values = [str(value) for value in df.get(column, []) if str(value)]
    return values[-1] if values else ""


if __name__ == "__main__":
    main()
