# D3K.1 Operator-Control Consumer Triage

Date: 2026-07-05

## Purpose

D3K.1 narrows the D3K consumer audit.

The purpose is to distinguish ordinary operator-control references from possible drift-risk consumer logic.

This is a read-only documentation audit only.

## No-Drift Scope

D3K.1 does not change production code.

D3K.1 does not mutate Supabase.

D3K.1 does not confirm or unconfirm operator control.

D3K.1 does not execute D3D.

D3K.1 does not change score, rank, state, transition, gamma confirmation, or trade signal status.

## Triage Distribution

- LIKELY_SAFE_AUDIT_OR_GUARDRAIL_CONTEXT: 3
- NEUTRAL_OPERATOR_CONTROL_REFERENCE: 270
- REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK: 12
- SAFE_AUDIT_DIAGNOSTIC_CONTEXT: 28

## Review-Required Files

- backend\campaign_api.py: 7
- backend\campaign_engine\operator_control_confirmation_candidate_engine.py: 1
- backend\campaign_engine\operator_control_plausibility_status_engine.py: 1
- backend\campaign_engine\operator_control_production_mutation_gate.py: 3

## Review-Required Hit Table

| File | Line | Danger Terms | Code |
|---|---:|---|---|
| `backend\campaign_api.py` | 310 | score | `"operator_control_not_derived_from_scores": operator_control.get("not_derived_from_scores"),` |
| `backend\campaign_api.py` | 496 | rank | `"operator_control_confirmed_ranked": [` |
| `backend\campaign_api.py` | 602 | score | `"not_derived_from_scores": match.get("operator_control_not_derived_from_scores"),` |
| `backend\campaign_api.py` | 649 | rank, ranking | `operator_rows = list(ranking_payload.get("operator_control_confirmed_ranked") or [])` |
| `backend\campaign_api.py` | 699 | score | `"operator_control_not_derived_from_scores": True,` |
| `backend\campaign_api.py` | 704 | rank, ranking | `"operator_control_confirmed_count": ranking_payload.get("operator_control_confirmed_count"),` |
| `backend\campaign_api.py` | 2320 | target | `"mutation_target": "evidence.operator_control.operator_control_confirmed",` |
| `backend\campaign_engine\operator_control_confirmation_candidate_engine.py` | 98 | composite | `reason = "Existing operator_control engine already confirms tape-derived Composite Operator control."` |
| `backend\campaign_engine\operator_control_plausibility_status_engine.py` | 176 | score | `"not_derived_from_scores": operator_control.get("not_derived_from_scores"),` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 179 | target | `"mutation_target": "evidence.operator_control.operator_control_confirmed",` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 233 | score | `operator_control["not_derived_from_scores"] = True` |
| `backend\campaign_engine\operator_control_production_mutation_gate.py` | 243 | target | `"mutation_target": "evidence.operator_control.operator_control_confirmed",` |

## Review-Required Context Blocks

### backend\campaign_api.py:310

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: score

Safe terms: None

```text
   308:             "operator_control_depth_requirement_met": operator_control.get("depth_requirement_met"),
   309:             "operator_control_method_basis": operator_control.get("method_basis"),
>> 310:             "operator_control_not_derived_from_scores": operator_control.get("not_derived_from_scores"),
   311:             "transition_readiness_verdict": transition_readiness.get("readiness_verdict"),
   312:             "evidence_supported_state": transition_readiness.get("evidence_supported_state"),
```

### backend\campaign_api.py:496

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: rank

Safe terms: None

```text
   494:         "operator_control_confirmed_count": base.get("operator_control_confirmed_count"),
   495:         "ranked_diagnostic_campaigns": ranked_rows,
>> 496:         "operator_control_confirmed_ranked": [
   497:             row for row in ranked_rows
   498:             if row.get("operator_control_confirmed") is True
```

### backend\campaign_api.py:602

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: score

Safe terms: None

```text
   600:             "depth_requirement_met": match.get("operator_control_depth_requirement_met"),
   601:             "method_basis": match.get("operator_control_method_basis"),
>> 602:             "not_derived_from_scores": match.get("operator_control_not_derived_from_scores"),
   603:         },
   604:         "transition_readiness_explanation": {
```

### backend\campaign_api.py:649

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: rank, ranking

Safe terms: None

```text
   647: 
   648:     ranked_rows = list(ranking_payload.get("ranked_diagnostic_campaigns") or [])
>> 649:     operator_rows = list(ranking_payload.get("operator_control_confirmed_ranked") or [])
   650:     conflicted_rows = list(ranking_payload.get("conflicted_campaigns") or [])
   651: 
```

### backend\campaign_api.py:699

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: score

Safe terms: None

```text
   697:             "frontend_impact": "NONE",
   698:             "operator_control_basis": "RAW_OHLCV_TAPE_BEHAVIOR_ONLY",
>> 699:             "operator_control_not_derived_from_scores": True,
   700:         },
   701:         "counts": {
```

### backend\campaign_api.py:704

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: rank, ranking

Safe terms: None

```text
   702:             "total_campaigns": ranking_payload.get("total_campaigns"),
   703:             "full_depth_count": ranking_payload.get("full_depth_count"),
>> 704:             "operator_control_confirmed_count": ranking_payload.get("operator_control_confirmed_count"),
   705:             "aligned_a_diagnostic_count": len(aligned_a_rows),
   706:             "gamma_refresh_needed_count": len(gamma_refresh_rows),
```

### backend\campaign_api.py:2320

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: target

Safe terms: None

```text
   2318:         "mutates_campaigns": bool(execution_authorized and len(mutation_summaries) > 0),
   2319:         "production_confirmation_allowed": bool(execution_authorized),
>> 2320:         "mutation_target": "evidence.operator_control.operator_control_confirmed",
   2321:         "score_impact": "NONE",
   2322:         "rank_impact": "NONE",
```

### backend\campaign_engine\operator_control_confirmation_candidate_engine.py:98

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: composite

Safe terms: None

```text
   96:     if operator_control_confirmed:
   97:         verdict = "ALREADY_CONFIRMED_BY_OPERATOR_CONTROL_ENGINE"
>> 98:         reason = "Existing operator_control engine already confirms tape-derived Composite Operator control."
   99:     elif not footprint_present:
   100:         verdict = "NO_OPERATOR_FOOTPRINT"
```

### backend\campaign_engine\operator_control_plausibility_status_engine.py:176

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: score

Safe terms: None

```text
   174:         "production_confirmation_engine": production_engine,
   175:         "production_confirmation_engine_version": production_engine_version,
>> 176:         "not_derived_from_scores": operator_control.get("not_derived_from_scores"),
   177:         "not_derived_from_gamma": operator_control.get("not_derived_from_gamma"),
   178:     }
```

### backend\campaign_engine\operator_control_production_mutation_gate.py:179

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: target

Safe terms: None

```text
   177:         "d3c_shadow_explicit_geometry_sml": explicit_geometry_sml,
   178:         "d3c_shadow_guardrail_ok": shadow_guardrail_ok,
>> 179:         "mutation_target": "evidence.operator_control.operator_control_confirmed",
   180:         "score_impact": "NONE",
   181:         "rank_impact": "NONE",
```

### backend\campaign_engine\operator_control_production_mutation_gate.py:233

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: score

Safe terms: None

```text
   231:     operator_control["production_confirmation_at"] = confirmation["confirmed_at"]
   232:     operator_control["production_confirmation_basis"] = confirmation["basis"]
>> 233:     operator_control["not_derived_from_scores"] = True
   234:     operator_control["score_impact"] = "NONE"
   235:     operator_control["rank_impact"] = "NONE"
```

### backend\campaign_engine\operator_control_production_mutation_gate.py:243

Triage: REVIEW_REQUIRED_POSSIBLE_CONSUMER_RISK

Danger terms: target

Safe terms: None

```text
   241:         "campaign_id": candidate.get("campaign_id"),
   242:         "timeframe": candidate.get("timeframe"),
>> 243:         "mutation_target": "evidence.operator_control.operator_control_confirmed",
   244:         "old_value": False,
   245:         "new_value": True,
```

## Interpretation Rules

A review-required hit is not automatically drift.

It is only a candidate for manual review.

Actual drift exists only if legacy operator-control confirmation is used to alter score, rank, state, transition, production confirmation, or trade signal status.

Safe contexts include diagnostic endpoints, audit engines, guardrails, dry-run gates, and no-impact metadata.
