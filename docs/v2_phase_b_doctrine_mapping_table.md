# Sigmalytic V2 Phase B — Doctrine Mapping Table

Date: 2026-07-03  
Status: Phase B diagnostic doctrine map  
Scope: Documentation only  
Code impact: NONE  
Score impact: NONE  
Rank impact: NONE  
State impact: NONE  
Transition impact: NONE  

---

## 1. Purpose

Phase B defines the formal doctrine mapping table for Sigmalytic V2.

This file exists to prevent doctrine drift before any classifier, ranking model, state transition engine, or campaign advancement rule is allowed to use the evidence.

Phase B does not change scoring, ranking, campaign state, or transitions.

Phase B only answers:

- What does each evidence field mean doctrinally?
- Which doctrine does the field belong to?
- Is the field raw tape evidence, derived tape evidence, or diagnostic aggregation?
- Which campaign lifecycle stage does the field support?
- Is the field currently diagnostic-only?
- Could the field later become transition-eligible?
- Does the field describe campaign behavior or tactical behavior?
- Does the field create confirmation, caution, conflict, or blocking evidence?

---

## 2. Doctrine Layers Currently Live in Evidence Builder

The live evidence object exposes the following major doctrine sections:

| Evidence Section | Doctrine Family | Current Status | Scoring Impact | Ranking Impact | State Impact | Transition Impact |
|---|---|---:|---:|---:|---:|---:|
| raw_metrics | Raw OHLCV / Tape-derived measurements | LIVE | NONE | NONE | NONE | NONE |
| operator_control | Operator campaign control | LIVE | NONE | NONE | NONE | NONE |
| wyckoff_doctrine | Wyckoff Verdict + Wyckoff Survival | LIVE | NONE | NONE | NONE | NONE |
| multi_scale_weis | David Weis / Weis Wave | LIVE | NONE | NONE | NONE | NONE |
| vsa_weis_overlay | VSA + Weis overlay | LIVE | NONE | NONE | NONE | NONE |
| transition_readiness | Diagnostic readiness summary | LIVE | NONE | NONE | NONE | NONE |
| symbol_behavior_profile | Symbol behavior / liquidity context | LIVE | NONE | NONE | NONE | NONE |

---

## 3. Evidence Classification Types

| Classification | Meaning |
|---|---|
| RAW_TAPE_MEASUREMENT | Direct or near-direct measurement from OHLCV bars, spreads, closes, volume, range position, or price progress. |
| DERIVED_TAPE_EVIDENCE | Computed from raw tape but not derived from existing Sigmalytic scores. |
| DOCTRINE_DIAGNOSTIC | A doctrine-specific diagnostic verdict or score. |
| READINESS_DIAGNOSTIC | A diagnostic readiness indication that is not yet allowed to move state. |
| CONTEXT_DIAGNOSTIC | A liquidity, volatility, or symbol-specific context adjustment. |
| CONFLICT_EVIDENCE | Evidence that may caution, block, or downgrade interpretation later. |

---

## 4. Campaign Lifecycle States

| Lifecycle Stage | Meaning |
|---|---|
| MICRO_OBSERVATION | Early observation only; insufficient for campaign confirmation. |
| BIRTH_WATCH | Possible early campaign birth. |
| CONFIRMATION | Evidence begins supporting institutional/operator campaign behavior. |
| SURVIVAL | Campaign survives tests, pullbacks, adverse pressure, or supply. |
| EXPANSION | Campaign advances after control or absorption. |
| MATURING | Campaign has advanced enough to require caution and distribution-risk monitoring. |
| DISTRIBUTION_RISK | Evidence suggests exhaustion, upthrust, no demand, buying climax, or supply return. |

---

## 5. Raw Metrics Doctrine Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| bar_count | RAW_TAPE_MEASUREMENT | All doctrines | Available historical depth. Determines whether evidence is shallow, usable, or full-campaign depth. | All stages | Diagnostic | Yes, as minimum depth gate |
| bar_depth_tier | DERIVED_TAPE_EVIDENCE | All doctrines | Classifies whether the symbol has enough data for campaign-level interpretation. | Birth through Maturity | Diagnostic | Yes |
| bar_depth_full_campaign_eligible | DERIVED_TAPE_EVIDENCE | All doctrines | Confirms sufficient bars for full campaign analysis. | Survival, Expansion, Maturity | Diagnostic | Yes |
| max_campaign_state_by_depth | DERIVED_TAPE_EVIDENCE | All doctrines | Maximum state that evidence depth can responsibly support. | All stages | Diagnostic | Yes |
| latest_close_location | RAW_TAPE_MEASUREMENT | Wyckoff / Weis / VSA | Where the close occurs within the bar; high close supports demand, low close supports supply. | Confirmation, Survival, Expansion | Diagnostic | Yes |
| latest_effort_ratio | DERIVED_TAPE_EVIDENCE | Weis / VSA | Relative volume effort. Used with spread/result to judge effort versus result. | Confirmation, Survival, Distribution Risk | Diagnostic | Yes |
| latest_spread_ratio | DERIVED_TAPE_EVIDENCE | VSA / Weis | Relative spread expansion or compression. Used to detect absorption, no demand, no supply, or climactic action. | Confirmation, Survival, Distribution Risk | Diagnostic | Yes |
| absorption_bar_count | DERIVED_TAPE_EVIDENCE | Wyckoff / Weis | Count of bars where effort does not produce proportional downside progress. | Birth, Confirmation, Survival | Diagnostic | Yes |
| range_position_40 | DERIVED_TAPE_EVIDENCE | Wyckoff / Livermore | Position in recent range. High position after absorption may support markup or maturity; low position after failed breakdown may support spring/recapture. | Birth, Expansion, Maturity | Diagnostic | Yes |
| up_progress_20 | DERIVED_TAPE_EVIDENCE | Livermore / Weis | Recent upside progress. Used to judge whether demand is producing result. | Confirmation, Expansion | Diagnostic | Yes |
| down_progress_20 | DERIVED_TAPE_EVIDENCE | Livermore / Weis | Recent downside progress. Used to judge whether supply is producing result. | Survival, Distribution Risk | Diagnostic | Yes |
| up_efficiency_20 | DERIVED_TAPE_EVIDENCE | Weis | Upside progress per unit of volume/effort. | Confirmation, Expansion | Diagnostic | Yes |
| down_efficiency_20 | DERIVED_TAPE_EVIDENCE | Weis | Downside progress per unit of volume/effort. | Survival, Distribution Risk | Diagnostic | Yes |
| failing_downside_count | DERIVED_TAPE_EVIDENCE | Wyckoff / Weis | Counts failed downside attempts. Supports absorption or operator defense. | Survival | Diagnostic | Yes |
| drawdown_from_recent_high | DERIVED_TAPE_EVIDENCE | Livermore / Wyckoff | Measures retreat from recent high. Helps distinguish normal reaction from loss of control. | Survival, Maturity, Distribution Risk | Diagnostic | Yes |
| recent_support | DERIVED_TAPE_EVIDENCE | Wyckoff / Livermore | Recent support reference. Used for LPS, spring, and survival interpretation. | Birth, Survival | Diagnostic | Yes |
| prior_support | DERIVED_TAPE_EVIDENCE | Wyckoff / Livermore | Older support reference. Used to compare whether structure is improving or deteriorating. | Survival | Diagnostic | Yes |
| prior_down_thrust | DERIVED_TAPE_EVIDENCE | Weis | Prior downside thrust measurement. Used against current down thrust. | Survival, Distribution Risk | Diagnostic | Yes |
| current_down_thrust | DERIVED_TAPE_EVIDENCE | Weis | Current downside thrust measurement. Expansion of downside thrust may warn of supply return. | Survival, Distribution Risk | Diagnostic | Yes |

---

## 6. Operator Control Doctrine Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| operator_control.verdict | DOCTRINE_DIAGNOSTIC | Operator Campaign Control | Summary verdict that raw tape behavior supports operator control. | Confirmation, Survival, Expansion | Diagnostic | Yes |
| operator_control.operator_control_confirmed | DOCTRINE_DIAGNOSTIC | Operator Campaign Control | Boolean confirmation that sufficient evidence supports operator control. | Confirmation, Survival, Expansion | Diagnostic | Yes |
| operator_control.evidence_count | DERIVED_TAPE_EVIDENCE | Operator Campaign Control | Count of raw evidence flags supporting control. | Confirmation, Survival, Expansion | Diagnostic | Yes |
| operator_control.method_basis | CONTROL_GUARDRAIL | Operator Campaign Control | Confirms method is RAW_OHLCV_TAPE_BEHAVIOR_ONLY. | All stages | Guardrail | Must remain required |
| operator_control.not_derived_from_scores | CONTROL_GUARDRAIL | Operator Campaign Control | Confirms operator control is not derived from existing scores. | All stages | Guardrail | Must remain required |
| operator_control.depth_requirement_met | READINESS_DIAGNOSTIC | Operator Campaign Control | Confirms enough bars exist to trust operator control evidence. | Confirmation onward | Diagnostic | Yes |
| evidence_flags.survives_adverse_tests | DERIVED_TAPE_EVIDENCE | Wyckoff / Operator Control | Price survives adverse pressure without structural failure. | Survival | Diagnostic | Yes |
| evidence_flags.higher_lows_after_tests | DERIVED_TAPE_EVIDENCE | Wyckoff / Livermore | Higher lows after tests imply improving sponsorship. | Survival, Expansion | Diagnostic | Yes |
| evidence_flags.recapture_after_breakdown | DERIVED_TAPE_EVIDENCE | Wyckoff | Recapture after breakdown suggests spring-like recovery or bear trap. | Birth, Survival | Diagnostic | Yes |
| evidence_flags.demand_efficiency_dominates_supply | DERIVED_TAPE_EVIDENCE | Weis / Operator Control | Demand produces more result per unit effort than supply. | Confirmation, Expansion | Diagnostic | Yes |
| evidence_flags.absorption_against_resistance | DERIVED_TAPE_EVIDENCE | Wyckoff | Supply is absorbed near resistance. | Confirmation, Expansion | Diagnostic | Yes |
| evidence_flags.high_volume_controlled_spread | DERIVED_TAPE_EVIDENCE | VSA / Wyckoff | High effort with controlled spread can imply absorption. | Birth, Survival | Diagnostic | Yes |
| evidence_flags.shortening_downside_thrust | DERIVED_TAPE_EVIDENCE | Weis | Downside thrust contracts, implying supply is losing effectiveness. | Survival | Diagnostic | Yes |
| evidence_flags.supply_failure | DERIVED_TAPE_EVIDENCE | Wyckoff / Weis | Supply effort fails to create downside result. | Survival, Expansion | Diagnostic | Yes |

---

## 7. Wyckoff Doctrine Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| wyckoff_doctrine.verdict.verdict | DOCTRINE_DIAGNOSTIC | Wyckoff | Overall Wyckoff verdict such as WATCH or stronger confirmation. | Birth through Expansion | Diagnostic | Yes |
| wyckoff_doctrine.phase | DOCTRINE_DIAGNOSTIC | Wyckoff | Current Wyckoff phase interpretation. | Birth through Maturity | Diagnostic | Yes |
| spring_score | DOCTRINE_DIAGNOSTIC | Wyckoff Phase C | Measures spring/bear-trap behavior. | Birth, Survival | Diagnostic | Yes |
| sign_of_strength_score | DOCTRINE_DIAGNOSTIC | Wyckoff Phase D/E | Measures SOS behavior after absorption or range resolution. | Confirmation, Expansion | Diagnostic | Yes |
| supply_absorption_score | DOCTRINE_DIAGNOSTIC | Wyckoff | Measures whether supply is being absorbed. | Birth, Survival, Confirmation | Diagnostic | Yes |
| stopping_climax_score | DOCTRINE_DIAGNOSTIC | Wyckoff | Measures possible stopping action after decline. | Birth Watch | Diagnostic | Yes |
| behavioral_resolution_score | DOCTRINE_DIAGNOSTIC | Wyckoff / Behavioral Resolution | Measures price resolution after obstacle. | Confirmation, Expansion | Diagnostic | Yes |
| meaningful_resistance_score | DOCTRINE_DIAGNOSTIC | Wyckoff | Measures whether a meaningful obstacle exists. | Birth, Confirmation | Diagnostic | Yes |
| progress_against_resistance | DERIVED_TAPE_EVIDENCE | Wyckoff | Measures progress through or against resistance. | Confirmation, Expansion | Diagnostic | Yes |
| cause_width_pct | DERIVED_TAPE_EVIDENCE | Wyckoff Cause | Measures horizontal cause/range width. | Birth, Confirmation | Diagnostic | Yes |
| support_level | DERIVED_TAPE_EVIDENCE | Wyckoff | Support reference for spring, LPS, and survival. | Birth, Survival | Diagnostic | Yes |
| resistance_level | DERIVED_TAPE_EVIDENCE | Wyckoff | Resistance reference for SOS, absorption, and breakout. | Confirmation, Expansion | Diagnostic | Yes |
| survival.survival_state | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Whether campaign is surviving, at risk, or failing. | Survival | Diagnostic | Yes |
| survival.survival_grade | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Quality grade for survival evidence. | Survival | Diagnostic | Yes |
| wyckoff_survival_score | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Aggregate survival score. | Survival | Diagnostic | Yes, after calibration |
| sos_persistence_score | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Persistence of strength after SOS. | Survival, Expansion | Diagnostic | Yes |
| lps_quality_score | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Quality of Last Point of Support behavior. | Survival, Expansion | Diagnostic | Yes |
| absorption_continuation_score | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Continuation of absorption after initial evidence. | Survival | Diagnostic | Yes |
| range_escape_stability_score | DOCTRINE_DIAGNOSTIC | Wyckoff Survival | Stability after escaping a range. | Expansion | Diagnostic | Yes |

---

## 8. Weis / Multi-Scale Weis Doctrine Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| multi_scale_weis.dominant_wave_direction | DOCTRINE_DIAGNOSTIC | David Weis / Weis Wave | Dominant wave direction across scales. | Confirmation, Expansion, Distribution Risk | Diagnostic | Yes |
| multi_scale_weis.wave_coherence_score | DOCTRINE_DIAGNOSTIC | Weis Wave | Agreement strength across micro, meso, and macro waves. | Confirmation, Expansion | Diagnostic | Yes |
| multi_scale_weis.conflict_state | DOCTRINE_DIAGNOSTIC | Weis Wave | Whether wave structure is aligned or conflicted. | All stages | Diagnostic | Yes |
| multi_scale_weis.phase_permission | DOCTRINE_DIAGNOSTIC | Weis Wave | Interprets whether wave evidence permits expansion or warns caution. | Expansion, Maturity | Diagnostic | Yes |
| micro.direction | DOCTRINE_DIAGNOSTIC | Weis Wave | Short-term wave direction. | Tactical / Timing | Diagnostic | Limited |
| meso.direction | DOCTRINE_DIAGNOSTIC | Weis Wave | Intermediate campaign wave direction. | Confirmation, Survival, Expansion | Diagnostic | Yes |
| macro.direction | DOCTRINE_DIAGNOSTIC | Weis Wave | Larger campaign wave direction. | Survival, Expansion, Maturity | Diagnostic | Yes |
| wave_volume_z | DERIVED_TAPE_EVIDENCE | Weis / VSA | Relative volume on current wave. | Confirmation, Distribution Risk | Diagnostic | Yes |
| wave_efficiency | DERIVED_TAPE_EVIDENCE | Weis | Price result per unit effort. | Confirmation, Expansion, Distribution Risk | Diagnostic | Yes |
| wave_distance_atr | DERIVED_TAPE_EVIDENCE | Weis | Wave distance normalized by ATR. | Expansion, Maturity | Diagnostic | Yes |
| wave_effort_ratio | DERIVED_TAPE_EVIDENCE | Weis / VSA | Wave effort relative to normal. | Confirmation, Distribution Risk | Diagnostic | Yes |
| wave_close_location | RAW_TAPE_MEASUREMENT | Weis / VSA | Close location of latest wave. | Confirmation, Survival, Expansion | Diagnostic | Yes |
| upwave_result_improving | DERIVED_TAPE_EVIDENCE | Weis | Up waves are producing better result. | Confirmation, Expansion | Diagnostic | Yes |
| downwave_result_improving | DERIVED_TAPE_EVIDENCE | Weis | Down waves are producing better result. Can warn of supply return. | Distribution Risk | Diagnostic | Yes |
| shortening_upside_thrust | DERIVED_TAPE_EVIDENCE | Weis | Upward progress is shortening. May warn of exhaustion. | Maturity, Distribution Risk | Diagnostic | Yes |
| shortening_downside_thrust | DERIVED_TAPE_EVIDENCE | Weis | Downside progress is shortening. May support survival. | Survival | Diagnostic | Yes |
| effort_producing_upside_result | DERIVED_TAPE_EVIDENCE | Weis | Bullish effort is producing price result. | Confirmation, Expansion | Diagnostic | Yes |
| effort_failing_upside_result | DERIVED_TAPE_EVIDENCE | Weis | Bullish effort fails to produce upside. | Maturity, Distribution Risk | Diagnostic | Yes |
| effort_producing_downside_result | DERIVED_TAPE_EVIDENCE | Weis | Bearish effort is producing downside. | Distribution Risk | Diagnostic | Yes |
| effort_failing_downside_result | DERIVED_TAPE_EVIDENCE | Weis | Bearish effort fails to produce downside. | Survival, Expansion | Diagnostic | Yes |
| demand_dominance | DERIVED_TAPE_EVIDENCE | Weis / Operator Control | Demand wave behavior dominates supply. | Confirmation, Expansion | Diagnostic | Yes |
| supply_dominance | DERIVED_TAPE_EVIDENCE | Weis / Distribution | Supply wave behavior dominates demand. | Distribution Risk | Diagnostic | Yes |

---

## 9. VSA / Weis Overlay Doctrine Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| vsa_bias | DOCTRINE_DIAGNOSTIC | VSA / Weis | Aggregate VSA directional bias. | Confirmation, Distribution Risk | Diagnostic | Yes |
| vsa_alert | DOCTRINE_DIAGNOSTIC | VSA / Weis | Human-readable VSA alert. | All stages | Diagnostic | Yes |
| buying_climax | DERIVED_TAPE_EVIDENCE | VSA / Wyckoff | High effort near highs may indicate climactic demand/exhaustion. | Distribution Risk | Diagnostic | Yes |
| upthrust_supply | DERIVED_TAPE_EVIDENCE | VSA / Wyckoff | Upthrust suggests supply over demand after breakout attempt. | Distribution Risk | Diagnostic | Yes |
| no_supply_test | DERIVED_TAPE_EVIDENCE | VSA / Wyckoff | Weak supply on test may support survival. | Survival, Expansion | Diagnostic | Yes |
| no_demand_test | DERIVED_TAPE_EVIDENCE | VSA / Wyckoff | Weak demand on rally may caution against expansion. | Maturity, Distribution Risk | Diagnostic | Yes |
| effort_vs_result_divergence | DERIVED_TAPE_EVIDENCE | Weis / VSA | Effort fails to produce expected result. Meaning depends on direction and location. | Survival or Distribution Risk | Diagnostic | Yes |

---

## 10. Transition Readiness Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| transition_readiness.readiness_verdict | READINESS_DIAGNOSTIC | Evidence Integration | Summarizes maximum readiness supported by evidence. | All stages | Diagnostic Only | Yes, later |
| transition_readiness.evidence_supported_state | READINESS_DIAGNOSTIC | Evidence Integration | Highest state evidence appears capable of supporting. | All stages | Diagnostic Only | Yes, later |
| transition_readiness.max_campaign_state_by_depth | READINESS_DIAGNOSTIC | Evidence Depth | Highest state allowed by available bar depth. | All stages | Diagnostic Only | Yes |
| transition_readiness.operator_control_confirmed | READINESS_DIAGNOSTIC | Operator Control | Whether operator control supports readiness. | Confirmation onward | Diagnostic Only | Yes |
| transition_readiness.operator_control_evidence_count | DERIVED_TAPE_EVIDENCE | Operator Control | Count of operator control evidence flags. | Confirmation onward | Diagnostic Only | Yes |
| transition_readiness.vsa_evidence_count | DERIVED_TAPE_EVIDENCE | VSA / Weis | Count of VSA evidence flags. | Survival through Distribution Risk | Diagnostic Only | Yes |
| transition_readiness.blocking_reasons | CONFLICT_EVIDENCE | Evidence Integration | Reasons stronger transition should be blocked. | All stages | Diagnostic Only | Yes |
| readiness_flags.micro_observation_ready | READINESS_DIAGNOSTIC | Evidence Integration | Evidence can support observation only. | Micro Observation | Diagnostic Only | Yes |
| readiness_flags.birth_watch_ready | READINESS_DIAGNOSTIC | Evidence Integration | Evidence can support birth watch. | Birth Watch | Diagnostic Only | Yes |
| readiness_flags.survival_ready | READINESS_DIAGNOSTIC | Evidence Integration | Evidence can support survival interpretation. | Survival | Diagnostic Only | Yes |
| readiness_flags.confirmation_ready | READINESS_DIAGNOSTIC | Evidence Integration | Evidence can support confirmation interpretation. | Confirmation | Diagnostic Only | Yes |
| readiness_flags.full_campaign_ready | READINESS_DIAGNOSTIC | Evidence Integration | Evidence can support full campaign interpretation. | Expansion, Maturity | Diagnostic Only | Yes |

---

## 11. Symbol Behavior Profile Map

| Field | Evidence Type | Doctrine Family | Doctrinal Meaning | Lifecycle Support | Current Use | Future Transition Eligible |
|---|---|---|---|---|---|---|
| liquidity_class | CONTEXT_DIAGNOSTIC | Context | Low liquidity can reduce reliability of volume evidence. | All stages | Diagnostic | As caution only |
| volatility_class | CONTEXT_DIAGNOSTIC | Context | Volatility context affects interpretation of spread, thrust, and effort. | All stages | Diagnostic | As caution only |
| atr_pct | RAW_TAPE_MEASUREMENT | Context | ATR as percentage of price. | All stages | Diagnostic | As context only |
| latest_volume_ratio | DERIVED_TAPE_EVIDENCE | VSA / Weis | Latest volume relative to average. | Confirmation, Distribution Risk | Diagnostic | Yes |
| latest_volume_z | DERIVED_TAPE_EVIDENCE | VSA / Weis | Standardized latest volume. | Confirmation, Distribution Risk | Diagnostic | Yes |
| latest_spread_pct | RAW_TAPE_MEASUREMENT | VSA / Weis | Latest spread as percent of price. | All stages | Diagnostic | Yes |
| latest_range_position_60 | DERIVED_TAPE_EVIDENCE | Wyckoff / Livermore | Position in 60-bar range. | Birth, Expansion, Maturity | Diagnostic | Yes |
| last5_return | RAW_TAPE_MEASUREMENT | Livermore | Short-term price progress. | Tactical / Confirmation | Diagnostic | Limited |
| last20_return | RAW_TAPE_MEASUREMENT | Livermore | Intermediate price progress. | Confirmation, Expansion | Diagnostic | Yes |

---

## 12. Current Guardrails

These guardrails are mandatory and must remain intact until a later phase explicitly changes them:

| Guardrail | Required Value |
|---|---|
| score_impact | NONE |
| rank_impact | NONE |
| state_impact | NONE |
| transition_impact | NONE |
| diagnostic_only | true |
| state_transition_enabled | false |
| wired_into_evidence_builder | true |
| operator_control.method_basis | RAW_OHLCV_TAPE_BEHAVIOR_ONLY |
| operator_control.not_derived_from_scores | true |

---

## 13. Phase B Completion Criteria

Phase B is complete only when:

1. This doctrine mapping table is committed.
2. The live evidence sections are mapped to doctrine families.
3. Each field has a lifecycle interpretation.
4. Each field is labeled raw, derived, diagnostic, readiness, context, or conflict.
5. No scoring code has changed.
6. No ranking code has changed.
7. No campaign state code has changed.
8. No transition logic has changed.
9. The next phase can design a doctrine classifier using this mapping table as its written source.

---

## 14. Explicit Non-Goals

Phase B does not:

- classify campaigns,
- rank campaigns,
- advance campaign states,
- change thresholds,
- alter operator control,
- alter transition readiness,
- modify discovery,
- modify Supabase schema,
- modify frontend display,
- create buy/sell signals.

Phase B is a doctrine control document only.

---

## 15. Next Phase After Phase B

The next phase may design a diagnostic doctrine classifier.

That classifier must consume this mapping table and produce human-readable interpretations such as:

- Wyckoff accumulation support
- Weis wave expansion support
- VSA caution
- Operator control confirmed
- Survival evidence present
- Distribution-risk conflict present

The classifier must remain diagnostic-only until separately authorized.

