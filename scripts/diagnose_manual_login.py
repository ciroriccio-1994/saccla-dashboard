from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Error, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.clickandfind_internal_api import LoginNetworkRecorder


OUTPUT_PATH = Path("outputs/login_diagnostics/manual_login_network.csv")


def main() -> None:
    load_dotenv()
    url = os.getenv("CLICKANDFIND_URL")
    if not url:
        raise SystemExit("CLICKANDFIND_URL is missing from .env")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        recorder = LoginNetworkRecorder()
        recorder.attach(page)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            print("Log in manually and interact with ClickAndFind until the application is ready.")
            print("Open the vehicle list if that normally initializes services, then press ENTER here.")
            input()
        except KeyboardInterrupt:
            print("Interrupted. Saving captured manual-login traffic.")
        finally:
            try:
                recorder.save(OUTPUT_PATH, page, context)
                print(f"Saved manual login diagnostics: {OUTPUT_PATH}")
            except Error as exc:
                print(f"Could not save manual login diagnostics: {type(exc).__name__}: {exc}")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
