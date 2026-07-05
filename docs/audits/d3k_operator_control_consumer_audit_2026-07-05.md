# D3K Operator-Control Consumer Audit

Date: 2026-07-05

## Purpose

D3K audits where operator-control fields are consumed in the codebase.

The objective is to prevent legacy `operator_control_confirmed` or legacy `OPERATOR_CONTROL_EVIDENCED` values from accidentally driving score, rank, state, transition, UI promotion, or production confirmation logic.

## Audit Type

Read-only documentation audit.

This audit does not change production code.

This audit does not mutate Supabase.

This audit does not confirm or unconfirm operator control.

This audit does not execute D3D.

## Search Patterns

- operator_control_confirmed
- OPERATOR_CONTROL_EVIDENCED
- operator_control
- operatorControl

## Risk Context Words

- score
- rank
- ranking
- state
- transition
- survival_score
- composite
- campaign_rank
- confirmed

## Summary

Total operator-control related hits: 277

Hits with risk-context words on same line: 120

## Hits by File

- backend\campaign_api.py: 140
- backend\campaign_engine\campaign_evidence_builder.py: 33
- backend\campaign_engine\diagnostic_doctrine_classifier.py: 8
- backend\campaign_engine\early_operator_footprint_engine.py: 16
- backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py: 8
- backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py: 5
- backend\campaign_engine\explicit_upper_zone_diagnostic_engine.py: 3
- backend\campaign_engine\operator_control_classifier.py: 1
- backend\campaign_engine\operator_control_confirmation_candidate_engine.py: 10
- backend\campaign_engine\operator_control_plausibility_status_engine.py: 17
- backend\campaign_engine\operator_control_production_mutation_gate.py: 23
- backend\campaign_engine\structural_location_input_review_engine.py: 2
- backend\campaign_engine\structural_location_validation_engine.py: 4
- backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py: 7

## Risk-Context Hits by File

- backend\campaign_api.py: 69
- backend\campaign_engine\campaign_evidence_builder.py: 12
- backend\campaign_engine\diagnostic_doctrine_classifier.py: 2
- backend\campaign_engine\early_operator_footprint_engine.py: 1
- backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py: 2
- backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py: 2
- backend\campaign_engine\explicit_upper_zone_diagnostic_engine.py: 2
- backend\campaign_engine\operator_control_confirmation_candidate_engine.py: 6
- backend\campaign_engine\operator_control_plausibility_status_engine.py: 5
- backend\campaign_engine\operator_control_production_mutation_gate.py: 12
- backend\campaign_engine\structural_location_input_review_engine.py: 1
- backend\campaign_engine\structural_location_validation_engine.py: 2
- backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py: 4

## Full Hit Table

| File | Line | Risk Context | Code |
|---|---:|---|---|
| `backend\campaign_api.py` | 240 | False | `"operator_control",` |
| `backend\campaign_api.py` | 273 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_api.py` | 279 | True | `operator_confirmed = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_api.py` | 305 | True | `"operator_control_confirmed": operator_confirmed,` |
| `backend\campaign_api.py` | 306 | False | `"operator_control_verdict": operator_control.get("verdict"),` |
| `backend\campaign_api.py` | 307 | False | `"operator_control_evidence_count": operator_control.get("evidence_count"),` |
| `backend\campaign_api.py` | 308 | False | `"operator_control_depth_requirement_met": operator_control.get("depth_requirement_met"),` |
| `backend\campaign_api.py` | 309 | False | `"operator_control_method_basis": operator_control.get("method_basis"),` |
| `backend\campaign_api.py` | 310 | True | `"operator_control_not_derived_from_scores": operator_control.get("not_derived_from_scores"),` |
| `backend\campaign_api.py` | 325 | True | `not bool(row.get("operator_control_confirmed")),` |
| `backend\campaign_api.py` | 326 | False | `-(int(row.get("operator_control_evidence_count") or 0)),` |
| `backend\campaign_api.py` | 333 | True | `if row.get("operator_control_confirmed") is True` |
| `backend\campaign_api.py` | 346 | True | `"operator_control_confirmed_count": len(operator_confirmed_rows),` |
| `backend\campaign_api.py` | 348 | True | `"operator_control_confirmed_campaigns": operator_confirmed_rows,` |
| `backend\campaign_api.py` | 365 | True | `operator_confirmed = bool(row.get("operator_control_confirmed"))` |
| `backend\campaign_api.py` | 366 | False | `operator_evidence_count = int(row.get("operator_control_evidence_count") or 0)` |
| `backend\campaign_api.py` | 494 | True | `"operator_control_confirmed_count": base.get("operator_control_confirmed_count"),` |
| `backend\campaign_api.py` | 496 | True | `"operator_control_confirmed_ranked": [` |
| `backend\campaign_api.py` | 498 | True | `if row.get("operator_control_confirmed") is True` |
| `backend\campaign_api.py` | 544 | True | `operator_confirmed = bool(match.get("operator_control_confirmed"))` |
| `backend\campaign_api.py` | 566 | True | `failed_or_missing_items.append("operator_control_confirmed")` |
| `backend\campaign_api.py` | 595 | False | `"operator_control_explanation": {` |
| `backend\campaign_api.py` | 598 | False | `"verdict": match.get("operator_control_verdict"),` |
| `backend\campaign_api.py` | 599 | False | `"evidence_count": match.get("operator_control_evidence_count"),` |
| `backend\campaign_api.py` | 600 | False | `"depth_requirement_met": match.get("operator_control_depth_requirement_met"),` |
| `backend\campaign_api.py` | 601 | False | `"method_basis": match.get("operator_control_method_basis"),` |
| `backend\campaign_api.py` | 602 | True | `"not_derived_from_scores": match.get("operator_control_not_derived_from_scores"),` |
| `backend\campaign_api.py` | 649 | True | `operator_rows = list(ranking_payload.get("operator_control_confirmed_ranked") or [])` |
| `backend\campaign_api.py` | 678 | True | `"operator_control_confirmed": row.get("operator_control_confirmed"),` |
| `backend\campaign_api.py` | 679 | False | `"operator_control_evidence_count": row.get("operator_control_evidence_count"),` |
| `backend\campaign_api.py` | 698 | False | `"operator_control_basis": "RAW_OHLCV_TAPE_BEHAVIOR_ONLY",` |
| `backend\campaign_api.py` | 699 | True | `"operator_control_not_derived_from_scores": True,` |
| `backend\campaign_api.py` | 704 | True | `"operator_control_confirmed_count": ranking_payload.get("operator_control_confirmed_count"),` |
| `backend\campaign_api.py` | 713 | True | `"operator_control_confirmed_campaigns": operator_rows,` |
| `backend\campaign_api.py` | 760 | True | `if row.get("operator_control_confirmed") is True:` |
| `backend\campaign_api.py` | 775 | True | `if row.get("operator_control_confirmed") is True and has_hard_conflict:` |
| `backend\campaign_api.py` | 778 | True | `if row.get("operator_control_confirmed") is True and has_refresh_flag:` |
| `backend\campaign_api.py` | 817 | True | `"operator_control_confirmed_count": len(operator_confirmed_rows),` |
| `backend\campaign_api.py` | 1102 | True | `and review.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 1103 | False | `and review.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_api.py` | 1164 | True | `"operator_control_confirmed_by_this_engine": review.get("operator_control_confirmed_by_this_engine"),` |
| `backend\campaign_api.py` | 1165 | False | `"operator_control_confirmation_impact": review.get("operator_control_confirmation_impact"),` |
| `backend\campaign_api.py` | 1190 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 1191 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 1327 | True | `and validation.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 1328 | False | `and validation.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_api.py` | 1384 | True | `"operator_control_confirmed_by_this_engine": validation.get("operator_control_confirmed_by_this_engine"),` |
| `backend\campaign_api.py` | 1385 | False | `"operator_control_confirmation_impact": validation.get("operator_control_confirmation_impact"),` |
| `backend\campaign_api.py` | 1407 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 1408 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 1539 | True | `and review.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 1540 | False | `and review.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_api.py` | 1601 | True | `"operator_control_confirmed_current": review.get("operator_control_confirmed_current"),` |
| `backend\campaign_api.py` | 1624 | True | `"operator_control_confirmed_by_this_engine": review.get("operator_control_confirmed_by_this_engine"),` |
| `backend\campaign_api.py` | 1625 | False | `"operator_control_confirmation_impact": review.get("operator_control_confirmation_impact"),` |
| `backend\campaign_api.py` | 1654 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 1655 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 1765 | True | `and row.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 1797 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 1878 | True | `confirmed_counter[str(bool(row.get("operator_control_confirmed_current")))] += 1` |
| `backend\campaign_api.py` | 1885 | True | `and row.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 1902 | True | `0 if row.get("operator_control_confirmed_current") is False else 1,` |
| `backend\campaign_api.py` | 1916 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 1934 | True | `"operator_control_confirmed_distribution": _counter_to_dict(confirmed_counter),` |
| `backend\campaign_api.py` | 2004 | True | `and row.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 2035 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 2064 | False | `def operator_control_plausibility_status_review():` |
| `backend\campaign_api.py` | 2080 | False | `from backend.campaign_engine.operator_control_plausibility_status_engine import (` |
| `backend\campaign_api.py` | 2083 | False | `classify_operator_control_plausibility,` |
| `backend\campaign_api.py` | 2085 | False | `from backend.campaign_engine.operator_control_production_mutation_gate import (` |
| `backend\campaign_api.py` | 2086 | False | `evaluate_d3d_operator_control_candidate,` |
| `backend\campaign_api.py` | 2089 | False | `from campaign_engine.operator_control_plausibility_status_engine import (` |
| `backend\campaign_api.py` | 2092 | False | `classify_operator_control_plausibility,` |
| `backend\campaign_api.py` | 2094 | False | `from campaign_engine.operator_control_production_mutation_gate import (` |
| `backend\campaign_api.py` | 2095 | False | `evaluate_d3d_operator_control_candidate,` |
| `backend\campaign_api.py` | 2115 | False | `d3d_candidate = evaluate_d3d_operator_control_candidate(campaign)` |
| `backend\campaign_api.py` | 2116 | False | `row = classify_operator_control_plausibility(campaign, d3d_candidate)` |
| `backend\campaign_api.py` | 2122 | True | `legacy_counter[str(bool(row.get("legacy_operator_control_confirmed")))] += 1` |
| `backend\campaign_api.py` | 2132 | True | `and row.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 2133 | True | `and row.get("operator_control_unconfirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 2167 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 2168 | True | `"operator_control_unconfirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 2185 | True | `"legacy_operator_control_confirmed_distribution": _counter_to_dict(legacy_counter),` |
| `backend\campaign_api.py` | 2197 | False | `def operator_control_production_mutation_gate(request: dict \| None = None):` |
| `backend\campaign_api.py` | 2205 | True | `- evidence.operator_control.operator_control_confirmed only` |
| `backend\campaign_api.py` | 2211 | False | `from backend.campaign_engine.operator_control_production_mutation_gate import (` |
| `backend\campaign_api.py` | 2215 | False | `evaluate_d3d_operator_control_candidate,` |
| `backend\campaign_api.py` | 2216 | False | `build_d3d_operator_control_mutation,` |
| `backend\campaign_api.py` | 2219 | False | `from campaign_engine.operator_control_production_mutation_gate import (` |
| `backend\campaign_api.py` | 2223 | False | `evaluate_d3d_operator_control_candidate,` |
| `backend\campaign_api.py` | 2224 | False | `build_d3d_operator_control_mutation,` |
| `backend\campaign_api.py` | 2266 | False | `candidate = evaluate_d3d_operator_control_candidate(c)` |
| `backend\campaign_api.py` | 2297 | False | `updated_campaign, mutation_summary = build_d3d_operator_control_mutation(` |
| `backend\campaign_api.py` | 2320 | True | `"mutation_target": "evidence.operator_control.operator_control_confirmed",` |
| `backend\campaign_api.py` | 2347 | False | `def operator_control_confirmation_candidate_review():` |
| `backend\campaign_api.py` | 2363 | False | `from backend.campaign_engine.operator_control_confirmation_candidate_engine import (` |
| `backend\campaign_api.py` | 2364 | False | `classify_operator_control_confirmation_candidate,` |
| `backend\campaign_api.py` | 2369 | False | `from campaign_engine.operator_control_confirmation_candidate_engine import (` |
| `backend\campaign_api.py` | 2370 | False | `classify_operator_control_confirmation_candidate,` |
| `backend\campaign_api.py` | 2427 | False | `candidate = classify_operator_control_confirmation_candidate(` |
| `backend\campaign_api.py` | 2437 | True | `and candidate.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 2438 | False | `and candidate.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_api.py` | 2484 | True | `"operator_control_confirmed_current": candidate.get("operator_control_confirmed_current"),` |
| `backend\campaign_api.py` | 2493 | True | `"operator_control_confirmed_by_this_engine": candidate.get("operator_control_confirmed_by_this_engine"),` |
| `backend\campaign_api.py` | 2498 | False | `"operator_control_confirmation_impact": candidate.get("operator_control_confirmation_impact"),` |
| `backend\campaign_api.py` | 2522 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_api.py` | 2523 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 2548 | False | `def operator_control_reconciliation_review():` |
| `backend\campaign_api.py` | 2633 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_api.py` | 2650 | True | `operator_control_confirmed = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_api.py` | 2651 | False | `operator_control_verdict = operator_control.get("verdict")` |
| `backend\campaign_api.py` | 2667 | True | `if operator_control_confirmed:` |
| `backend\campaign_api.py` | 2687 | False | `and footprints.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_api.py` | 2688 | True | `and footprints.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 2719 | False | `"operator_control_verdict": operator_control_verdict,` |
| `backend\campaign_api.py` | 2720 | True | `"operator_control_confirmed": operator_control_confirmed,` |
| `backend\campaign_api.py` | 2734 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 2762 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 2851 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_api.py` | 2885 | True | `operator_control_confirmed = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_api.py` | 2886 | False | `operator_control_verdict = operator_control.get("verdict")` |
| `backend\campaign_api.py` | 2888 | True | `if footprint_present and operator_control_confirmed:` |
| `backend\campaign_api.py` | 2890 | True | `elif footprint_present and not operator_control_confirmed:` |
| `backend\campaign_api.py` | 2892 | True | `elif not footprint_present and operator_control_confirmed:` |
| `backend\campaign_api.py` | 2906 | False | `and footprints.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_api.py` | 2907 | True | `and footprints.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_api.py` | 2933 | False | `"operator_control_confirmation_impact": footprints.get("operator_control_confirmation_impact"),` |
| `backend\campaign_api.py` | 2934 | True | `"operator_control_confirmed_by_this_engine": footprints.get("operator_control_confirmed_by_this_engine"),` |
| `backend\campaign_api.py` | 2942 | False | `"operator_control_verdict": operator_control_verdict,` |
| `backend\campaign_api.py` | 2943 | True | `"operator_control_confirmed": operator_control_confirmed,` |
| `backend\campaign_api.py` | 2969 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_api.py` | 3575 | True | `"operator_control_confirmed_counts": _count_nested_bool(` |
| `backend\campaign_api.py` | 3577 | False | `"operator_control",` |
| `backend\campaign_api.py` | 3578 | True | `"operator_control_confirmed",` |
| `backend\campaign_api.py` | 3580 | False | `"operator_control_verdict_counts": _count_nested_evidence_field(` |
| `backend\campaign_api.py` | 3582 | False | `"operator_control",` |
| `backend\campaign_api.py` | 3585 | False | `"operator_control_evidence_count_counts": _count_nested_evidence_field(` |
| `backend\campaign_api.py` | 3587 | False | `"operator_control",` |
| `backend\campaign_api.py` | 3609 | True | `"raw_metric_operator_control_confirmed_counts": _count_raw_metric_field(` |
| `backend\campaign_api.py` | 3611 | True | `"operator_control_confirmed",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 156 | False | `operator_control: Optional[Dict[str, Any]] = None,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 168 | False | `operator_control = operator_control or {}` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 175 | True | `operator_confirmed = bool(operator_control.get("operator_control_confirmed", False))` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 176 | False | `operator_evidence_count = int(operator_control.get("evidence_count", 0) or 0)` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 177 | False | `operator_verdict = str(operator_control.get("verdict", "UNKNOWN"))` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 234 | True | `"operator_control_confirmed": operator_confirmed,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 235 | False | `"operator_control_verdict": operator_verdict,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 236 | False | `"operator_control_evidence_count": operator_evidence_count,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 253 | False | `def _build_operator_control_evidence(` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 303 | True | `"operator_control_confirmed": False,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 408 | True | `operator_control_confirmed = bool(depth_requirement_met and evidence_count >= 3)` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 418 | True | `"operator_control_confirmed": operator_control_confirmed,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 419 | True | `"verdict": "OPERATOR_CONTROL_EVIDENCED" if operator_control_confirmed else "OPERATOR_CONTROL_NOT_CONFIRMED",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 524 | False | `"operator_control_evidence",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 545 | False | `"operator_control_evidence",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1452 | False | `operator_control = cls._build_operator_control_evidence(` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1473 | False | `operator_control=operator_control,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1486 | True | `"operator_control_confirmed": bool(operator_control.get("operator_control_confirmed", False)),` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1487 | False | `"operator_control_verdict": operator_control.get("verdict"),` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1488 | False | `"operator_control_evidence_count": int(operator_control.get("evidence_count", 0)),` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1560 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1561 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1657 | False | `"operator_control": operator_control,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1703 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1704 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1761 | True | `"operator_control_confirmed": False,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1762 | False | `"operator_control_verdict": "NO_OPERATOR_CONTROL_EVIDENCE",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1763 | False | `"operator_control_evidence_count": 0,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1781 | False | `"operator_control": {` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1793 | True | `"operator_control_confirmed": False,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1860 | True | `"operator_control_confirmed": False,` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1861 | False | `"operator_control_verdict": "NO_OPERATOR_CONTROL_EVIDENCE",` |
| `backend\campaign_engine\campaign_evidence_builder.py` | 1862 | False | `"operator_control_evidence_count": 0,` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 43 | False | `self._operator_control(ev, labels)` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 68 | False | `"operator_control_interpretation": self._operator_summary(ev),` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 88 | False | `def _operator_control(self, ev: Dict[str, Any], labels: List[str]) -> None:` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 89 | False | `oc = ev.get("operator_control") or {}` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 90 | True | `if oc.get("operator_control_confirmed") is True:` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 228 | False | `oc = ev.get("operator_control") or {}` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 230 | True | `"confirmed": bool(oc.get("operator_control_confirmed")),` |
| `backend\campaign_engine\diagnostic_doctrine_classifier.py` | 265 | False | `"operator_control",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 46 | False | `operator_control = _safe_dict(ev.get("operator_control"))` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 47 | False | `oc_flags = _safe_dict(operator_control.get("evidence_flags"))` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 100 | False | `"operator_control.evidence_flags.high_volume_controlled_spread",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 124 | False | `"operator_control.evidence_flags.absorption_against_resistance",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 125 | False | `"operator_control.evidence_flags.higher_lows_after_tests",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 145 | False | `"operator_control.evidence_flags.higher_lows_after_tests",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 146 | False | `"operator_control.evidence_flags.demand_efficiency_dominates_supply",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 164 | False | `"operator_control.evidence_flags.recapture_after_breakdown",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 177 | False | `"operator_control.evidence_flags.shortening_downside_thrust",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 196 | False | `"operator_control.evidence_flags.recapture_after_breakdown",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 221 | False | `"operator_control.evidence_flags.high_volume_controlled_spread",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 223 | False | `"operator_control.evidence_flags.demand_efficiency_dominates_supply",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 224 | False | `"operator_control.evidence_flags.supply_failure",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 247 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 248 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\early_operator_footprint_engine.py` | 287 | False | `"operator_control",` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 80 | False | `from backend.campaign_engine.operator_control_production_mutation_gate import (` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 81 | False | `evaluate_d3d_operator_control_candidate,` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 84 | False | `from campaign_engine.operator_control_production_mutation_gate import (` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 85 | False | `evaluate_d3d_operator_control_candidate,` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 88 | False | `return evaluate_d3d_operator_control_candidate(campaign)` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 96 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 176 | True | `if bool(operator_control.get("operator_control_confirmed")):` |
| `backend\campaign_engine\explicit_geometry_sml_diagnostic_engine.py` | 191 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py` | 72 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py` | 125 | False | `risk_side_must_not_confirm_operator_control = bool(risk_side_upper_zone)` |
| `backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py` | 155 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py` | 164 | True | `"operator_control_confirmed_current": bool(operator_control.get("operator_control_confirmed")),` |
| `backend\campaign_engine\explicit_sml_taxonomy_audit_engine.py` | 180 | False | `"risk_side_must_not_confirm_operator_control": risk_side_must_not_confirm_operator_control,` |
| `backend\campaign_engine\explicit_upper_zone_diagnostic_engine.py` | 64 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\explicit_upper_zone_diagnostic_engine.py` | 144 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\explicit_upper_zone_diagnostic_engine.py` | 153 | True | `"operator_control_confirmed_current": bool(operator_control.get("operator_control_confirmed")),` |
| `backend\campaign_engine\operator_control_classifier.py` | 4 | False | `operator_dominance/operator_control_classifier.py` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 63 | False | `def classify_operator_control_confirmation_candidate(` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 71 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 78 | True | `operator_control_confirmed = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 96 | True | `if operator_control_confirmed:` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 98 | True | `reason = "Existing operator_control engine already confirms tape-derived Composite Operator control."` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 127 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 128 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 138 | True | `"operator_control_confirmed_current": operator_control_confirmed,` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 144 | True | `"candidate_rule": "footprint_count >= 4 AND hard_confirmation_count >= 1 AND caution_count == 0 AND operator_control_confirmed_current == false",` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 150 | False | `"operator_control",` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 31 | False | `ENGINE_VERSION = "phase_d3j_operator_control_plausibility_status_v1"` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 56 | False | `def classify_operator_control_plausibility(` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 62 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 75 | True | `legacy_confirmed = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 83 | False | `production_engine = operator_control.get("production_confirmation_engine")` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 84 | False | `production_engine_version = operator_control.get("production_confirmation_engine_version")` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 140 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 141 | True | `"operator_control_unconfirmed_by_this_engine": False,` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 155 | True | `"legacy_operator_control_confirmed": legacy_confirmed,` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 168 | False | `"operator_control_verdict": operator_control.get("verdict"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 169 | False | `"operator_control_status": operator_control.get("status"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 170 | False | `"operator_control_method_basis": operator_control.get("method_basis"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 171 | False | `"operator_control_evidence_count": operator_control.get("evidence_count"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 172 | False | `"operator_control_engine": operator_control.get("engine"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 173 | False | `"operator_control_engine_version": operator_control.get("engine_version"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 176 | True | `"not_derived_from_scores": operator_control.get("not_derived_from_scores"),` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 177 | False | `"not_derived_from_gamma": operator_control.get("not_derived_from_gamma"),` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 19 | False | `ENGINE_VERSION = "phase_d3d_operator_control_production_mutation_gate_explicit_geometry_only_v2"` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 98 | False | `def evaluate_d3d_operator_control_candidate(campaign: Dict[str, Any]) -> Dict[str, Any]:` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 101 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 113 | True | `already_confirmed = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 128 | True | `and shadow.get("operator_control_confirmed_by_this_engine") is False` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 129 | False | `and shadow.get("operator_control_confirmation_impact") == "NONE"` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 141 | True | `block_reasons.append("Operator control is already confirmed in evidence.operator_control.")` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 179 | True | `"mutation_target": "evidence.operator_control.operator_control_confirmed",` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 188 | False | `def build_d3d_operator_control_mutation(campaign: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 191 | False | `operator_control = deepcopy(_as_dict(evidence.get("operator_control")))` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 226 | True | `operator_control["operator_control_confirmed"] = True` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 227 | True | `operator_control["verdict"] = "OPERATOR_CONTROL_CONFIRMED"` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 228 | False | `operator_control["production_confirmation"] = confirmation` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 229 | False | `operator_control["production_confirmation_engine"] = ENGINE_NAME` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 230 | False | `operator_control["production_confirmation_engine_version"] = ENGINE_VERSION` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 231 | True | `operator_control["production_confirmation_at"] = confirmation["confirmed_at"]` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 232 | False | `operator_control["production_confirmation_basis"] = confirmation["basis"]` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 233 | True | `operator_control["not_derived_from_scores"] = True` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 234 | True | `operator_control["score_impact"] = "NONE"` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 235 | True | `operator_control["rank_impact"] = "NONE"` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 236 | True | `operator_control["state_impact"] = "NONE"` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 237 | False | `evidence["operator_control"] = operator_control` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 243 | True | `"mutation_target": "evidence.operator_control.operator_control_confirmed",` |
| `backend\campaign_engine\structural_location_input_review_engine.py` | 247 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\structural_location_input_review_engine.py` | 248 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\structural_location_validation_engine.py` | 85 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\structural_location_validation_engine.py` | 86 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\structural_location_validation_engine.py` | 333 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\structural_location_validation_engine.py` | 334 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 286 | False | `operator_control = _as_dict(evidence.get("operator_control"))` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 295 | True | `operator_control_confirmed_current = bool(operator_control.get("operator_control_confirmed"))` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 360 | True | `if operator_control_confirmed_current:` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 378 | True | `"operator_control_confirmed_by_this_engine": False,` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 379 | False | `"operator_control_confirmation_impact": "NONE",` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 395 | True | `"operator_control_confirmed_current": operator_control_confirmed_current,` |
| `backend\campaign_engine\wyckoff_weis_operator_confirmation_engine.py` | 427 | False | `"operator_control",` |

## Preliminary No-Drift Interpretation

A hit is not automatically drift.

A hit becomes drift-risk only if legacy operator-control confirmation is used to alter score, rank, state, transition, production confirmation, or trade signal status.

D3J should be the preferred read-only endpoint for plausibility display and review.

D3D remains the only controlled production mutation gate for operator-control confirmation.

## Required Follow-Up Review

Each risk-context hit should be reviewed to determine whether it is:

1. Safe diagnostic display;
2. Safe audit/endpoint plumbing;
3. Legacy preservation;
4. Drift-risk consumer logic.

No remediation should occur until the consumer location is identified precisely.
