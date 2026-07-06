from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


CONTRACT_NAME = "SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT"
CONTRACT_VERSION = "source_resolution_src7a_explicit_sml_contract_v1"

ALLOWED_LEVEL_TYPES = {
    "EXPLICIT_SML",
    "EXPLICIT_SUPPORT",
    "EXPLICIT_RESISTANCE",
    "EXPLICIT_STRUCTURAL_LOCATION",
    "EXPLICIT_TRUE_HVN",
    "EXPLICIT_TRUE_POC",
    "EXPLICIT_RANGE_LOW",
    "EXPLICIT_RANGE_HIGH",
}

ALLOWED_SOURCE_METHODS = {
    "MANUAL_STRUCTURAL_MARKUP",
    "AUDITED_CHART_STRUCTURAL_MARKUP",
    "PROVIDER_EXPLICIT_STRUCTURAL_LEVEL",
    "TRUE_VOLUME_AT_PRICE_PROVIDER",
    "TICK_DERIVED_VOLUME_AT_PRICE",
    "EXCHANGE_VOLUME_AT_PRICE",
}

REJECTED_SOURCE_METHODS = {
    "INFERRED_SML",
    "INFERRED_STRUCTURAL_LOCATION",
    "HVN_ABSORPTION_PROXY",
    "OHLCV_DERIVED_PROFILE_APPROXIMATION",
    "DAILY_OHLCV_DERIVED_APPROXIMATION",
    "INTRADAY_OHLCV_DERIVED_APPROXIMATION",
    "SCORE_DERIVED",
    "RANK_DERIVED",
    "EDGE_DERIVED",
    "PROBABILITY_DERIVED",
    "TRADE_SIGNAL_DERIVED",
}

REQUIRED_TEXT_FIELDS = {
    "symbol",
    "level_type",
    "source_method",
    "source_reference",
    "source_timestamp_utc",
    "observed_window_start_utc",
    "observed_window_end_utc",
}

FORBIDDEN_TRUE_FLAGS = {
    "is_inferred",
    "is_proxy",
    "is_hvn_absorption_proxy",
    "derived_from_score",
    "derived_from_rank",
    "derived_from_probability",
    "derived_from_edge",
    "derived_from_expected_return",
    "derived_from_target_projection",
    "derived_from_trade_signal",
    "derived_from_gamma_options_overlay",
    "derived_from_ohlcv_profile_approximation",
    "confirms_operator_control",
    "authorizes_d3d",
    "mutates_campaigns",
    "writes_to_supabase",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _upper(value: Any) -> str:
    return _string(value).upper()


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    if isinstance(value, str):
        lowered = value.strip().lower()

        if lowered in {"true", "1", "yes", "y"}:
            return True

        if lowered in {"false", "0", "no", "n"}:
            return False

    return None


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def validate_explicit_sml_record(record: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not isinstance(record, dict):
        return {
            "contract": CONTRACT_NAME,
            "version": CONTRACT_VERSION,
            "validation_timestamp_utc": _utc_now(),
            "record_valid": False,
            "d3d_preflight_ready": False,
            "production_mutation_authorized": False,
            "failure_count": 1,
            "failures": [
                {
                    "field": "record",
                    "expected": "dict",
                    "actual": type(record).__name__,
                }
            ],
            "warnings": [],
        }

    normalized = {
        "symbol": _upper(record.get("symbol")),
        "level_type": _upper(record.get("level_type")),
        "source_method": _upper(record.get("source_method")),
        "source_reference": _string(record.get("source_reference")),
        "source_timestamp_utc": _string(record.get("source_timestamp_utc")),
        "observed_window_start_utc": _string(record.get("observed_window_start_utc")),
        "observed_window_end_utc": _string(record.get("observed_window_end_utc")),
        "price_low": _finite_float(record.get("price_low")),
        "price_mid": _finite_float(record.get("price_mid")),
        "price_high": _finite_float(record.get("price_high")),
        "is_explicit": _bool(record.get("is_explicit")),
    }

    for field in REQUIRED_TEXT_FIELDS:
        if not normalized[field]:
            failures.append(
                {
                    "field": field,
                    "expected": "non-empty explicit source field",
                    "actual": record.get(field),
                }
            )

    if normalized["level_type"] not in ALLOWED_LEVEL_TYPES:
        failures.append(
            {
                "field": "level_type",
                "expected": sorted(ALLOWED_LEVEL_TYPES),
                "actual": record.get("level_type"),
            }
        )

    if normalized["source_method"] not in ALLOWED_SOURCE_METHODS:
        failures.append(
            {
                "field": "source_method",
                "expected": sorted(ALLOWED_SOURCE_METHODS),
                "actual": record.get("source_method"),
            }
        )

    if normalized["source_method"] in REJECTED_SOURCE_METHODS:
        failures.append(
            {
                "field": "source_method",
                "expected": "non-proxy, non-inferred, non-score-derived method",
                "actual": record.get("source_method"),
            }
        )

    if normalized["price_low"] is None:
        failures.append(
            {
                "field": "price_low",
                "expected": "finite numeric price",
                "actual": record.get("price_low"),
            }
        )

    if normalized["price_mid"] is None:
        failures.append(
            {
                "field": "price_mid",
                "expected": "finite numeric price",
                "actual": record.get("price_mid"),
            }
        )

    if normalized["price_high"] is None:
        failures.append(
            {
                "field": "price_high",
                "expected": "finite numeric price",
                "actual": record.get("price_high"),
            }
        )

    if (
        normalized["price_low"] is not None
        and normalized["price_mid"] is not None
        and normalized["price_high"] is not None
    ):
        if not (normalized["price_low"] <= normalized["price_mid"] <= normalized["price_high"]):
            failures.append(
                {
                    "field": "price_order",
                    "expected": "price_low <= price_mid <= price_high",
                    "actual": {
                        "price_low": normalized["price_low"],
                        "price_mid": normalized["price_mid"],
                        "price_high": normalized["price_high"],
                    },
                }
            )

        if normalized["price_low"] <= 0 or normalized["price_mid"] <= 0 or normalized["price_high"] <= 0:
            failures.append(
                {
                    "field": "price_values",
                    "expected": "positive price values",
                    "actual": {
                        "price_low": normalized["price_low"],
                        "price_mid": normalized["price_mid"],
                        "price_high": normalized["price_high"],
                    },
                }
            )

    if normalized["is_explicit"] is not True:
        failures.append(
            {
                "field": "is_explicit",
                "expected": True,
                "actual": record.get("is_explicit"),
            }
        )

    for field in FORBIDDEN_TRUE_FLAGS:
        value = _bool(record.get(field))

        if value is True:
            failures.append(
                {
                    "field": field,
                    "expected": False,
                    "actual": record.get(field),
                }
            )

    source_text = " ".join(
        [
            normalized["source_method"],
            normalized["source_reference"],
            _string(record.get("notes")),
            _string(record.get("source_label")),
        ]
    ).upper()

    forbidden_terms = [
        "INFERRED",
        "PROXY",
        "SYNTHETIC",
        "APPROXIMATION",
        "SCORE DERIVED",
        "RANK DERIVED",
        "EDGE DERIVED",
        "TRADE SIGNAL",
        "HVN_ABSORPTION_PROXY",
    ]

    for term in forbidden_terms:
        if term in source_text:
            failures.append(
                {
                    "field": "source_text",
                    "expected": f"must not contain {term}",
                    "actual": source_text,
                }
            )
            break

    if normalized["level_type"] in {"EXPLICIT_TRUE_HVN", "EXPLICIT_TRUE_POC"}:
        if normalized["source_method"] not in {
            "TRUE_VOLUME_AT_PRICE_PROVIDER",
            "TICK_DERIVED_VOLUME_AT_PRICE",
            "EXCHANGE_VOLUME_AT_PRICE",
            "AUDITED_CHART_STRUCTURAL_MARKUP",
        }:
            failures.append(
                {
                    "field": "true_hvn_poc_source_method",
                    "expected": [
                        "TRUE_VOLUME_AT_PRICE_PROVIDER",
                        "TICK_DERIVED_VOLUME_AT_PRICE",
                        "EXCHANGE_VOLUME_AT_PRICE",
                        "AUDITED_CHART_STRUCTURAL_MARKUP",
                    ],
                    "actual": normalized["source_method"],
                }
            )

    if _bool(record.get("eligible_for_immediate_d3d_mutation")) is True:
        failures.append(
            {
                "field": "eligible_for_immediate_d3d_mutation",
                "expected": False,
                "actual": record.get("eligible_for_immediate_d3d_mutation"),
            }
        )

    if record.get("campaign_id") in ["", None]:
        warnings.append("campaign_id is absent. Contract validation can pass, but campaign binding is required before any future dry-run preflight.")

    record_valid = len(failures) == 0

    return {
        "contract": CONTRACT_NAME,
        "version": CONTRACT_VERSION,
        "validation_timestamp_utc": _utc_now(),
        "record_valid": record_valid,
        "d3d_preflight_ready": record_valid,
        "production_mutation_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "operator_control_confirmed_by_this_contract": False,
        "normalized_record": normalized,
        "failure_count": len(failures),
        "failures": failures,
        "warnings": warnings,
    }


def validate_many_explicit_sml_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    results = [validate_explicit_sml_record(record) for record in records]

    valid_count = sum(1 for item in results if item.get("record_valid") is True)
    invalid_count = len(results) - valid_count

    return {
        "contract": CONTRACT_NAME,
        "version": CONTRACT_VERSION,
        "validation_timestamp_utc": _utc_now(),
        "record_count": len(results),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "production_mutation_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "operator_control_confirmed_by_this_contract": False,
        "results": results,
    }
