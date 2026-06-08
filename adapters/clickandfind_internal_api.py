from __future__ import annotations

import json
import os
import re
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import yaml
from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Error, Page, TimeoutError, sync_playwright


RAW_RESPONSE_DIR = Path("outputs/raw_api_responses")
RELEVANT_ENDPOINTS_PATH = Path("outputs/network_logs/relevant_endpoints.csv")
INTERNAL_ENDPOINTS_PATH = Path("config/internal_endpoints.yaml")
SCREENSHOT_DIR = Path("outputs/screenshots")
LOGIN_HTML_PATH = Path("outputs/login_page.html")
LOGIN_DIAGNOSTICS_DIR = Path("outputs/login_diagnostics")
AUTOMATIC_LOGIN_NETWORK_PATH = LOGIN_DIAGNOSTICS_DIR / "automatic_login_network.csv"

USERNAME_SELECTORS = [
    'input[name="username"]',
    'input[name="user"]',
    'input[id*="user" i]',
    'input[name*="user" i]',
    'input[placeholder*="user" i]',
]
COMPANY_SELECTORS = [
    'input[name="company"]',
    'input[name="azienda"]',
    'input[id*="company" i]',
    'input[id*="azienda" i]',
    'input[name*="company" i]',
    'input[name*="azienda" i]',
    'input[placeholder*="company" i]',
    'input[placeholder*="azienda" i]',
]
PASSWORD_SELECTORS = [
    'input[type="password"]',
    'input[name="password"]',
    'input[id*="pass" i]',
    'input[name*="pass" i]',
]
LOGIN_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'text="Login"',
    'text="Accedi"',
    'text="Entra"',
]


class LoginNetworkRecorder:
    FIELDNAMES = [
        "timestamp",
        "method",
        "url",
        "resource_type",
        "status",
        "content_type",
        "page_url",
        "cookie_names",
    ]

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def attach(self, page: Page) -> None:
        page.on("response", self._on_response)

    def clear(self) -> None:
        self.records.clear()

    def _on_response(self, response: Any) -> None:
        request = response.request
        if request.resource_type not in {"xhr", "fetch"}:
            return
        self.records.append(
            {
                "timestamp": datetime.now().isoformat(),
                "method": request.method,
                "url": request.url,
                "resource_type": request.resource_type,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
        )

    def save(self, path: str | Path, page: Page, context: BrowserContext) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cookie_names = ",".join(sorted(cookie.get("name", "") for cookie in context.cookies()))
        rows = self.records or [
            {
                "timestamp": datetime.now().isoformat(),
                "method": "",
                "url": "",
                "resource_type": "",
                "status": "",
                "content_type": "",
            }
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "page_url": page.url, "cookie_names": cookie_names})


class ClickAndFindInternalApiAdapter:
    """Authenticated internal-endpoint client using Playwright only for session acquisition."""

    OPERATION_CODES = ["03", "04", "0B", "pause", "operazioni"]

    def __init__(
        self,
        selectors_path: str | Path = "config/selectors.yaml",
        raw_response_dir: str | Path = RAW_RESPONSE_DIR,
        headless: bool | None = None,
        timeout_ms: int = 30_000,
        username: str | None = None,
        company: str | None = None,
        password: str | None = None,
        login_mode: str | None = None,
        base_url: str | None = None,
        allow_manual_fallback: bool = True,
        diagnostics_enabled: bool = True,
    ) -> None:
        load_dotenv()
        self.base_url = (base_url or os.getenv("CLICKANDFIND_URL") or "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("Missing required ClickAndFind URL.")
        self.username = username if username is not None else os.getenv("CLICKANDFIND_USERNAME", "")
        self.password = password if password is not None else os.getenv("CLICKANDFIND_PASSWORD", "")
        self.company = company if company is not None else os.getenv("CLICKANDFIND_COMPANY", "")
        self.login_mode = (login_mode or os.getenv("LOGIN_MODE", "human_like")).strip().lower()
        if self.login_mode not in {"auto", "human_like", "manual"}:
            raise ValueError("LOGIN_MODE must be one of: auto, human_like, manual")
        self.headless = headless if headless is not None else os.getenv("HEADLESS", "false").lower() == "true"
        self.timeout_ms = timeout_ms
        self.allow_manual_fallback = allow_manual_fallback
        self.diagnostics_enabled = diagnostics_enabled
        self.selectors = _load_selectors(selectors_path)
        self.endpoint_urls = _load_endpoint_urls(INTERNAL_ENDPOINTS_PATH)
        self.raw_response_dir = Path(raw_response_dir)
        self.raw_response_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.service_session_activation = "not_attempted"
        self.login_mode_used = self.login_mode
        self.manual_fallback_required = False
        self.login_network_recorder = LoginNetworkRecorder()

    def login(self) -> bool:
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.login_network_recorder.attach(self.page)
        self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=60_000)
        if self.diagnostics_enabled:
            self._save_login_diagnostics()

        login_completed = False
        if self.login_mode == "manual":
            self._manual_login()
            login_completed = True
        elif self.login_mode == "human_like":
            login_completed = self._attempt_human_like_login()
        else:
            login_completed = self._attempt_automated_login()

        if not login_completed:
            if not self.allow_manual_fallback:
                print("Automatic login was not completed.")
                return False
            self.manual_fallback_required = True
            print("Automatic login was not completed. Log in manually in the browser.")
            print("After login, select the company if needed, then press ENTER here to continue.")
            input()

        if self.diagnostics_enabled:
            self._capture_automatic_login_network()
        self._print_session_diagnostics()
        return self.activate_service_session()

    def _manual_login(self) -> None:
        self.manual_fallback_required = True
        print("Manual login mode is active. Enter credentials in the browser.")
        print("After reaching the ClickAndFind application, press ENTER here to continue.")
        input()

    def _capture_automatic_login_network(self) -> None:
        self._require_page()
        self.login_network_recorder.clear()
        print("Capturing post-login XHR/fetch traffic for 5 seconds...")
        self.page.wait_for_timeout(5_000)
        self.login_network_recorder.save(AUTOMATIC_LOGIN_NETWORK_PATH, self.page, self.context)
        print(f"Saved automatic login network diagnostics: {AUTOMATIC_LOGIN_NETWORK_PATH}")

    def close(self) -> None:
        for resource in (self.context, self.browser):
            if resource is not None:
                try:
                    resource.close()
                except Error:
                    pass
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Error:
                pass

    def get_vehicles(self) -> dict[str, Any]:
        replay = self._replay_for("vehicles_list")
        response = self._post_service(
            "vehicles_list",
            self._endpoint_url("vehicles_list", replay),
            data={"action": "list_terminals", "detail": "all"},
            filename_prefix="vehicles",
        )
        return response

    def get_parking_areas(self) -> dict[str, Any]:
        replay = self._replay_for("parking_list")
        return self._post_service(
            "parking_list",
            self._endpoint_url("parking_list", replay),
            data={"action": "list_parcheggi_t3"},
            filename_prefix="parking_areas",
        )

    def get_tracking(self, codtrasp: str | int, check_date: str | date, tag: str | None = None) -> dict[str, Any]:
        params = {
            "codtrasp": str(codtrasp),
            "startdate": _date_string(check_date),
            "singolo": "true",
            "telemetrie": "false",
            "ora_iniziale": "00:00",
            "ora_finale": "24:00",
            "fileOnly": "false",
        }
        if tag:
            params["TAG"] = tag
        replay = self._replay_for("tracking")
        params = {**replay.get("params", {}), **params}
        return self._get_service(
            "tracking",
            self._endpoint_url("tracking", replay),
            params=params,
            filename_prefix=f"tracking_codtrasp_{codtrasp}_{_date_string(check_date)}",
        )

    def get_driver_status(self, codtrasp: str | int, check_date: str | date) -> dict[str, Any]:
        replay = self._replay_for("driver_status")
        params = {
            **replay.get("params", {}),
            "codtrasp": str(codtrasp),
            "date": f"{_date_string(check_date)} 24:00",
        }
        return self._get_service(
            "driver_status",
            self._endpoint_url("driver_status", replay),
            params=params,
            filename_prefix=f"driver_status_codtrasp_{codtrasp}_{_date_string(check_date)}",
        )

    def get_operations(self, codtrasp: str | int, check_date: str | date, op: str) -> dict[str, Any]:
        replay = self._replay_for("operations")
        params = {
                **replay.get("params", {}),
                "codtrasp": str(codtrasp),
                "startdate": _date_string(check_date),
                "ora_iniziale": "00:00",
                "ora_finale": "24:00",
                "op": op,
                "showDirty": "false",
            }
        return self._get_service(
            "operations",
            self._endpoint_url("operations", replay),
            params=params,
            filename_prefix=f"operations_codtrasp_{codtrasp}_{_date_string(check_date)}_op_{op}",
        )

    def get_all_operations(self, codtrasp: str | int, check_date: str | date) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for op in self.OPERATION_CODES:
            try:
                results[op] = self.get_operations(codtrasp, check_date, op)
            except Exception as exc:
                print(f"Operation endpoint failed for op={op}: {type(exc).__name__}: {exc}")
                results[op] = {"error": str(exc), "records": []}
        return results

    def get_alarms(self, codtrasp: str | int, check_date: str | date) -> dict[str, Any]:
        replay = self._replay_for("alarms")
        params = {
                **replay.get("params", {}),
                "codtrasp": str(codtrasp),
                "startdate": _date_string(check_date),
                "ora_iniziale": "00:00",
                "ora_finale": "24:00",
                "op": "allarmi2",
                "showDirty": "false",
            }
        return self._get_service(
            "alarms",
            self._endpoint_url("alarms", replay),
            params=params,
            filename_prefix=f"alarms_codtrasp_{codtrasp}_{_date_string(check_date)}",
        )

    def run_vehicle_check(self, codtrasp: str | int, check_date: str | date, tag: str | None = None) -> dict[str, Any]:
        return {
            "tracking": self.get_tracking(codtrasp, check_date, tag=tag),
            "driver_status": self.get_driver_status(codtrasp, check_date),
            "operations": self.get_all_operations(codtrasp, check_date),
            "alarms": self.get_alarms(codtrasp, check_date),
        }

    def validate_services_session(self) -> bool:
        replay = self._replay_for("vehicles_list")
        url = self._endpoint_url("vehicles_list", replay)
        data = {"action": "list_terminals", "detail": "all"}
        result = self._browser_fetch("vehicles_list", "POST", url, data=data)
        if _session_expired(result.get("text", "")):
            print("Authenticated page is open, but service session is not valid.")
            return False
        print("Service session is valid.")
        return True

    def activate_service_session(self) -> bool:
        self._require_page()
        print("Activating ClickAndFind service session...")
        self.page.wait_for_timeout(5_000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=20_000)
        except TimeoutError:
            pass

        try:
            app_url = f"{urlsplit(self.page.url).scheme}://{urlsplit(self.page.url).netloc}/t3/index.php"
            if "/t3/index.php" not in self.page.url:
                self.page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
            else:
                self.page.reload(wait_until="domcontentloaded", timeout=60_000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=20_000)
            except TimeoutError:
                pass
        except Error as exc:
            print(f"Authenticated page reload was skipped: {type(exc).__name__}")

        try:
            ready_state = self.page.evaluate("document.readyState")
            print(f"Application document.readyState: {ready_state}")
        except Error:
            pass
        self._click_safe_app_element()
        self._move_and_click_page_center()
        try:
            self.page.keyboard.press("Escape")
        except Error:
            pass
        self._trigger_safe_vehicle_action()
        self._prime_with_driver_status()
        self.page.wait_for_timeout(2_000)

        if self.validate_services_session():
            self.service_session_activation = "automatic"
            print("Service session activated automatically.")
            return True

        if not self.allow_manual_fallback:
            self.service_session_activation = "failed"
            print("Service session activation failed without manual fallback.")
            return False

        print("Please click inside the ClickAndFind web app or open the vehicle list manually, then press ENTER.")
        self.manual_fallback_required = True
        input()
        self.page.wait_for_timeout(1_000)
        if self.validate_services_session():
            self.service_session_activation = "manual"
            print("Service session activated manually.")
            return True

        self.service_session_activation = "failed"
        print("Service session activation failed.")
        return False

    def _move_and_click_page_center(self) -> None:
        if not self.page:
            return
        try:
            viewport = self.page.viewport_size or {"width": 1280, "height": 720}
            x = max(int(viewport["width"] / 2), 1)
            y = max(int(viewport["height"] / 2), 1)
            self.page.mouse.move(x - 20, y - 20, steps=5)
            self.page.mouse.move(x, y, steps=5)
            self.page.mouse.click(x, y)
            print("Moved mouse and clicked the center of the application page.")
        except Error:
            pass

    def _click_safe_app_element(self) -> None:
        if not self.page:
            return
        selectors = [
            _selector_value(self.selectors.get("application", {}).get("container")),
            "main",
            '[role="main"]',
            "body",
        ]
        for selector in selectors:
            if not selector:
                continue
            try:
                locator = self.page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=1_000):
                    locator.click(position={"x": 5, "y": 5}, timeout=3_000)
                    print(f"Clicked safe application element: {selector}")
                    return
            except Error:
                continue

    def _trigger_safe_vehicle_action(self) -> None:
        if not self.page:
            return
        configured = [
            _selector_value(self.selectors.get("navigation", {}).get("vehicles")),
            _selector_value(self.selectors.get("vehicle_list", {}).get("open")),
        ]
        for selector in configured:
            if not selector:
                continue
            try:
                locator = self.page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=1_000):
                    locator.click(timeout=3_000)
                    print(f"Triggered configured vehicle-list action: {selector}")
                    return
            except Error:
                continue

    def _prime_with_driver_status(self) -> None:
        replay = self._replay_for("driver_status")
        url = self._endpoint_url("driver_status", replay)
        params = replay.get("params", {})
        if not params.get("codtrasp") or not params.get("date"):
            return
        try:
            result = self._browser_fetch("driver_status", "GET", url, params=params)
            if not _session_expired(result.get("text", "")):
                print("Driver-status service responded during session activation.")
        except Error as exc:
            print(f"Driver-status activation probe failed: {type(exc).__name__}")

    def _attempt_automated_login(self) -> bool:
        if not self.page:
            return False
        login = self.selectors.get("login", {})
        username_selectors = _selector_candidates(login.get("username"), USERNAME_SELECTORS)
        company_selectors = _selector_candidates(login.get("company"), COMPANY_SELECTORS)
        password_selectors = _selector_candidates(login.get("password"), PASSWORD_SELECTORS)
        submit_selectors = _selector_candidates(login.get("submit"), LOGIN_SELECTORS)
        if not self.username or not self.password:
            print("Username or password is missing from .env; manual login required.")
            return False
        try:
            username_filled = self._fill_first_visible(username_selectors, self.username, "username")
            company_filled = True
            if self.company:
                company_filled = self._fill_first_visible(company_selectors, self.company, "company", required=False)
            password_filled = self._fill_first_visible(password_selectors, self.password, "password")

            if not username_filled or not password_filled:
                print("Automatic login could not find required username/password fields.")
                return False

            if self._click_login(submit_selectors):
                self._wait_after_login()
                if self._is_authenticated():
                    print("Automatic login completed and authenticated session verified.")
                    return True
                print("Automatic login submitted, but authenticated session was not verified.")
            else:
                print("Automatic login could not find a login button.")
            if self.company and not company_filled:
                print("Company field was not found during automatic login.")
        except TimeoutError:
            print("Automatic login selectors timed out; manual login required.")
        except Error as exc:
            print(f"Automatic login failed: {type(exc).__name__}. Manual login required.")
        return False

    def _attempt_human_like_login(self) -> bool:
        if not self.page:
            return False
        if not self.username or not self.password:
            print("Username or password is missing from .env; manual login required.")
            return False

        try:
            self.page.wait_for_load_state("networkidle", timeout=20_000)
        except TimeoutError:
            pass

        username_locator = self.page.locator('input[name="username"]')
        company_locator = self.page.locator('input[name="company"]')
        password_locator = self.page.locator('input[name="password"]')
        submit_locator = self.page.locator("input#login_button")

        if not self._type_exact_login_field(username_locator, self.username, "username"):
            return False
        if not self._type_exact_login_field(company_locator, self.company, "company"):
            return False

        try:
            company_locator.press("Tab")
        except Error:
            try:
                company_locator.evaluate("element => element.blur()")
            except Error:
                pass

        if not self._type_exact_login_field(password_locator, self.password, "password"):
            return False

        username_value = username_locator.input_value()
        company_value = company_locator.input_value()
        password_value = password_locator.input_value()
        validation_errors = []
        if username_value != self.username:
            validation_errors.append("username")
        if company_value != self.company:
            validation_errors.append("company")
        if len(password_value) != len(self.password):
            validation_errors.append("password length")
        if validation_errors:
            print(f"Human-like login validation failed: {', '.join(validation_errors)}")
            return False

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(
                path=str(SCREENSHOT_DIR / "login_filled_before_submit.png"),
                full_page=True,
            )
            print(f"Saved filled-login screenshot: {SCREENSHOT_DIR / 'login_filled_before_submit.png'}")
        except Error as exc:
            print(f"Could not save filled-login screenshot: {type(exc).__name__}")

        login = self.selectors.get("login", {})
        remember_selector = _selector_value(login.get("remember"))
        if remember_selector:
            try:
                checkbox = self.page.locator(remember_selector).first
                if checkbox.count() and checkbox.is_visible(timeout=1_000) and not checkbox.is_checked():
                    checkbox.click(timeout=3_000)
                    print("Clicked configured remember checkbox.")
            except Error:
                pass

        previous_url = self.page.url
        try:
            submit_locator.wait_for(state="visible", timeout=10_000)
            submit_locator.click(timeout=5_000)
            print("Submitted human-like login using input#login_button.")
        except Error as exc:
            print(f"Human-like login submit failed: {type(exc).__name__}")
            return False

        try:
            self.page.wait_for_url(re.compile(r"/t3/index\.php"), timeout=30_000)
        except TimeoutError:
            try:
                self.page.wait_for_url(lambda url: url != previous_url, timeout=10_000)
            except TimeoutError:
                pass
        try:
            self.page.wait_for_load_state("networkidle", timeout=30_000)
        except TimeoutError:
            pass
        self.page.wait_for_timeout(3_000)
        if "/t3/index.php" in self.page.url or self._is_authenticated():
            print("Human-like login completed.")
            return True
        return False

    def _type_exact_login_field(self, locator: Any, value: str, label: str) -> bool:
        if not self.page:
            return False
        try:
            locator.wait_for(state="visible", timeout=10_000)
            locator.click(timeout=5_000)
            self._print_active_element(f"before typing {label}")
            active = self._active_element()
            if active.get("name") != label:
                print(
                    f"Focus validation failed for {label}: "
                    f"active name={active.get('name', '')} id={active.get('id', '')}"
                )
                return False
            try:
                locator.press("Meta+A")
            except Error:
                locator.press("Control+A")
            locator.fill("")
            locator.type(value, delay=50)
            self._print_active_element(f"after typing {label}")
            actual_value = locator.input_value()
            if label == "password":
                print(f"Password length read back: {len(actual_value)}")
            else:
                print(f"{label.capitalize()} value read back: {actual_value}")
            return True
        except Error as exc:
            print(f"Could not type {label}: {type(exc).__name__}")
            return False

    def _print_active_element(self, stage: str) -> None:
        if not self.page:
            return
        try:
            active = self.page.evaluate(
                """
                () => ({
                    name: document.activeElement?.getAttribute('name') || '',
                    id: document.activeElement?.id || ''
                })
                """
            )
            print(
                f"Active element {stage}: "
                f"name={active.get('name', '')} id={active.get('id', '')}"
            )
        except Error:
            print(f"Active element {stage}: unavailable")

    def _active_element(self) -> dict[str, str]:
        if not self.page:
            return {"name": "", "id": ""}
        try:
            return self.page.evaluate(
                """
                () => ({
                    name: document.activeElement?.getAttribute('name') || '',
                    id: document.activeElement?.id || ''
                })
                """
            )
        except Error:
            return {"name": "", "id": ""}

    def _type_first_visible(
        self,
        selectors: list[str],
        value: str,
        label: str,
        required: bool = True,
    ) -> bool:
        locator = self._first_visible_locator(selectors)
        if locator:
            try:
                locator.click(timeout=3_000)
                locator.fill("")
                locator.type(value, delay=50)
                print(f"Typed {label} slowly.")
                return True
            except Error:
                pass
        if label == "username":
            return self._type_by_label(["user", "username", "utente", "login"], value, label)
        if label == "company":
            return self._type_by_label(["company", "azienda", "societa", "società"], value, label) or not required
        return False

    def _type_by_label(self, terms: list[str], value: str, label: str) -> bool:
        if not self.page:
            return False
        for term in terms:
            try:
                locator = self.page.get_by_label(re.compile(term, re.IGNORECASE)).first
                if locator.count() and locator.is_visible(timeout=1_000):
                    locator.click(timeout=3_000)
                    locator.fill("")
                    locator.type(value, delay=50)
                    print(f"Typed {label} slowly using label match: {term}")
                    return True
            except Error:
                continue
        return False

    def _first_visible_locator(self, selectors: list[str]) -> Any | None:
        if not self.page:
            return None
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=1_000):
                    return locator
            except Error:
                continue
        return None

    def _fill_first_visible(
        self,
        selectors: list[str],
        value: str,
        label: str,
        required: bool = True,
    ) -> bool:
        if not self.page or not value:
            return False
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                if not locator.is_visible(timeout=1_000):
                    continue
                locator.fill(value, timeout=5_000)
                print(f"Filled {label} using selector: {selector}")
                return True
            except Error:
                continue

        if label == "username":
            return self._fill_by_label(["user", "username", "utente", "login"], value, label)
        if label == "company":
            return self._fill_by_label(["company", "azienda", "societa", "società"], value, label) or not required
        return False

    def _fill_by_label(self, label_terms: list[str], value: str, label: str) -> bool:
        if not self.page:
            return False
        for term in label_terms:
            try:
                locator = self.page.get_by_label(re.compile(term, re.IGNORECASE)).first
                if locator.count() == 0:
                    continue
                if not locator.is_visible(timeout=1_000):
                    continue
                locator.fill(value, timeout=5_000)
                print(f"Filled {label} using label match: {term}")
                return True
            except Error:
                continue
        return False

    def _click_login(self, selectors: list[str]) -> bool:
        if not self.page:
            return False
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                if not locator.is_visible(timeout=1_000):
                    continue
                locator.click(timeout=5_000)
                print(f"Clicked login using selector: {selector}")
                return True
            except Error:
                continue

        for term in ["login", "accedi", "entra"]:
            try:
                button = self.page.get_by_role("button", name=re.compile(term, re.IGNORECASE)).first
                if button.count() == 0:
                    continue
                if not button.is_visible(timeout=1_000):
                    continue
                button.click(timeout=5_000)
                print(f"Clicked login using button role: {term}")
                return True
            except Error:
                continue
        return False

    def _wait_after_login(self) -> None:
        if not self.page:
            return
        try:
            self.page.wait_for_load_state("networkidle", timeout=20_000)
        except TimeoutError:
            pass
        try:
            self.page.wait_for_timeout(2_000)
        except Error:
            pass

    def _is_authenticated(self) -> bool:
        if not self.context or not self.page:
            return False
        if self.page.url.rstrip("/") != self.base_url.rstrip("/"):
            return True
        try:
            replay = self._replay_for("vehicles_list")
            probe_url = replay.get("url") or self.endpoint_urls.get("vehicles_list", "")
            if not probe_url:
                return False
            result = self._browser_fetch(
                "vehicles_list",
                "POST",
                probe_url,
                data={"action": "list_terminals", "detail": "all"},
            )
            text = result.get("text", "")
            if result.get("status") == 200 and text.strip() and not _looks_like_login_page(text):
                return True
        except Error:
            pass
        return False

    def _save_login_diagnostics(self) -> None:
        if not self.page:
            return
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        LOGIN_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(SCREENSHOT_DIR / "login_page.png"), full_page=True)
            print(f"Saved login screenshot: {SCREENSHOT_DIR / 'login_page.png'}")
        except Error as exc:
            print(f"Could not save login screenshot: {type(exc).__name__}")
        try:
            LOGIN_HTML_PATH.write_text(self.page.content(), encoding="utf-8")
            print(f"Saved login HTML: {LOGIN_HTML_PATH}")
        except Error as exc:
            print(f"Could not save login HTML: {type(exc).__name__}")
        self.print_visible_input_fields()

    def print_visible_input_fields(self) -> None:
        if not self.page:
            return
        try:
            fields = self.page.locator("input, textarea, select").evaluate_all(
                """
                elements => elements.map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    value: ['password', 'hidden'].includes((el.getAttribute('type') || '').toLowerCase())
                        ? ''
                        : (el.value || ''),
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                }))
                """
            )
        except Error as exc:
            print(f"Could not inspect input fields: {type(exc).__name__}")
            return

        print("Visible input fields before login:")
        if not fields:
            print("- none found")
            return
        for field in fields:
            print(
                "- "
                f"tag={field.get('tag', '')} | "
                f"type={field.get('type', '')} | "
                f"name={field.get('name', '')} | "
                f"id={field.get('id', '')} | "
                f"placeholder={field.get('placeholder', '')} | "
                f"aria-label={field.get('ariaLabel', '')} | "
                f"value={field.get('value', '')} | "
                f"visible={field.get('visible', False)}"
            )

    def _get_service(
        self,
        endpoint_type: str,
        endpoint_url: str,
        params: dict[str, str],
        filename_prefix: str,
    ) -> dict[str, Any]:
        result = self._fetch_with_session_retry(endpoint_type, "GET", endpoint_url, params=params)
        return self._handle_response(result, filename_prefix, "GET", endpoint_url, params, {})

    def _post_service(
        self,
        endpoint_type: str,
        endpoint_url: str,
        data: dict[str, str],
        filename_prefix: str,
    ) -> dict[str, Any]:
        result = self._fetch_with_session_retry(endpoint_type, "POST", endpoint_url, data=data)
        return self._handle_response(result, filename_prefix, "POST", endpoint_url, {}, data)

    def _fetch_with_session_retry(
        self,
        endpoint_type: str,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        result = self._browser_fetch(endpoint_type, method, url, params=params, data=data)
        if not _session_expired(result.get("text", "")):
            return result
        print("Authenticated page is open, but service session is not valid.")
        if not self.allow_manual_fallback:
            raise RuntimeError("ClickAndFind service session expired.")
        print("Please click inside the ClickAndFind web app or open the vehicle list manually, then press ENTER.")
        input()
        retried = self._browser_fetch(endpoint_type, method, url, params=params, data=data)
        if not _session_expired(retried.get("text", "")):
            self.service_session_activation = "manual"
        return retried

    def _browser_fetch(
        self,
        endpoint_type: str,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._require_page()
        method = method.upper()
        params = params or {}
        data = data or {}
        final_url = f"{url}?{urlencode(params)}" if method == "GET" and params else url
        body = urlencode(data) if method == "POST" else None
        self._log_request(method, final_url, params=params, data=data)
        result = self.page.evaluate(
            """
            async ({url, method, body}) => {
                const headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                };
                const response = await fetch(url, {
                    method,
                    headers,
                    credentials: "include",
                    body: method === "POST" ? body : null
                });
                const text = await response.text();
                return {
                    status: response.status,
                    content_type: response.headers.get("content-type") || "",
                    text,
                    final_url: response.url,
                    response_size: new TextEncoder().encode(text).length
                };
            }
            """,
            {"url": final_url, "method": method, "body": body},
        )
        result["endpoint_type"] = endpoint_type
        self._log_response(
            int(result.get("status", 0)),
            str(result.get("content_type", "")),
            str(result.get("text", "")),
            detect_response_type(str(result.get("text", "")), str(result.get("content_type", ""))),
        )
        return result

    def _handle_response(
        self,
        response: dict[str, Any],
        filename_prefix: str,
        method: str,
        url: str,
        params: dict[str, str],
        data: dict[str, str],
    ) -> dict[str, Any]:
        status = int(response.get("status", 0))
        content_type = str(response.get("content_type", ""))
        text = str(response.get("text", ""))
        final_url = str(response.get("final_url", url))
        response_type = detect_response_type(text, content_type)
        raw_path = self._save_raw_response(filename_prefix, text, content_type)
        parsed: Any = None
        parse_error = ""
        parsed_result = parse_response_body(text, content_type)
        parsed = parsed_result.get("parsed")
        parse_error = parsed_result.get("parse_error", "")
        endpoint_type = str(response.get("endpoint_type", ""))
        operation_code = params.get("op", "") if endpoint_type == "operations" else ""
        records, node_type = extract_endpoint_records(parsed, endpoint_type, operation_code)
        if parse_error:
            print(f"Parse failed for {filename_prefix}; raw response saved to {raw_path}")

        return {
            "method": method,
            "url": final_url,
            "params": params,
            "data": data,
            "status": status,
            "content_type": content_type,
            "response_type": response_type,
            "response_size": int(response.get("response_size", len(text.encode("utf-8")))),
            "raw_path": str(raw_path),
            "raw_text": text,
            "parsed": parsed,
            "parse_error": parse_error,
            "record_node_type": node_type,
            "records": records,
        }

    def _save_raw_response(self, filename_prefix: str, text: str, content_type: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = response_suffix(content_type, text)
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename_prefix).strip("_")
        path = self.raw_response_dir / f"{safe_prefix}_{timestamp}.{suffix}"
        path.write_text(text, encoding="utf-8")
        return path

    def _require_context(self) -> None:
        if self.context is None:
            raise RuntimeError("Adapter is not logged in. Call login() first.")

    def _require_page(self) -> None:
        if self.page is None or self.page.is_closed():
            raise RuntimeError("Authenticated browser page is not available. Call login() first.")

    def _print_session_diagnostics(self) -> None:
        self._require_page()
        print(f"Current page URL: {self.page.url}")
        cookies = self.context.cookies("https://www.clickandfind.it") if self.context else []
        print(f"Cookies for www.clickandfind.it: {len(cookies)}")
        print(f"Cookie names: {[cookie.get('name', '') for cookie in cookies]}")
        storage = self.page.evaluate(
            """
            () => ({
                localStorageKeys: Object.keys(localStorage),
                sessionStorageKeys: Object.keys(sessionStorage)
            })
            """
        )
        print(f"localStorage keys: {storage.get('localStorageKeys', [])}")
        print(f"sessionStorage keys: {storage.get('sessionStorageKeys', [])}")

    def _endpoint_url(self, endpoint_type: str, replay: dict[str, Any]) -> str:
        discovered_url = replay.get("url", "")
        if discovered_url:
            return discovered_url
        configured_url = self.endpoint_urls.get(endpoint_type, "")
        if configured_url:
            return configured_url
        raise RuntimeError(
            f"Missing URL for endpoint type '{endpoint_type}'. "
            f"Run scripts/extract_internal_endpoints.py or update {INTERNAL_ENDPOINTS_PATH}."
        )

    def _replay_for(self, endpoint_type: str) -> dict[str, Any]:
        if not RELEVANT_ENDPOINTS_PATH.exists():
            return {}
        try:
            import csv

            with RELEVANT_ENDPOINTS_PATH.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row.get("endpoint_type") != endpoint_type:
                        continue
                    method = row.get("method", "").upper()
                    url = row.get("url", "")
                    post_data = row.get("post_data_preview", "")
                    return {
                        "method": method,
                        "url": _url_without_query(url),
                        "params": _query_params(url),
                        "data": _flat_params(post_data),
                    }
        except Exception as exc:
            print(f"Could not read endpoint replay data: {type(exc).__name__}: {exc}")
        return {}

    @staticmethod
    def _log_request(method: str, url: str, params: dict[str, str], data: dict[str, str]) -> None:
        print(f"[api request] method={method} url={url}")
        print(f"[api request] query_params={_redact_dict(params)}")
        print(f"[api request] post_data={_redact_dict(data)}")

    @staticmethod
    def _log_response(status: int, content_type: str, text: str, response_type: str) -> None:
        print(
            f"[api response] status={status} content_type={content_type} "
            f"size={len(text.encode('utf-8'))} type={response_type}"
        )
        print(f"[api response] preview={_safe_preview(text, 200)}")
        if status == 404:
            print("Endpoint URL is wrong. Check config/internal_endpoints.yaml against network logs.")


def parse_response_body(text: str, content_type: str = "") -> dict[str, Any]:
    stripped = _clean_response_text(text)
    if not stripped:
        return {"parsed": None, "parse_error": "", "response_type": "empty"}

    response_type = detect_response_type(stripped, content_type)
    if response_type == "json":
        try:
            return {"parsed": json.loads(stripped), "parse_error": "", "response_type": response_type}
        except json.JSONDecodeError as exc:
            return _parse_error("json", exc, stripped)

    if response_type == "html":
        return {"parsed": {"html": _safe_preview(stripped, 2000)}, "parse_error": "", "response_type": response_type}

    if response_type == "xml":
        xml_text = _repair_xml_text(stripped)
        try:
            root = ElementTree.fromstring(xml_text)
            return {"parsed": {root.tag: xml_element_to_dict(root)}, "parse_error": "", "response_type": response_type}
        except ElementTree.ParseError as exc:
            recovered = _recover_xml_with_bs4(xml_text)
            if recovered is not None:
                return {"parsed": recovered, "parse_error": f"ElementTree recovered with BeautifulSoup: {exc}", "response_type": response_type}
            return _parse_error("xml", exc, stripped)

    return {"parsed": {"text": stripped}, "parse_error": "", "response_type": response_type}


def xml_element_to_dict(element: ElementTree.Element) -> dict[str, Any] | str:
    children = list(element)
    attributes = {f"@{key}": value for key, value in element.attrib.items()}
    text = (element.text or "").strip()

    if not children:
        if attributes:
            if text:
                attributes["#text"] = text
            return attributes
        return text

    result: dict[str, Any] = dict(attributes)
    for child in children:
        child_value = xml_element_to_dict(child)
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_value)
        else:
            result[child.tag] = child_value
    if text:
        result["#text"] = text
    return result


def extract_records(parsed: Any) -> list[dict[str, Any]]:
    candidates = _record_candidates(parsed)
    if not candidates:
        return []
    largest = max(candidates, key=len)
    return [flatten_record(record) for record in largest]


def extract_endpoint_records(
    parsed: Any,
    endpoint_type: str,
    operation_code: str = "",
) -> tuple[list[dict[str, Any]], str]:
    node_type = _record_node_type(endpoint_type, operation_code)
    if node_type:
        nodes = _find_named_nodes(parsed, node_type)
        if nodes:
            return [flatten_record(node) for node in nodes], node_type
    return extract_records(parsed), node_type or "generic"


def _record_node_type(endpoint_type: str, operation_code: str) -> str:
    if endpoint_type == "vehicles_list":
        return "terminal"
    if endpoint_type == "parking_list":
        return "parcheggio"
    if endpoint_type == "tracking":
        return "position"
    if endpoint_type == "alarms":
        return "allarme"
    if endpoint_type == "operations":
        return {
            "03": "carico",
            "04": "scarico",
            "pause": "pausa",
            "operazioni": "operazione",
        }.get(operation_code, "")
    return ""


def _find_named_nodes(value: Any, node_name: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == node_name:
                if isinstance(child, list):
                    found.extend(child)
                else:
                    found.append(child)
            found.extend(_find_named_nodes(child, node_name))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_named_nodes(child, node_name))
    return found


def flatten_record(record: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(record, dict):
        return {prefix or "value": record}
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        clean_key = key.lstrip("@")
        next_key = f"{prefix}_{clean_key}" if prefix else clean_key
        if isinstance(value, dict):
            flattened.update(flatten_record(value, next_key))
        elif isinstance(value, list):
            flattened[next_key] = json.dumps(value, ensure_ascii=False)
        else:
            flattened[next_key] = value
    return flattened


def response_suffix(content_type: str, text: str) -> str:
    response_type = detect_response_type(text, content_type)
    if response_type == "json":
        return "json"
    if response_type == "xml":
        return "xml"
    return "txt"


def _record_candidates(value: Any) -> list[list[dict[str, Any]]]:
    candidates: list[list[dict[str, Any]]] = []
    if isinstance(value, list):
        dict_items = [item for item in value if isinstance(item, dict)]
        if dict_items:
            candidates.append(dict_items)
        for item in value:
            candidates.extend(_record_candidates(item))
    elif isinstance(value, dict):
        for child in value.values():
            candidates.extend(_record_candidates(child))
    return candidates


def _date_string(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def detect_response_type(text: str, content_type: str = "") -> str:
    stripped = (text or "").lstrip()
    lowered = (content_type or "").lower()
    if not stripped:
        return "empty"
    if "json" in lowered or stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if "html" in lowered or re.search(r"<\s*html\b", stripped[:500], re.IGNORECASE):
        return "html"
    if "xml" in lowered or stripped.startswith("<?xml"):
        return "xml"
    if stripped.startswith("<"):
        return "xml"
    return "text"


def _clean_response_text(text: str) -> str:
    if text is None:
        return ""
    return text.strip().lstrip("\ufeff")


def _repair_xml_text(text: str) -> str:
    repaired = text.strip()
    # Escape bare ampersands while preserving valid entities.
    return re.sub(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]+;)", "&amp;", repaired)


def _recover_xml_with_bs4(text: str) -> dict[str, Any] | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    try:
        soup = BeautifulSoup(text, "xml")
        root = next((child for child in soup.contents if getattr(child, "name", None)), None)
        if root is None:
            return None
        return {root.name: _bs4_node_to_dict(root)}
    except Exception:
        try:
            soup = BeautifulSoup(text, "lxml-xml")
            root = next((child for child in soup.contents if getattr(child, "name", None)), None)
            if root is None:
                return None
            return {root.name: _bs4_node_to_dict(root)}
        except Exception:
            return None


def _bs4_node_to_dict(node: Any) -> Any:
    children = [child for child in getattr(node, "children", []) if getattr(child, "name", None)]
    attrs = {f"@{key}": value for key, value in getattr(node, "attrs", {}).items()}
    text = node.get_text(strip=True) if hasattr(node, "get_text") else ""
    if not children:
        if attrs:
            if text:
                attrs["#text"] = text
            return attrs
        return text
    result: dict[str, Any] = dict(attrs)
    for child in children:
        value = _bs4_node_to_dict(child)
        if child.name in result:
            if not isinstance(result[child.name], list):
                result[child.name] = [result[child.name]]
            result[child.name].append(value)
        else:
            result[child.name] = value
    return result


def _parse_error(response_type: str, exc: Exception, text: str) -> dict[str, Any]:
    return {
        "parsed": None,
        "parse_error": f"{response_type} parse failed: {type(exc).__name__}: {exc}; preview={_safe_preview(text, 500)}",
        "response_type": response_type,
    }


def _url_without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _query_params(url: str) -> dict[str, str]:
    return _flat_params(urlsplit(url).query)


def _flat_params(encoded: str) -> dict[str, str]:
    if not encoded:
        return {}
    params = parse_qs(encoded, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in params.items()}


def _redact_dict(values: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in values.items():
        if "pass" in str(key).lower():
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _safe_preview(text: str, limit: int = 300) -> str:
    if not text:
        return ""
    preview = text.replace("\r", " ").replace("\n", " ")[:limit]
    return re.sub(r"(?i)(password|passwd|pwd)=([^&\\s]+)", r"\1=***", preview)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _load_selectors(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_endpoint_urls(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    endpoints = config.get("endpoints", config)
    return {
        str(endpoint_type): str(value.get("url", "") if isinstance(value, dict) else value).strip()
        for endpoint_type, value in endpoints.items()
    }


def _selector_value(config: Any) -> str:
    if isinstance(config, str):
        return config.strip()
    if isinstance(config, dict):
        by = str(config.get("by", "css")).lower()
        value = str(config.get("value", "")).strip()
        if by == "xpath" and value:
            return f"xpath={value}"
        return value
    return ""


def _selector_candidates(config: Any, fallbacks: list[str]) -> list[str]:
    configured = _selector_value(config)
    candidates = [configured] if configured else []
    candidates.extend(fallbacks)
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _looks_like_login_page(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ["password", "login", "accedi", "username"])


def _session_expired(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").lower())
    return "session expired" in normalized
