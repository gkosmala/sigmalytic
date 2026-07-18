from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_FRONTEND_URL = "https://sigmalytic-frontend.onrender.com"

REQUIRED_CLICK_GROUPS = [
    {"name": "Behavioral Intelligence", "candidates": ["Behavioral Intelligence", "Command Center"]},
    {"name": "Campaigns", "candidates": ["Campaigns"]},
    {"name": "Portfolio", "candidates": ["Portfolio"]},
    {"name": "Journal", "candidates": ["Journal"]},
    {"name": "Import History", "candidates": ["Import History"]},
    {"name": "Radar Screen", "candidates": ["Radar Screen"]},
    {"name": "Scoreboard", "candidates": ["Scoreboard"]},
    {"name": "Divergence", "candidates": ["Divergence"]},
    {"name": "Preferences", "candidates": ["Preferences"]},
    {"name": "Admin", "candidates": ["Admin"]},
    {"name": "Setup", "candidates": ["Setup"]},
]

OPTIONAL_CLICK_GROUPS = [
    {"name": "Billing", "candidates": ["Billing"]},
]

SHELL_MARKERS = [
    "Decision Command Center",
    "Radar Screen",
    "Scoreboard",
    "Preferences",
    "Setup",
]

FORBIDDEN_GLOBAL_MARKERS = [
    "D3F1B_TODAY_FRONTEND_FETCH_ERROR",
    "Controlled Persistence Lifecycle",
    "D3E.9 Final Lifecycle Regression Sweep",
    "ATTENTION",
]


def event(events: list[dict[str, Any]], level: str, message: str, **extra: Any) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "message": message}
    payload.update(extra)
    events.append(payload)
    print(f"{level}: {message}", flush=True)


def find_clickable(page: Any, labels: list[str], timeout_ms: int = 3500) -> tuple[Any | None, str | None]:
    for label in labels:
        locators = [
            page.get_by_role("button", name=label, exact=True).first(),
            page.get_by_text(label, exact=True).first(),
            page.locator(f"text={label}").first(),
        ]
        for locator in locators:
            try:
                locator.wait_for(state="visible", timeout=timeout_ms)
                return locator, label
            except PlaywrightTimeoutError:
                continue
    return None, None


def wait_for_auth_if_needed(page: Any, events: list[dict[str, Any]], timeout_seconds: int) -> None:
    overlay = page.locator("#auth-overlay")
    try:
        visible = overlay.is_visible(timeout=3000)
    except Exception:
        visible = False

    if not visible:
        event(events, "PASS", "Authentication overlay is not visibly blocking the app.")
        return

    event(events, "WARN", "Authentication overlay visible. Complete login in Chromium if prompted.")
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            if not overlay.is_visible(timeout=1000):
                event(events, "PASS", "Authentication overlay cleared.")
                return
        except Exception:
            event(events, "PASS", "Authentication overlay no longer detectable.")
            return
        time.sleep(1)

    raise AssertionError("Authentication overlay remained visible and blocked the browser regression test.")


def verify_shell(page: Any, events: list[dict[str, Any]]) -> None:
    page.locator("body").wait_for(state="visible", timeout=30000)
    body = page.locator("body").inner_text(timeout=15000)
    missing = [marker for marker in SHELL_MARKERS if marker not in body]
    if missing:
        raise AssertionError(f"Missing required live shell markers: {missing}")
    event(events, "PASS", "Live app shell markers are present.", markers=SHELL_MARKERS)


def verify_no_forbidden_global_markers(page: Any, events: list[dict[str, Any]]) -> None:
    body = page.locator("body").inner_text(timeout=15000)
    found = [marker for marker in FORBIDDEN_GLOBAL_MARKERS if marker in body]
    if found:
        raise AssertionError(f"Forbidden global D3F/D3E markers visible in live UI: {found}")
    event(events, "PASS", "Forbidden global D3F/D3E panel markers are absent.")


def click_group(page: Any, group: dict[str, Any], required: bool, events: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"name": group["name"], "required": required, "clicked": False, "matched_label": None, "status": "NOT_RUN"}
    locator, label = find_clickable(page, group["candidates"])

    if locator is None:
        if required:
            raise AssertionError(f"Required click target not found: {group['name']}")
        result["status"] = "SKIPPED_OPTIONAL_NOT_FOUND"
        event(events, "SKIP", f"Optional click target not found: {group['name']}")
        return result

    locator.click(timeout=12000)
    page.wait_for_timeout(1100)
    page.locator("body").wait_for(state="visible", timeout=15000)

    result["clicked"] = True
    result["matched_label"] = label
    result["status"] = "PASS"
    event(events, "PASS", f"Clicked {group['name']}.", matched_label=label)
    return result


def test_load_symbol(page: Any, events: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"name": "Load Symbol", "required": True, "clicked": False, "matched_label": None, "status": "NOT_RUN"}

    ticker_input = page.locator("#ticker-input").first()
    ticker_input.wait_for(state="visible", timeout=15000)
    ticker_input.fill("MSFT", timeout=10000)

    locator, label = find_clickable(page, ["Load Symbol"], timeout_ms=5000)
    if locator is None:
        raise AssertionError("Load Symbol button was not found.")

    locator.click(timeout=12000)
    page.wait_for_timeout(1800)

    result["clicked"] = True
    result["matched_label"] = label
    result["status"] = "PASS"
    event(events, "PASS", "Clicked Load Symbol after filling ticker input.", symbol="MSFT")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sigmalytic V2 browser regression smoke test.")
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--profile-dir", default=".sigmalytic_playwright_profile")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--auth-timeout-seconds", type=int, default=240)
    parser.add_argument("--slowmo", type=int, default=120)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict[str, Any]] = []
    click_results: list[dict[str, Any]] = []
    page_errors: list[str] = []
    console_errors: list[str] = []

    report: dict[str, Any] = {
        "test_name": "SIGMALYTIC_V2_BROWSER_REGRESSION_SMOKE",
        "mode": "LIVE_BROWSER_SMOKE_READ_ONLY",
        "frontend_url": args.frontend_url,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "status": "RUNNING",
        "events": events,
        "click_results": click_results,
        "page_errors": page_errors,
        "console_errors": console_errors,
        "guardrails": {
            "application_runtime_patch": False,
            "supabase_write": False,
            "campaign_mutation": False,
            "d3d_authorization": False,
            "operator_control_confirmation": False,
            "trade_signal_creation": False,
            "stripe_touch": False,
        },
    }

    try:
        with sync_playwright() as p:
            profile_dir = Path(args.profile_dir)
            profile_dir.mkdir(parents=True, exist_ok=True)

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=not args.headed,
                slow_mo=args.slowmo if args.headed else 0,
                viewport={"width": 1440, "height": 950},
            )

            page = context.pages[0] if context.pages else context.new_page()
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            event(events, "INFO", "Navigating to live frontend.", url=args.frontend_url)
            page.goto(args.frontend_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1800)

            initial_png = output_dir / "initial_live_ui.png"
            page.screenshot(path=str(initial_png), full_page=True)
            event(events, "INFO", "Initial screenshot saved.", path=str(initial_png))

            wait_for_auth_if_needed(page, events, args.auth_timeout_seconds)
            verify_shell(page, events)
            verify_no_forbidden_global_markers(page, events)

            for group in REQUIRED_CLICK_GROUPS:
                click_results.append(click_group(page, group, required=True, events=events))

            for group in OPTIONAL_CLICK_GROUPS:
                click_results.append(click_group(page, group, required=False, events=events))

            click_results.append(test_load_symbol(page, events))
            verify_no_forbidden_global_markers(page, events)

            final_png = output_dir / "final_live_ui.png"
            page.screenshot(path=str(final_png), full_page=True)
            event(events, "INFO", "Final screenshot saved.", path=str(final_png))

            context.close()

        if page_errors:
            raise AssertionError(f"Browser page errors detected: {page_errors}")

        report["status"] = "PASS"
        event(events, "PASS", "Browser regression smoke test passed.")

    except Exception as exc:
        report["status"] = "FAIL"
        report["failure"] = str(exc)
        event(events, "FAIL", str(exc))

    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()

        report_path = output_dir / "browser_regression_report.json"
        summary_path = output_dir / "summary.txt"

        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        summary_lines = [
            "SIGMALYTIC V2 BROWSER REGRESSION SMOKE",
            f"STATUS: {report['status']}",
            f"FRONTEND_URL: {args.frontend_url}",
            f"REPORT_JSON: {report_path}",
            "",
            "CLICK RESULTS:",
        ]

        for result in click_results:
            summary_lines.append(
                f"- {result['name']}: {result['status']} "
                f"matched={result.get('matched_label')} required={result.get('required')}"
            )

        summary_lines.extend([
            "",
            f"PAGE_ERRORS: {len(page_errors)}",
            f"CONSOLE_ERRORS_LOGGED: {len(console_errors)}",
            "",
            "GUARDRAILS:",
            "- No application runtime patch.",
            "- No Supabase write.",
            "- No campaign mutation.",
            "- No D3D authorization.",
            "- No operator-control confirmation.",
            "- No trade signal creation.",
            "- No Stripe touch.",
        ])

        summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        print("")
        print("=" * 72)
        print(summary_path.read_text(encoding="utf-8"))
        print("=" * 72)

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())