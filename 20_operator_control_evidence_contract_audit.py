#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

MODULE_PATH = Path("backend/campaign_engine/operator_control_evidence_contract.py")
REPORT = Path("audit_step20_operator_control_evidence_contract.json")


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("operator_control_evidence_contract", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load operator_control_evidence_contract module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_payload() -> dict[str, Any]:
    return {
        "operator_control_evidence": {
            "tested_supply_exhaustion": {
                "present": True,
                "source": "read_only_campaign_evidence",
                "explanation": "Supply exhaustion is tested through repeated failure of supply to extend downside.",
            },
            "active_demand_validation": {
                "present": True,
                "source": "read_only_campaign_evidence",
                "explanation": "Demand is active through support response and renewed absorption.",
            },
            "support_validation": {
                "present": True,
                "source": "read_only_campaign_evidence",
                "explanation": "Support validation is present through repeated defense of structural level.",
            },
            "structural_location": {
                "present": True,
                "source": "read_only_campaign_evidence",
                "explanation": "Location is structurally meaningful within the campaign base/resolution zone.",
            },
            "absence_of_contrary_failure": {
                "present": True,
                "source": "read_only_campaign_evidence",
                "explanation": "No contrary failure is present in the evidence set.",
            },
            "survival_score": 99,
            "rank": 1,
            "probability": 0.99,
            "gamma": "fresh",
        }
    }


def score_only_payload() -> dict[str, Any]:
    return {
        "operator_control_evidence": {
            "survival_score": 99,
            "campaign_score": 98,
            "rank": 1,
            "probability": 0.99,
            "gamma": "fresh",
        }
    }


def forbidden_action_payload() -> dict[str, Any]:
    payload = valid_payload()
    payload["operator_control_confirmed"] = True
    payload["authorizes_d3d"] = True
    return payload


def missing_required_payload() -> dict[str, Any]:
    payload = valid_payload()
    del payload["operator_control_evidence"]["active_demand_validation"]
    return payload


def assert_condition(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        print("PASS:", message)
    else:
        print("FAIL:", message)
        failures.append(message)


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 20 OPERATOR-CONTROL EVIDENCE CONTRACT AUDIT")
    print("MODE: LOCAL CONTRACT AUDIT / NO PRODUCTION MUTATION")
    print("=" * 72)

    failures: list[str] = []

    if not MODULE_PATH.exists():
        print("FAIL: contract module missing")
        return 1

    module = load_module()
    validate = module.validate_operator_control_evidence_contract

    result_valid = validate(valid_payload())
    result_score_only = validate(score_only_payload())
    result_forbidden = validate(forbidden_action_payload())
    result_missing = validate(missing_required_payload())

    assert_condition(
        result_valid["status"] == "EVIDENCE_SUFFICIENT_READ_ONLY_NOT_A_TRADE_SIGNAL",
        "valid evidence payload accepted as read-only evidence sufficient",
        failures,
    )

    assert_condition(
        result_valid["operator_control_confirmed"] is False,
        "valid evidence payload does not confirm operator control",
        failures,
    )

    assert_condition(
        result_valid["d3d_authorized"] is False,
        "valid evidence payload does not authorize D3D",
        failures,
    )

    assert_condition(
        result_valid["trade_signal"] is False,
        "valid evidence payload does not create trade signal",
        failures,
    )

    assert_condition(
        result_score_only["evidence_sufficient"] is False,
        "score/rank/probability/gamma-only payload rejected",
        failures,
    )

    assert_condition(
        result_forbidden["evidence_sufficient"] is False,
        "payload with forbidden action flags rejected",
        failures,
    )

    assert_condition(
        result_missing["evidence_sufficient"] is False,
        "payload missing active_demand_validation rejected",
        failures,
    )

    required_keys = set(module.REQUIRED_EVIDENCE_KEYS)
    expected_keys = {
        "tested_supply_exhaustion",
        "active_demand_validation",
        "support_validation",
        "structural_location",
        "absence_of_contrary_failure",
    }

    assert_condition(
        required_keys == expected_keys,
        "required evidence key set is exact and complete",
        failures,
    )

    report = {
        "mode": "LOCAL_CONTRACT_AUDIT_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "contract_version": module.CONTRACT_VERSION,
        "failures": failures,
        "results": {
            "valid_payload": result_valid,
            "score_only_payload": result_score_only,
            "forbidden_action_payload": result_forbidden,
            "missing_required_payload": result_missing,
        },
        "doctrine": {
            "operator_control_is_evidence_not_score": True,
            "score_rank_probability_gamma_only_rejected": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Report written:", REPORT)

    if failures:
        print("=" * 72)
        print("FAIL: STEP 20 CONTRACT AUDIT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 20 COMPLETE — OPERATOR-CONTROL EVIDENCE CONTRACT HARDENED")
    print("PASS: evidence sufficient does not mutate, confirm, authorize D3D, or create trade signals.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
