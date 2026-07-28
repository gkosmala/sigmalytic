#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

REPORT = Path("audit_step25_campaign_pipeline_read_only_validation_locator.json")

BACKEND_BASE = "https://sigmalytic-backend.onrender.com"

CANDIDATE_ENDPOINT_PATTERNS = [
    r'["\'](/api/[^"\']*campaign[^"\']*read[^"\']*)["\']',
    r'["\'](/api/[^"\']*pipeline[^"\']*read[^"\']*)["\']',
    r'["\'](/api/[^"\']*campaign[^"\']*validation[^"\']*)["\']',
    r'["\'](/api/[^"\']*pipeline[^"\']*validation[^"\']*)["\']',
    r'["\'](/api/[^"\']*campaign[^"\']*coverage[^"\']*)["\']',
    r'["\'](/api/[^"\']*pipeline[^"\']*coverage[^"\']*)["\']',
    r'["\'](/api/[^"\']*diagnostic[^"\']*campaign[^"\']*)["\']',
]

UNSAFE_ENDPOINT_TERMS = [
    "run-full-nightly",
    "run_full_nightly",
    "write",
    "insert",
    "upsert",
    "delete",
    "mutation",
    "mutate",
    "execute",
    "authorize",
    "d3d",
    "stripe",
    "billing",
]

REQUIRED_SNAPSHOT_FIELDS = [
    "universe_count",
    "bars_symbols_count",
    "symbols_missing_bars",
    "record_min_bars",
    "pagination_complete",
    "schema_payload_alignment",
    "write_path_not_executed_during_validation",
]

SOURCE_REQUIRED_TERMS = [
    "universe",
    "bars",
    "campaign",
    "supabase",
    "payload",
    "schema",
]


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def should_scan(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts or ".git" in parts:
        return False
    return path.suffix.lower() == ".py" and path.parts and path.parts[0] in {"backend", "frontend"}


def find_candidate_endpoints() -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    for path in sorted(Path(".").rglob("*.py")):
        if not should_scan(path):
            continue

        text = safe_read(path)
        lines = text.splitlines()

        try:
            ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        for idx, line in enumerate(lines, start=1):
            for pattern in CANDIDATE_ENDPOINT_PATTERNS:
                for match in re.finditer(pattern, line, flags=re.IGNORECASE):
                    endpoint = match.group(1)
                    key = f"{endpoint}|{path}|{idx}"
                    if key in seen:
                        continue
                    seen.add(key)

                    unsafe = any(term in endpoint.lower() for term in UNSAFE_ENDPOINT_TERMS)

                    hits.append({
                        "endpoint": endpoint,
                        "path": str(path),
                        "line": idx,
                        "unsafe": unsafe,
                        "text": line.strip(),
                    })

    return hits


def source_term_presence() -> dict[str, bool]:
    combined_parts: list[str] = []

    for path in sorted(Path("backend").rglob("*.py")):
        if should_scan(path):
            combined_parts.append(safe_read(path).lower())

    combined = "\n".join(combined_parts)

    return {
        term: term.lower() in combined
        for term in SOURCE_REQUIRED_TERMS
    }


def get_json(endpoint: str) -> tuple[int | None, dict[str, Any] | None, str | None]:
    url = BACKEND_BASE.rstrip("/") + endpoint

    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "Sigmalytic-Step25-ReadOnlyValidationLocator/1.0"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            body = response.read().decode("utf-8", errors="replace")

        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return status, parsed, None
            return status, None, "JSON root is not object"
        except Exception as exc:
            return status, None, f"JSON parse failed: {exc}"

    except Exception as exc:
        return None, None, str(exc)


def snapshot_field_check(payload: dict[str, Any]) -> dict[str, bool]:
    flat = json.dumps(payload).lower()
    return {
        field: field.lower() in flat
        for field in REQUIRED_SNAPSHOT_FIELDS
    }


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 25 CAMPAIGN PIPELINE READ-ONLY VALIDATION LOCATOR")
    print("MODE: LOCAL SOURCE LOCATOR + GET-ONLY ENDPOINT CHECK / NO WRITE")
    print("=" * 72)

    failures: list[str] = []
    reviews: list[str] = []

    source_terms = source_term_presence()
    missing_source_terms = [term for term, present in source_terms.items() if not present]

    if missing_source_terms:
        failures.append(f"missing required source terms: {missing_source_terms}")

    endpoints = find_candidate_endpoints()
    safe_candidates = [item for item in endpoints if not item["unsafe"]]

    checked: list[dict[str, Any]] = []

    for item in safe_candidates[:20]:
        endpoint = item["endpoint"]
        status, payload, error = get_json(endpoint)

        entry: dict[str, Any] = {
            "endpoint": endpoint,
            "status_code": status,
            "error": error,
            "snapshot_field_check": None,
            "qualifies_as_snapshot_candidate": False,
        }

        if payload is not None:
            field_check = snapshot_field_check(payload)
            entry["snapshot_field_check"] = field_check
            entry["qualifies_as_snapshot_candidate"] = all(field_check.values())

        checked.append(entry)

    qualifying = [item for item in checked if item["qualifies_as_snapshot_candidate"]]

    if not qualifying:
        reviews.append(
            "No existing live GET endpoint currently exposes the complete campaign pipeline validation snapshot contract."
        )

    report = {
        "mode": "LOCAL_SOURCE_LOCATOR_AND_GET_ONLY_ENDPOINT_CHECK_NO_WRITE",
        "status": "PASS" if not failures else "FAIL",
        "source_terms": source_terms,
        "missing_source_terms": missing_source_terms,
        "candidate_endpoints": endpoints,
        "safe_candidate_endpoints": safe_candidates,
        "checked_live_endpoints": checked,
        "qualifying_snapshot_endpoints": qualifying,
        "required_snapshot_fields": REQUIRED_SNAPSHOT_FIELDS,
        "readiness": {
            "campaign_pipeline_validated_can_advance": bool(qualifying),
            "reason": (
                "campaign_pipeline_validated may advance only if a live GET endpoint "
                "exposes the complete read-only snapshot contract with all required fields."
            ),
        },
        "reviews": reviews,
        "failures": failures,
        "doctrine": {
            "get_only": True,
            "no_nightly_run": True,
            "no_alpaca_call_from_this_script": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Source terms:", source_terms)
    print("Candidate endpoints found:", len(endpoints))
    print("Safe candidate endpoints:", len(safe_candidates))
    print("Live checked endpoints:", len(checked))
    print("Qualifying snapshot endpoints:", len(qualifying))
    print("Report written:", REPORT)

    if safe_candidates:
        print("\nSAFE CANDIDATE ENDPOINTS")
        for item in safe_candidates[:40]:
            print(f"CANDIDATE: {item['endpoint']} | {item['path']}:{item['line']}")

    if checked:
        print("\nLIVE GET CHECKS")
        for item in checked:
            print(
                f"CHECK: {item['endpoint']} | status={item['status_code']} "
                f"| qualifies={item['qualifies_as_snapshot_candidate']} | error={item['error']}"
            )

    if qualifying:
        print("\nQUALIFYING SNAPSHOT ENDPOINTS")
        for item in qualifying:
            print(f"QUALIFIES: {item['endpoint']}")

    if reviews:
        print("\nREVIEWS")
        for review in reviews:
            print("REVIEW:", review)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 25 PIPELINE VALIDATION LOCATOR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 25 COMPLETE — PIPELINE VALIDATION LOCATOR PASSED")
    if qualifying:
        print("PASS: existing live read-only snapshot endpoint found.")
    else:
        print("PASS: no mutation occurred; next step must add a read-only validation snapshot endpoint.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
