from __future__ import annotations

from urllib.parse import parse_qs, urlparse


RELEVANT_ENDPOINT_TYPES = {
    "tracking",
    "operations",
    "alarms",
    "driver_status",
    "trip_points",
    "vehicles_list",
    "parking_list",
}


def classify_endpoint(url: str, payload: str = "") -> str:
    lowered_url = url.lower()
    lowered_payload = (payload or "").lower()
    combined = f"{lowered_url}\n{lowered_payload}"

    if "maps.googleapis.com" in lowered_url:
        return "google_maps"
    if "api-integration.cloud.ptvgroup.com" in lowered_url:
        return "ptv_location"
    if "gettracking_fast.php" in lowered_url:
        return "tracking"
    if "getoperazioni_fast.php" in lowered_url:
        return "operations"
    if "getallarmi.php" in lowered_url:
        return "alarms"
    if "statoautista_fast.php" in lowered_url:
        return "driver_status"
    if "gestione_viaggi_t3.php" in lowered_url and "listapuntivenditaviaggiofull" in combined:
        return "trip_points"
    if "gestione_mezzi_t3.php" in lowered_url and (
        "list_terminals" in combined or "lista_terminali" in combined
    ):
        return "vehicles_list"
    if "gestione_poi_t3.php" in lowered_url and "list_parcheggi" in combined:
        return "parking_list"
    if "gestione_utenti_t3.php" in lowered_url:
        return "users"
    if "gestione_poi_t3.php" in lowered_url:
        return "pois"
    return "other"


def url_without_query(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def merged_parameters(url: str, payload: str = "") -> dict[str, list[str]]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if payload:
        for key, values in parse_qs(payload, keep_blank_values=True).items():
            params.setdefault(key, []).extend(values)
    return params
