#!/usr/bin/env python3
"""
Sigmalytic V2 Step 13 — Final local no-drift closure sweep.

Purpose:
    Run the completed gate checks before commit/tag.

Mode:
    Local checks plus GET-only live checks.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPORT = Path("audit_step13_final_no_drift_closure_sweep.json")

COMMANDS = [
    {
        "name": "Step 1 UI smoke test",
        "cmd": ["py", "-B", "01_ui_smoke_playwright.py", "--url", "https://sigmalytic-frontend.onrender.com", "--headless"],
        "expected": 0,
    },
    {
        "name": "Step 3 no-drift regression sweep",
        "cmd": ["py", "-B", "03_no_drift_regression_sweep.py"],
        "expected": 0,
    },
    {
        "name": "Step 7D post-quarantine audit",
        "cmd": ["py", "-B", "07d_post_quarantine_audit.py"],
        "expected": 0,
    },
    {
        "name": "Step 8 lifecycle transition law audit",
        "cmd": ["py", "-B", "08_lifecycle_transition_law_audit.py", "--law", "lifecycle_transition_law.json"],
        "expected": 0,
    },
    {
        "name": "Step 9A semantic alert guardrail audit",
        "cmd": ["py", "-B", "09a_semantic_alert_guardrail_audit.py", "--root", "backend"],
        "expected": 0,
    },
    {
        "name": "Step 10 observability deploy check",
        "cmd": ["py", "-B", "10_observability_deploy_check.py"],
        "expected": 0,
    },
    {
        "name": "Step 11 documentation completeness audit",
        "cmd": ["py", "-B", "11_documentation_completeness_audit.py", "--docs", "docs", "--report", "audit_step11_documentation_completeness.json"],
        "expected": 0,
    },
    {
        "name": "Step 12 billing last gate",
        "cmd": ["py", "-B", "12_billing_last_gate.py", "--readiness", "v2_readiness.json"],
        "expected": 1,
        "expected_reason": "Billing/Stripe must remain blocked until remaining product gates are complete.",
    },
]

COMPILE_TARGETS = [
    "01_ui_smoke_playwright.py",
    "02_d3f2_callback_safe_locator.py",
    "03_no_drift_regression_sweep.py",
    "04_operator_control_evidence_validator.py",
    "05_pipeline_coverage_audit.py",
    "06_wlw_evidence_reconciliation.py",
    "07_legacy_fallback_quarantine_audit.py",
    "07a_legacy_fallback_classification.py",
    "07b_quarantine_signal_birth_score_dependency.py",
    "07c_verify_signal_birth_quarantine.py",
    "07d_post_quarantine_audit.py",
    "08_lifecycle_transition_law_audit.py",
    "09_alert_readiness_guardrail_audit.py",
    "09a_semantic_alert_guardrail_audit.py",
    "10_observability_deploy_check.py",
    "11_documentation_completeness_audit.py",
    "12_billing_last_gate.py",
    "13_final_no_drift_closure_sweep.py",
    "backend/signal_birth_engine.py",
]


def run(cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 13 FINAL LOCAL NO-DRIFT CLOSURE SWEEP")
    print("MODE: LOCAL + GET-ONLY / NO PRODUCTION MUTATION")
    print("=" * 72)

    failures: list[str] = []
    results: list[dict[str, Any]] = []

    print("\nPYTHON COMPILE CHECKS")
    for target in COMPILE_TARGETS:
        path = Path(target)
        if not path.exists():
            failures.append(f"missing compile target: {target}")
            print(f"FAIL: missing compile target: {target}")
            continue

        result = run(["py", "-m", "py_compile", target])
        results.append({"name": f"compile {target}", **result})

        if result["returncode"] == 0:
            print(f"PASS: compiles cleanly: {target}")
        else:
            failures.append(f"compile failed: {target}")
            print(f"FAIL: compile failed: {target}")
            print(result["stderr"])

    print("\nGATE CHECKS")
    for item in COMMANDS:
        name = item["name"]
        expected = item["expected"]
        result = run(item["cmd"])
        results.append({"name": name, **result})

        if result["returncode"] == expected:
            print(f"PASS: {name}")
            if "expected_reason" in item:
                print(f"PASS: expected blocked state confirmed — {item['expected_reason']}")
        else:
            failures.append(f"{name}: expected exit {expected}, got {result['returncode']}")
            print(f"FAIL: {name}")
            print(f"Expected exit: {expected}")
            print(f"Actual exit: {result['returncode']}")
            print(result["stdout"])
            print(result["stderr"])

    print("\nGIT STATUS INVENTORY")
    git_status = run(["git", "status", "--short"])
    print(git_status["stdout"])

    report = {
        "mode": "LOCAL_AND_GET_ONLY_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "git_status_short": git_status["stdout"],
        "doctrine": {
            "operator_control_is_evidence_not_score": True,
            "d3d_remains_blocked": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_correctly_blocked": True
        },
        "results": results,
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written: {REPORT}")

    if failures:
        print("=" * 72)
        print("FAIL: STEP 13 FINAL CLOSURE SWEEP FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 13 COMPLETE — FINAL LOCAL NO-DRIFT CLOSURE SWEEP PASSED")
    print("PASS: billing remains correctly blocked.")
    print("PASS: ready for commit/tag decision.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
