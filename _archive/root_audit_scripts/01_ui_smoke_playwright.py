#!/usr/bin/env python3
"""
Sigmalytic V2 Step 1 — Browser-level UI smoke test.

Purpose:
    Verify that the preserved live UI remains interactive after the f431a61 hotfix.

Mode:
    Browser read-only. No backend write. No Supabase mutation. No D3D. No Stripe.

Usage:
    py -B 01_ui_smoke_playwright.py --url https://sigmalytic-frontend.onrender.com --headless
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class ClickTarget:
    name: str
    candidates: tuple[str, ...]


TARGETS = [
    ClickTarget("Command Center", ("#tab-command", "text=Command Center")),
    ClickTarget("Live Feed", ("#tab-feed", "text=Live Feed")),
    ClickTarget("Radar Screen", ("#tab-radar", "text=Radar Screen")),
    ClickTarget("Scoreboard", ("#tab-scoreboard", "text=Scoreboard")),
    ClickTarget("Preferences", ("#tab-preferences", "text=Preferences")),
    ClickTarget("Setup", ("#tab-setup", "text=Setup")),
    ClickTarget("Load Symbol", ("button:has-text('Load Symbol')", "text=Load Symbol")),
]

FORBIDDEN_TEXT = [
    "D3F1B_TODAY_FRONTEND_FETCH_ERROR",
    "Controlled Persistence Lifecycle",
    "ATTENTION",
]


def locator_for(page, candidate: str):
    if candidate.startswith("text="):
        return page.get_by_text(candidate.removeprefix("text="), exact=False).first
    return page.locator(candidate).first


def assert_forbidden_absent(page, timeout_ms: int) -> None:
    body_text = page.locator("body").inner_text(timeout=timeout_ms)
    for forbidden in FORBIDDEN_TEXT:
        if forbidden in body_text:
            raise AssertionError(f"Forbidden global/frozen panel text found: {forbidden}")


def click_target(page, target: ClickTarget, timeout_ms: int) -> str:
    last_error: Exception | None = None

    for candidate in target.candidates:
        locator = locator_for(page, candidate)

        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
        except Exception as exc:
            last_error = exc
            continue

        try:
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

        try:
            locator.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass

        try:
            locator.click(timeout=10000)
            return f"{candidate} / normal click"
        except Exception as normal_click_error:
            last_error = normal_click_error

        try:
            locator.evaluate("(element) => element.click()")
            return f"{candidate} / DOM click fallback"
        except Exception as dom_click_error:
            last_error = dom_click_error
            continue

    raise AssertionError(f"Could not click {target.name}. Last error: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://sigmalytic-frontend.onrender.com")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except Exception as exc:
        print("FAIL: Playwright is not installed or Chromium is unavailable.")
        print("Install with:")
        print("  py -m pip install playwright")
        print("  py -m playwright install chromium")
        print(f"Import error: {exc}")
        return 2

    print("=" * 72)
    print("SIGMALYTIC V2 — UI SMOKE TEST V1.1")
    print("MODE: BROWSER READ-ONLY / NO MUTATION")
    print("=" * 72)
    print(f"URL: {args.url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page(viewport={"width": 1920, "height": 1200})
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        try:
            page.goto(args.url, wait_until="networkidle", timeout=args.timeout_ms)
            page.wait_for_selector("#main-content", timeout=args.timeout_ms)
            print("PASS: main-content exists.")

            assert_forbidden_absent(page, args.timeout_ms)
            for forbidden in FORBIDDEN_TEXT:
                print(f"PASS: forbidden global marker absent: {forbidden}")

            for target in TARGETS:
                print(f"TEST CLICK: {target.name}")
                method = click_target(page, target, args.timeout_ms)
                page.wait_for_selector("#main-content", timeout=args.timeout_ms)
                assert_forbidden_absent(page, args.timeout_ms)
                page.wait_for_timeout(500)
                print(f"PASS: clicked {target.name} using {method}")

            if console_errors:
                print("WARN: Browser console errors were observed:")
                for item in console_errors[:10]:
                    print("  ", item)
            else:
                print("PASS: no browser console errors observed during smoke path.")

            print("=" * 72)
            print("PASS: UI buttons/tiles are interactive.")
            print("PASS: global D3F/D3E panel is not blocking the app shell.")
            print("=" * 72)
            return 0

        except PlaywrightTimeoutError as exc:
            print(f"FAIL: browser timed out: {exc}")
            return 1
        except Exception as exc:
            print(f"FAIL: UI smoke test failed: {exc}")
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
