"""
Adapter HTTP puro (requests) per ClickAndFind — compatibile con Streamlit Cloud.
Non richiede Playwright né un browser installato.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("CLICKANDFIND_URL", "https://www.clickandfind.it")

ENDPOINTS = {
    "vehicles_list": f"{BASE_URL}/commons/services/gestione_mezzi_t3.php",
    "parking_list":  f"{BASE_URL}/commons/services/gestione_poi_t3.php",
    "tracking":      f"{BASE_URL}/commons/services/gettracking_fast.php",
    "operations":    f"{BASE_URL}/commons/services/getoperazioni_fast.php",
    "alarms":        f"{BASE_URL}/commons/services/getallarmi.php",
    "driver_status": f"{BASE_URL}/commons/services/statoautista_fast.php",
}

OPERATION_CODES = ["03", "04", "0B", "operazioni", "pause"]

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "*/*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
}


def _date_str(d: date | str) -> str:
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    return str(d)


def _session_expired(text: str) -> bool:
    markers = ["session", "login", "expired", "scaduta", "<!DOCTYPE", "<html"]
    lower = text.lower()
    return any(m.lower() in lower for m in markers) and len(text) < 2000


class ClickAndFindHttpAdapter:
    """Autenticazione e recupero dati via requests — senza browser."""

    def __init__(self, username: str, company: str, password: str) -> None:
        self.username = username.strip()
        self.company = company.strip()
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session_data: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Login                                                                #
    # ------------------------------------------------------------------ #

    def login(self) -> bool:
        """Esegue il login su ClickAndFind e restituisce True se riuscito."""
        try:
            # 1. Prima visita per ottenere i cookie iniziali
            self.session.get(f"{BASE_URL}/", timeout=20)

            # 2. POST login
            resp = self.session.post(
                f"{BASE_URL}/index.php",
                data={
                    "username": self.username,
                    "company":  self.company,
                    "password": self.password,
                },
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=20,
                allow_redirects=True,
            )

            body = resp.text.lower()
            # Login fallito se torna alla pagina di login con errore
            if "inserire username" in body or "password errata" in body or "utente non trovato" in body:
                return False

            # 3. Accedi alla pagina principale per attivare la sessione servizi
            main_resp = self.session.get(f"{BASE_URL}/t3/main.php", timeout=20)
            if main_resp.status_code != 200:
                return False

            # 4. Valida la sessione chiamando vehicles_list
            return self._validate_session()

        except Exception as exc:
            print(f"Login error: {type(exc).__name__}: {exc}")
            return False

    def _validate_session(self) -> bool:
        try:
            resp = self.session.post(
                ENDPOINTS["vehicles_list"],
                data={"action": "list_terminals", "detail": "all"},
                timeout=20,
            )
            if _session_expired(resp.text):
                return False
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Recupero dati                                                        #
    # ------------------------------------------------------------------ #

    def get_vehicles(self) -> dict[str, Any]:
        resp = self.session.post(
            ENDPOINTS["vehicles_list"],
            data={"action": "list_terminals", "detail": "all"},
            timeout=20,
        )
        return self._parse_response(resp, "vehicles_list")

    def get_tracking(self, codtrasp: str | int, check_date: date | str) -> dict[str, Any]:
        params = {
            "codtrasp":    str(codtrasp),
            "startdate":   _date_str(check_date),
            "singolo":     "true",
            "telemetrie":  "false",
            "ora_iniziale": "00:00",
            "ora_finale":  "24:00",
            "fileOnly":    "false",
        }
        resp = self.session.get(ENDPOINTS["tracking"], params=params, timeout=30)
        return self._parse_response(resp, "tracking")

    def get_driver_status(self, codtrasp: str | int, check_date: date | str) -> dict[str, Any]:
        params = {
            "codtrasp": str(codtrasp),
            "date":     f"{_date_str(check_date)} 24:00",
        }
        resp = self.session.get(ENDPOINTS["driver_status"], params=params, timeout=30)
        return self._parse_response(resp, "driver_status")

    def get_operations(self, codtrasp: str | int, check_date: date | str, op: str) -> dict[str, Any]:
        params = {
            "codtrasp":    str(codtrasp),
            "startdate":   _date_str(check_date),
            "ora_iniziale": "00:00",
            "ora_finale":  "24:00",
            "op":          op,
            "showDirty":   "false",
        }
        resp = self.session.get(ENDPOINTS["operations"], params=params, timeout=30)
        return self._parse_response(resp, "operations")

    def get_all_operations(self, codtrasp: str | int, check_date: date | str) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for op in OPERATION_CODES:
            try:
                results[op] = self.get_operations(codtrasp, check_date, op)
            except Exception as exc:
                results[op] = {"error": str(exc), "records": []}
        return results

    def get_alarms(self, codtrasp: str | int, check_date: date | str) -> dict[str, Any]:
        params = {
            "codtrasp":    str(codtrasp),
            "startdate":   _date_str(check_date),
            "ora_iniziale": "00:00",
            "ora_finale":  "24:00",
            "op":          "allarmi2",
            "showDirty":   "false",
        }
        resp = self.session.get(ENDPOINTS["alarms"], params=params, timeout=30)
        return self._parse_response(resp, "alarms")

    def run_vehicle_check(self, codtrasp: str | int, check_date: date | str) -> dict[str, Any]:
        return {
            "tracking":      self.get_tracking(codtrasp, check_date),
            "driver_status": self.get_driver_status(codtrasp, check_date),
            "operations":    self.get_all_operations(codtrasp, check_date),
            "alarms":        self.get_alarms(codtrasp, check_date),
        }

    def close(self) -> None:
        self.session.close()

    # ------------------------------------------------------------------ #
    # Parsing                                                              #
    # ------------------------------------------------------------------ #

    def _parse_response(self, resp: requests.Response, endpoint_type: str) -> dict[str, Any]:
        text = resp.text
        content_type = resp.headers.get("content-type", "")

        if _session_expired(text):
            return {"error": "session_expired", "records": [], "text": text}

        # JSON
        if "json" in content_type or text.strip().startswith("{") or text.strip().startswith("["):
            try:
                import json
                data = json.loads(text)
                if isinstance(data, list):
                    return {"records": data, "text": text}
                if isinstance(data, dict):
                    return {**data, "text": text}
                return {"records": [], "text": text}
            except Exception:
                pass

        # XML
        try:
            root = ElementTree.fromstring(text)
            records = []
            for child in root:
                record: dict[str, Any] = {}
                for elem in child:
                    record[elem.tag] = elem.text or ""
                if child.attrib:
                    record.update(child.attrib)
                records.append(record)
            return {"records": records, "text": text, "xml_root": root.tag}
        except ElementTree.ParseError:
            pass

        return {"records": [], "text": text, "parse_error": "unrecognized_format"}
