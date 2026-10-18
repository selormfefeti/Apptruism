"""
Open the hosted app in a headless browser and wait for the ranking to
render, the way a visitor would. Streamlit Community Cloud puts an app to
sleep after 12 hours without a live session, and a plain HTTP request does
not count, so the keep-awake workflow runs this every few hours.

    python tools/visit.py [url]
"""

import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://apptruism.streamlit.app/"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    start = time.monotonic()
    page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
    # Click the wake-up button if the app is asleep.
    try:
        page.get_by_role("button", name="Yes, get this app back up!").click(timeout=5_000)
        print("app was asleep; asked for it to wake")
    except Exception:  # noqa: BLE001 - no button means it is awake
        pass
    # Community Cloud serves the app inside an iframe, so the ranking header
    # appears in a child frame, not the top page. Poll every frame.
    deadline = time.monotonic() + 300
    seen = ""
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                text = " ".join(frame.inner_text("body").split())
            except Exception:  # noqa: BLE001 - cross-origin or not loaded yet
                continue
            if "organizations" in text:
                seen = text
                break
        if seen:
            break
        page.wait_for_timeout(2_000)
    if not seen:
        page.screenshot(path="visit-failed.png")
        raise SystemExit("the ranking never rendered; see visit-failed.png")
    page.wait_for_timeout(3_000)  # hold the session open briefly so it registers
    print(f"ranking rendered after {time.monotonic() - start:.0f}s")
    browser.close()
