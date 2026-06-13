# Sigmalytic Campaign State Specification — V1

## Core Decision

The primary object is the Campaign.

A symbol may have many campaigns over time.

Each campaign moves through a defined lifecycle:

BIRTH → CONFIRMED → SURVIVING → EXPANDING → MATURING → DISTRIBUTION_RISK → CLOSED

Regression is allowed between active states when structure weakens.

---

## Valid States

### 1. BIRTH

A campaign is born when the validated research stack detects early structural resolution.

Required evidence:

- OBS_Q4
- PROG_Q4
- State 1
- SPD = Yes
- DEI = No
- DUR_60_120 preferred
- Accumulation classification
- D-Score >= 2 preferred

Interpretation:

The stock is under meaningful structural resistance, seller pressure is diminishing, and the market has not yet fully repriced the transition.

---

### 2. CONFIRMED

A campaign becomes confirmed when SOS/JAC appears.

Required evidence:

- Break above resistance
- Expanding spread
- Above-normal volume
- Close in upper half of range
- Rel volume preferably > 1.5x

Interpretation:

The campaign has shown a Sign of Strength / Jump Across the Creek. Demand is now visible.

---

### 3. SURVIVING

A campaign is surviving when BU/LPS and CHoCH confirm that the breakout structure is holding.

Required evidence:

- Pullback toward breakout level
- Reduced volume on pullback
- Narrowing range
- Support holds
- Up-wave efficiency exceeds down-wave efficiency by 2x or more

Interpretation:

The campaign survived the test. Supply is not reasserting control.

---

### 4. EXPANDING

A campaign is expanding when markup is underway.

Required evidence:

- Progress score accelerating
- Up-wave efficiency improving
- Relative strength improving
- Higher highs / higher lows
- Operator Dominance remains elevated

Interpretation:

The campaign has moved from absorption into markup.

---

### 5. MATURING

A campaign is maturing when it approaches its projected target zone.

Required evidence:

- P&F target within 15%
- Cause score projection approaching conservative target
- Expansion still active
- Operator Dominance not yet deteriorating sharply

Interpretation:

The campaign remains active, but the easy part of the move may already be captured.

---

### 6. DISTRIBUTION_RISK

A campaign enters distribution risk when two or more distribution warnings appear.

Distribution triggers:

- Obstacle score drops below Q2
- Behavioral state transitions to Ambiguous or Distribution
- Volume expands but h3_return < 1%
- Up-wave price efficiency falls below down-wave efficiency
- Failed breakout
- Volume climax
- Consecutive lower lows with expanding volume
- Operator Dominance falls below warning threshold

Interpretation:

The operator may be preparing to exit into crowd buying.

---

### 7. CLOSED

A campaign is closed when the lifecycle ends.

Close reasons:

- TARGET_REACHED
- STOP_HIT
- OPERATOR_EXIT
- TIMEOUT
- MANUAL
- INVALIDATED

Interpretation:

The campaign is no longer active and becomes part of the historical analog database.

---

## Valid Transition Matrix

BIRTH → CONFIRMED, CLOSED

CONFIRMED → SURVIVING, BIRTH, CLOSED

SURVIVING → EXPANDING, CONFIRMED, CLOSED

EXPANDING → MATURING, SURVIVING, CLOSED

MATURING → DISTRIBUTION_RISK, EXPANDING, CLOSED

DISTRIBUTION_RISK → CLOSED, MATURING

CLOSED → terminal

---

## Design Rules

1. SQL defines allowed state names.
2. Python enforces valid transitions.
3. Every state transition must create a campaign_state_history row.
4. Every campaign day must create a campaign_observations row.
5. Historical analog matching is tied to campaign state, not just birth.
6. Operator Dominance is recalculated at each observation.
7. Distribution Risk is recalculated at each observation.
8. Campaigns are never deleted; they are closed.