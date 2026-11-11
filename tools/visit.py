"""
Open the hosted app in a headless browser and wait for the ranking to
render, the way a visitor would. Streamlit Community Cloud puts an app to
sleep after 12 hours without a live session, and a plain HTTP request does
not count, so the keep-awake workflow runs this every few hours.

    python tools/visit.py [url]
"""

import re
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://apptruism.streamlit.app/"
WAIT_SECONDS = 600

def fail(reason: str) -> None:
    # A workflow annotation: shows on the run page, in the failure email's
    # run view, and through the public API, so nobody needs the raw log.
    print(f"::error title=Keep-awake visit failed::{reason}", flush=True)
    raise SystemExit(1)


with sync_playwright() as p:
    # GitHub's runners ship with Chrome, so use it and skip the 150 MB
    # browser download that once hung the job. Fall back to Playwright's own
    # Chromium where Chrome is missing.
    try:
        browser = p.chromium.launch(channel="chrome")
    except Exception:  # noqa: BLE001
        try:
            browser = p.chromium.launch()
        except Exception:  # noqa: BLE001 - neither is present: fetch Chromium once
            subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
                           check=True, timeout=420)
            browser = p.chromium.launch()
    page = browser.new_page()
    start = time.monotonic()
    page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
    # Click the wake-up button if the app is asleep.
    try:
        page.get_by_role("button", name=re.compile("get this app back up|wake", re.I)).click(timeout=5_000)
        print("app was asleep; asked for it to wake", flush=True)
    except Exception:  # noqa: BLE001 - no button means it is awake
        pass
    # Community Cloud serves the app inside an iframe, so the ranking header
    # appears in a child frame, not the top page. Poll every frame.
    # A cold start downloads a 550 MB release before the ranking can show,
    # which has taken seven minutes on Streamlit's side, so wait up to ten.
    deadline = time.monotonic() + WAIT_SECONDS
    seen = ""
    last_report = 0.0
    while time.monotonic() < deadline:
        snapshots = []
        for frame in page.frames:
            try:
                text = " ".join(frame.inner_text("body").split())
            except Exception:  # noqa: BLE001 - cross-origin or not loaded yet
                continue
            snapshots.append(text)
            if "organizations" in text:
                seen = text
                break
        if seen:
            break
        if time.monotonic() - last_report >= 30:
            # Progress for the run log, so a failure explains itself.
            longest = max(snapshots, key=len, default="")
            print(f"  t+{time.monotonic() - start:4.0f}s  app frame: {longest[:110]!r}", flush=True)
            last_report = time.monotonic()
        page.wait_for_timeout(2_000)
    if not seen:
        page.screenshot(path="visit-failed.png")
        longest = max(snapshots, key=len, default="")
        fail(f"no ranking after {WAIT_SECONDS}s. The app showed: {longest[:300] or 'nothing'}")
    page.wait_for_timeout(3_000)  # hold the session open briefly so it registers
    print(f"ranking rendered after {time.monotonic() - start:.0f}s")
    browser.close()
