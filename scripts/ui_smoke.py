"""Drives the web UI in a real browser through run -> reject -> approve.

Needs the API running (uv run uvicorn api.server:app --port 8000) and Chrome
installed. Uses the live LLM, so it takes a minute or two.
Usage: uv run python -m scripts.ui_smoke [screenshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8000"
TASK = "Implement a class LRUCache with get(key) returning -1 if missing and put(key, value), O(1) each, evicting least recently used. Capacity 0 stores nothing."


def main(shots: Path) -> None:
    shots.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 900}, accept_downloads=True)
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(URL)
        page.wait_for_selector("#providerBadge:not(:empty)")
        page.screenshot(path=str(shots / "1_start.png"))

        page.fill("#task", TASK)
        page.click("#run")
        page.wait_for_selector("#liveCard:not(.hidden)")
        page.wait_for_selector("#timeline .ev", timeout=60000)
        page.screenshot(path=str(shots / "2_running.png"))

        page.wait_for_selector("#checkpointCard:not(.hidden)", timeout=180000)
        page.screenshot(path=str(shots / "3_checkpoint.png"), full_page=True)
        assert "def " in page.inner_text("#cpCode") or "class " in page.inner_text("#cpCode")

        page.click("#rejectToggle")
        page.click("#rejectSend")  # empty feedback must be refused client-side
        assert page.is_visible("#decideError"), "empty feedback should show an error"
        page.fill("#feedback", "Also make it thread-safe with a lock.")
        page.click("#rejectSend")
        page.wait_for_selector("#checkpointCard.hidden", state="attached")
        page.wait_for_function(
            "document.querySelector('#checkpointCard:not(.hidden)') && document.querySelector('#cpMeta').innerText.includes('2 of')",
            timeout=180000,
        )
        page.screenshot(path=str(shots / "4_second_checkpoint.png"), full_page=True)
        revised = page.inner_text("#cpCode")

        page.click("#approve")
        page.wait_for_selector("#resultCard:not(.hidden)", timeout=60000)
        page.screenshot(path=str(shots / "5_result.png"), full_page=True)
        with page.expect_download() as dl:
            page.click("#download")
        saved = Path(dl.value.path()).read_text()
        assert saved.strip() == page.inner_text("#resCode").strip()

        print("thread-safe revision mentions lock:", "lock" in revised.lower() or "Lock" in revised)
        print("console/page errors:", errors or "none")
        browser.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "ui_shots"))
