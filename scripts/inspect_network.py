from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from playwright.sync_api import Error, Page, Response, TimeoutError, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from network_classification import RELEVANT_ENDPOINT_TYPES, classify_endpoint


NETWORK_DIR = Path("outputs/network_logs")
JSON_DIR = NETWORK_DIR / "json_responses"
XML_DIR = NETWORK_DIR / "xml_responses"
TEXT_DIR = NETWORK_DIR / "text_responses"
SCREENSHOT_DIR = Path("outputs/screenshots")
SUMMARY_PATH = NETWORK_DIR / "network_summary.csv"
RELEVANT_ENDPOINTS_PATH = NETWORK_DIR / "relevant_endpoints.csv"
BINARY_CONTENT_MARKERS = (
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "font/",
    "image/",
    "video/",
    "audio/",
)


@dataclass
class NetworkRecord:
    index: int
    timestamp: str
    method: str
    url: str
    post_data_preview: str
    response_status: int | None
    content_type: str
    endpoint_type: str
    response_body_preview: str
    looks_like_json: bool
    saved_response_path: str
    error: str


class NetworkInspector:
    def __init__(self) -> None:
        self.records: list[NetworkRecord] = []
        self.counter = 0

    def attach(self, page: Page) -> None:
        page.on("response", self.capture_response)

    def capture_response(self, response: Response) -> None:
        request = response.request
        if request.resource_type not in {"xhr", "fetch"}:
            return

        self.counter += 1
        index = self.counter
        content_type = response.headers.get("content-type", "")
        post_data = request.post_data or ""
        endpoint_type = classify_endpoint(request.url, post_data)
        body = ""
        error = ""
        saved_path = ""
        looks_like_json = False

        if _is_binary_content(content_type):
            error = "binary content skipped"
        else:
            try:
                body = response.text()
                looks_like_json = _looks_like_json(content_type, body)
                saved_path = str(self._save_body(index, body, content_type))
            except Exception as exc:
                error = f"body unavailable: {type(exc).__name__}: {exc}"

        record = NetworkRecord(
            index=index,
            timestamp=datetime.now(timezone.utc).isoformat(),
            method=request.method,
            url=request.url,
            post_data_preview=_preview(post_data),
            response_status=response.status,
            content_type=content_type,
            endpoint_type=endpoint_type,
            response_body_preview=_preview(body),
            looks_like_json=looks_like_json,
            saved_response_path=saved_path,
            error=error,
        )
        self.records.append(record)
        print(f"[network] {record.index} {record.method} {record.response_status} {record.url}")

    def write_summary(self) -> None:
        NETWORK_DIR.mkdir(parents=True, exist_ok=True)
        fieldnames = list(NetworkRecord.__dataclass_fields__)
        with SUMMARY_PATH.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.records:
                writer.writerow(asdict(record))
        self.write_relevant_endpoints()

    def write_relevant_endpoints(self) -> None:
        relevant = [record for record in self.records if record.endpoint_type in RELEVANT_ENDPOINT_TYPES]
        fieldnames = list(NetworkRecord.__dataclass_fields__)
        with RELEVANT_ENDPOINTS_PATH.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in relevant:
                writer.writerow(asdict(record))

    @staticmethod
    def _save_body(index: int, body: str, content_type: str) -> Path:
        filename = f"response_{index:03d}"
        if _looks_like_json(content_type, body):
            path = JSON_DIR / f"{filename}.json"
            try:
                parsed = json.loads(body)
                path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
            except json.JSONDecodeError:
                path.write_text(body, encoding="utf-8")
            return path

        if _looks_like_xml(content_type, body):
            path = XML_DIR / f"{filename}.xml"
            path.write_text(body, encoding="utf-8")
            return path

        path = TEXT_DIR / f"{filename}.txt"
        path.write_text(_preview(body, limit=10_000), encoding="utf-8")
        return path


def main() -> None:
    load_dotenv()
    _ensure_output_dirs()

    url = _required_env("CLICKANDFIND_URL")
    username = os.getenv("CLICKANDFIND_USERNAME", "")
    password = os.getenv("CLICKANDFIND_PASSWORD", "")
    company = os.getenv("CLICKANDFIND_COMPANY", "")
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    selectors = _load_selectors("config/selectors.yaml")
    inspector = NetworkInspector()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        inspector.attach(page)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            _screenshot(page, SCREENSHOT_DIR / "network_inspection_start.png")
            login_done = _attempt_login(page, selectors, username, password)
            if login_done and company:
                print(f"Login submitted. Company from environment is configured: {company}")
            elif not login_done:
                print("Automatic login was not completed. Continue manually in the browser.")

            print(
                "Navigate manually inside ClickAndFind: select company, search a vehicle, "
                "open Carichi e Scarichi, Operazioni, and Allarmi. Press ENTER here when finished."
            )
            input()
        except KeyboardInterrupt:
            print("Interrupted by user. Saving captured network traffic.")
        except Error as exc:
            print(f"Playwright error: {type(exc).__name__}: {exc}")
        finally:
            try:
                _screenshot(page, SCREENSHOT_DIR / "network_inspection_end.png")
            except Error:
                print("Could not capture final screenshot; browser page may already be closed.")
            inspector.write_summary()
            print(f"Captured {len(inspector.records)} XHR/fetch responses.")
            print(f"Network summary: {SUMMARY_PATH}")
            print(f"Relevant endpoints: {RELEVANT_ENDPOINTS_PATH}")
            try:
                context.close()
            except Error:
                pass
            try:
                browser.close()
            except Error:
                pass


def _attempt_login(page: Page, selectors: dict[str, Any], username: str, password: str) -> bool:
    login = selectors.get("login", {})
    username_selector = _selector_value(login.get("username"))
    password_selector = _selector_value(login.get("password"))
    submit_selector = _selector_value(login.get("submit"))

    if not username_selector or not password_selector or not submit_selector:
        return False
    if not username or not password:
        print("Username or password is missing from .env; manual login required.")
        return False

    try:
        page.locator(username_selector).fill(username, timeout=10_000)
        page.locator(password_selector).fill(password, timeout=10_000)
        page.locator(submit_selector).click(timeout=10_000)
        page.wait_for_load_state("networkidle", timeout=20_000)
        print("Automatic login submitted using configured selectors.")
        return True
    except TimeoutError:
        print("Automatic login selectors timed out; manual login required.")
    except Error as exc:
        print(f"Automatic login failed: {type(exc).__name__}. Manual login required.")
    return False


def _load_selectors(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


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


def _ensure_output_dirs() -> None:
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    XML_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for path in [SUMMARY_PATH, RELEVANT_ENDPOINTS_PATH]:
        if path.exists():
            path.unlink()
    for directory in [JSON_DIR, XML_DIR, TEXT_DIR]:
        for path in directory.glob("response_*.*"):
            path.unlink()


def _screenshot(page: Page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)
    print(f"Screenshot saved: {path}")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _is_binary_content(content_type: str) -> bool:
    lowered = content_type.lower()
    return any(marker in lowered for marker in BINARY_CONTENT_MARKERS)


def _looks_like_json(content_type: str, body: str) -> bool:
    stripped = body.lstrip()
    return "json" in content_type.lower() or stripped.startswith("{") or stripped.startswith("[")


def _looks_like_xml(content_type: str, body: str) -> bool:
    stripped = body.lstrip()
    lowered = content_type.lower()
    return "xml" in lowered or stripped.startswith("<?xml")


def _preview(value: str, limit: int = 2000) -> str:
    if not value:
        return ""
    normalized = value.replace("\r", " ").replace("\n", " ")
    return normalized[:limit]


if __name__ == "__main__":
    main()
